#!/usr/bin/env python3
"""Refresh the public GitHub projection; preserve coordinator evidence timestamps."""
import argparse
import base64
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
import runpy
from datetime import datetime, timezone
from urllib.parse import quote

_publisher = runpy.run_path(str(Path(__file__).with_name('publish-data.py')))
publish, snapshot = _publisher['publish'], _publisher['snapshot']

REPO = 'shinycake/quill'


def api(path, repository=REPO, raw=False, paginate=False, allow_missing=False):
    args = ['gh', 'api', f'repos/{repository}/{path}']
    if raw:
        args += ['-H', 'Accept: application/vnd.github.raw+json']
    if paginate:
        args += ['--paginate', '--slurp']
    result = subprocess.run(args, text=True, capture_output=True, timeout=60)
    if result.returncode:
        if allow_missing and 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip())
    value = json.loads(result.stdout)
    return [item for page in value for item in page] if paginate else value


def valid_point(value):
    try:
        datetime.fromisoformat(value['t'].replace('Z', '+00:00'))
        return type(value['done']) is int and type(value['total']) is int and 0 <= value['done'] <= value['total'] and value['total'] > 0
    except (KeyError, AttributeError, ValueError, TypeError):
        return False


def instant(point):
    parsed = datetime.fromisoformat(point['t'].replace('Z', '+00:00'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def clean_points(points):
    """Drop invalid points, collapse repeated commits or timestamps, and return history in time order."""
    seen_sha, seen_time, kept = set(), set(), []
    # Newest write wins when two points share a commit or a timestamp.
    for point in reversed(sorted((p for p in points if isinstance(p, dict) and valid_point(p)), key=instant)):
        sha, when = point.get('sha'), instant(point)
        if (sha and sha in seen_sha) or when in seen_time:
            continue
        seen_sha.add(sha)
        seen_time.add(when)
        kept.append(point)
    return kept[::-1]


def check_plausible(parity, areas, points):
    """Refuse to record a README that parsed badly: no items, or a collapse against the last good point."""
    if not areas or parity['total'] <= 0:
        raise ValueError('Checklist parsed to zero items; keeping the previous snapshot')
    if parity['done'] > parity['total']:
        raise ValueError('Checklist has more done items than total items; keeping the previous snapshot')
    if points:
        last = points[-1]
        if parity['total'] < last['total'] * 0.8 or parity['done'] < last['done'] * 0.8:
            raise ValueError(f"Checklist {parity['done']}/{parity['total']} is far below the last recorded "
                             f"{last['done']}/{last['total']}; keeping the previous snapshot")


def initial_feeds(previous=None):
    # Optional history/coordinator reports cannot be prerequisites for observing GitHub.
    old = previous.get('feeds', {}) if isinstance(previous, dict) else {}
    if not isinstance(old, dict):
        old = {}
    feeds = {'loops.json': {'loops': []}, 'inprogress.json': {'items': []},
             'parity-history.json': {'points': []}}
    for file, key in (('loops.json', 'loops'), ('parity-history.json', 'points')):
        body = old.get(file)
        values = body.get(key) if isinstance(body, dict) else None
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            if key == 'points' and not valid_point(value):
                continue
            feeds[file][key].append(value)
    feeds['parity-history.json']['points'] = clean_points(feeds['parity-history.json']['points'])
    return feeds


def checklist(readme):
    areas = []
    area = None
    for line in readme.splitlines():
        if line.startswith('### '):
            area = {'name': line[4:], 'done': [], 'pending': []}
            areas.append(area)
        match = re.match(r'- \[([ x])\] (.*)', line)
        if match and area:
            text = re.sub(r'\s*<!--.*?-->', '', match[2]).strip()
            if match[1] == 'x':
                area['done'].append(text)
            else:
                blocked = bool(re.search(r'blocked|impossible', text, re.I))
                area['pending'].append({'text': text, 'blocked': blocked, 'reason': text if blocked else None})
    return [a for a in areas if a['done'] or a['pending']]


def refresh(feeds, main, readme, prs, events, commits):
    areas = checklist(readme)
    parity = {'done': sum(len(a['done']) for a in areas),
              'total': sum(len(a['done']) + len(a['pending']) for a in areas)}
    check_plausible(parity, areas, feeds['parity-history.json']['points'])
    feeds['areas.json'] = {'areas': areas}
    # Store only the fields the page renders; full GitHub payloads include large PR bodies/diffs.
    prs = [{**{key: p.get(key) for key in ('number', 'title', 'state', 'merged_at', 'created_at', 'updated_at', 'html_url')},
            'head': {'ref': p.get('head', {}).get('ref')}} for p in prs]
    events = [{**{key: e.get(key) for key in ('type', 'created_at')},
               'payload': {'ref': e.get('payload', {}).get('ref')},
               'actor': {'login': e.get('actor', {}).get('login')}} for e in events]
    commits = [{**{key: c.get(key) for key in ('sha', 'html_url')},
                'author': {'login': (c.get('author') or {}).get('login')},
                'commit': {key: c['commit'].get(key) for key in ('message', 'author')}} for c in commits]
    feeds['github.json'] = {'parity': parity, 'closedPRs': [p for p in prs if p.get('merged_at')],
                            'openPRs': [p for p in prs if p['state'] == 'open'],
                            'events': events, 'commits': commits, 'repo': REPO, 'main_sha': main['sha'], 'observed_at': datetime.now(timezone.utc).isoformat()}
    # PR evidence is authoritative; do not keep merged work "in progress".
    open_numbers = {p['number'] for p in prs if p['state'] == 'open'}
    feeds['inprogress.json']['items'] = [w for w in feeds['inprogress.json']['items'] if w.get('pr') in open_numbers]
    point = {'t': main['commit']['committer']['date'], 'sha': main['sha'][:7], **parity}
    # Raw done/total stay in every point; the dashboard rescales them against the newest total.
    feeds['parity-history.json']['points'] = clean_points([*feeds['parity-history.json']['points'], point])
    return feeds


def progress_items(readme, prs):
    anchors = {}
    area = None
    for line in readme.splitlines():
        if line.startswith('### '):
            area = line[4:]
        match = re.match(r'- \[ \] (.*)<!-- (parity:[a-z0-9-]+) -->', line)
        if match and area:
            anchors[match[2]] = (area, re.sub(r'\s*<!--.*?-->', '', line[6:]).strip())
    items = []
    for pr in prs:
        # Partial work has no completion fragment. An explicit PR marker maps
        # it to an unchecked item without advancing the completion count.
        ids = set(re.findall(r'<!-- parity-work:([a-z0-9-]+) -->', pr.get('body') or ''))
        ids = {'parity:' + id for id in ids}
        for file in api(f'pulls/{pr["number"]}/files?per_page=100', paginate=True):
            path = file['filename']
            if file['status'] == 'removed' or not path.startswith('parity-fragments/') or not path.endswith('.txt'):
                continue
            body = base64.b64decode(api(f'contents/{quote(path)}?ref={pr["head"]["sha"]}')['content']).decode()
            ids.update(id.strip() for id in body.splitlines())
        for id in sorted(ids & anchors.keys()):
            area, item = anchors[id]
            items.append({'area': area, 'item': item, 'label': pr['title'], 'kind': 'pr',
                          'pr': pr['number'], 'url': pr['html_url'], 'branch': pr['head']['ref']})
    return items


RACE = re.compile(r'fast.forward|HTTP 409|HTTP 422|already exists', re.I)


def observe(args):
    """One full read-modify-publish pass. Re-reads the published snapshot so a retry merges, never clobbers."""
    previous = api('contents/data.json?ref=codex/dashboard-data', args.publish_repo, raw=True, allow_missing=True)
    # A first publication needs no seeded branch or working build machine.
    feeds = initial_feeds(previous)
    if previous is None and args.publish_repo != 'shinycake/quill-dashboard':
        try:
            seed = api('contents/data.json?ref=codex/dashboard-data', 'shinycake/quill-dashboard', raw=True, allow_missing=True)
            feeds['parity-history.json'] = initial_feeds(seed)['parity-history.json']
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            print('History seed unavailable; observing the repository without it')
    head = api('commits/main')
    # The checklist moved from README.md to STATUS.md; older heads only have the README copy.
    source = api(f'contents/STATUS.md?ref={head["sha"]}', allow_missing=True) or api(f'contents/README.md?ref={head["sha"]}')
    readme = base64.b64decode(source['content']).decode()
    prs = api('pulls?state=all&sort=updated&direction=desc&per_page=100')
    open_prs = api('pulls?state=open&per_page=100', paginate=True)
    prs = list({p['number']: p for p in [*prs, *open_prs]}.values())
    refresh(feeds, head, readme, prs, api('events?per_page=30'), api(f'commits?sha={head["sha"]}&per_page=30'))
    # A disappearing PR fragment must not freeze parity, PR lists, and commit updates.
    warnings = []
    for pr in open_prs:
        try:
            feeds['inprogress.json']['items'].extend(progress_items(readme, [pr]))
        except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
            warnings.append(f'Could not map PR #{pr["number"]}: {error}')
    feeds['inprogress.json']['warnings'] = warnings
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, body in feeds.items():
            (root / name).write_text(json.dumps(body))
        data = snapshot(root)
        if args.output:
            args.output.write_text(json.dumps(data))
        else:
            publish(data, args.publish_repo)
    print(f'Observed {REPO} main {head["sha"]}: {feeds["github.json"]["parity"]}; {len(open_prs)} open PRs')
    for warning in warnings:
        print(warning)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish-repo', default='shinycake/quill-dashboard')
    parser.add_argument('--output', type=Path, help='Write a snapshot locally without publishing')
    args = parser.parse_args()
    # The caller serializes runs; if one still loses a ref race, retry from the newly published history.
    for attempt in range(1, 4):
        try:
            return observe(args)
        except RuntimeError as error:
            if attempt == 3 or not RACE.search(str(error)):
                raise
            print(f'Publish raced another writer (attempt {attempt}); re-reading and retrying')
            time.sleep(attempt * 3)


if __name__ == '__main__':
    main()
