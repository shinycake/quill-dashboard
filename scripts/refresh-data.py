#!/usr/bin/env python3
"""Refresh the public GitHub projection; preserve coordinator evidence timestamps."""
import base64
import json
import re
import subprocess
import tempfile
from pathlib import Path
import runpy
from datetime import datetime, timezone
from urllib.parse import quote

_publisher = runpy.run_path(str(Path(__file__).with_name('publish-data.py')))
publish, snapshot = _publisher['publish'], _publisher['snapshot']

REPO = 'shinycake/quill'


def api(path, repository=REPO, raw=False):
    args = ['gh', 'api', f'repos/{repository}/{path}']
    if raw:
        args += ['-H', 'Accept: application/vnd.github.raw+json']
    return json.loads(subprocess.check_output(args, text=True))


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
                            'events': events, 'commits': commits, 'observed_at': datetime.now(timezone.utc).isoformat()}
    # PR evidence is authoritative; do not keep merged work "in progress".
    open_numbers = {p['number'] for p in prs if p['state'] == 'open'}
    feeds['inprogress.json']['items'] = [w for w in feeds['inprogress.json']['items'] if w.get('pr') in open_numbers]
    point = {'t': main['commit']['committer']['date'], 'sha': main['sha'][:7], **parity}
    points = feeds['parity-history.json']['points']
    if not points or points[-1].get('sha') != point['sha']:
        points.append(point)
    return feeds


def progress_items(readme, prs):
    anchors = {}
    area = None
    for line in readme.splitlines():
        if line.startswith('### '):
            area = line[4:]
        match = re.match(r'- \[ \] (.*)<!-- (parity:[a-z0-9-]+) -->', line)
        if match and area:
            anchors[match[2]] = (area, match[1].strip())
    items = []
    for pr in prs:
        for file in api(f'pulls/{pr["number"]}/files?per_page=100'):
            path = file['filename']
            if file['status'] == 'removed' or not path.startswith('parity-fragments/') or not path.endswith('.txt'):
                continue
            body = base64.b64decode(api(f'contents/{quote(path)}?ref={pr["head"]["sha"]}')['content']).decode()
            for id in body.splitlines():
                if id.strip() in anchors:
                    area, item = anchors[id.strip()]
                    items.append({'area': area, 'item': item, 'label': pr['title'], 'kind': 'pr',
                                  'pr': pr['number'], 'url': pr['html_url'], 'branch': pr['head']['ref']})
    return items


def main():
    previous = api('contents/data.json?ref=codex/dashboard-data', 'shinycake/quill-dashboard', raw=True)
    feeds = previous['feeds']
    head = api('commits/main')
    readme = base64.b64decode(api(f'contents/README.md?ref={head["sha"]}')['content']).decode()
    # Keep recent closed PRs and fetch the complete current open queue separately.
    prs = json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/pulls?state=all&sort=updated&direction=desc&per_page=100'], text=True))
    open_prs = api('pulls?state=open&per_page=100')
    prs = list({p['number']: p for p in [*prs, *open_prs]}.values())
    refresh(feeds, head, readme, prs, api('events?per_page=30'), api(f'commits?sha={head["sha"]}&per_page=30'))
    feeds['inprogress.json'] = {'items': progress_items(readme, open_prs)}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, body in feeds.items():
            (root / name).write_text(json.dumps(body))
        publish(snapshot(root), 'shinycake/quill-dashboard')


if __name__ == '__main__':
    main()
