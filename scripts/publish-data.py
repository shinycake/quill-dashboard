#!/usr/bin/env python3
"""Publish dashboard snapshots to a data-only branch using the existing gh login."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

FEEDS = ('github.json', 'loops.json', 'parity-history.json', 'areas.json', 'inprogress.json')
BRANCH = 'codex/dashboard-data'


def require(condition, message='Invalid snapshot structure'):
    if not condition:
        raise ValueError(message)


def snapshot(directory):
    feeds = {name: json.loads((directory / name).read_text()) for name in FEEDS}
    areas = feeds['areas.json']['areas']
    require(isinstance(areas, list) and bool(areas), 'Areas must be a nonempty list')
    for area in areas:
        require(isinstance(area['name'], str) and isinstance(area['done'], list) and isinstance(area['pending'], list))
        require(all(isinstance(item, str) for item in area['done']))
        require(all(isinstance(item, str) or isinstance(item, dict) and isinstance(item.get('text'), str) for item in area['pending']))
    parity = feeds['github.json']['parity']
    require(all(type(parity[k]) is int and parity[k] >= 0 for k in ('done', 'total')))
    require(sum(len(a['done']) for a in areas) == parity['done'], 'Area and GitHub done counts disagree; regenerate before publishing')
    require(sum(len(a['done']) + len(a['pending']) for a in areas) == parity['total'], 'Area and GitHub totals disagree; regenerate before publishing')
    for key in ('closedPRs', 'openPRs', 'events', 'commits'):
        require(isinstance(feeds['github.json'][key], list), f'{key} must be a list')
    for file, key in (('loops.json', 'loops'), ('parity-history.json', 'points'), ('inprogress.json', 'items')):
        require(isinstance(feeds[file][key], list), f'{file}: {key} must be a list')
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'feeds': feeds}


def publish(data, repository):
    endpoint = f'repos/{repository}'

    def api(path, method='GET', payload=None, allow_missing=False):
        args = ['gh', 'api', f'{endpoint}/{path}', '--method', method]
        if payload is not None:
            args += ['--input', '-']
        result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                                text=True, capture_output=True, timeout=60)
        if result.returncode:
            if allow_missing and 'HTTP 404' in result.stderr:
                return None
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout)

    ref = api(f'git/ref/heads/{BRANCH}', allow_missing=True)
    parent = ref['object']['sha'] if ref else None
    # Compare the Git tree before creating a commit; unchanged data needs no write.
    if parent:
        previous = api(f'contents/data.json?ref={BRANCH}')
        old = json.loads(base64.b64decode(previous['content']))
        if old.get('feeds') == data['feeds']:
            print('No data changes; skipped publish')
            return
    tree = api('git/trees', 'POST', {'tree': [{'path': 'data.json', 'mode': '100644', 'type': 'blob',
                                            'content': json.dumps(data, separators=(',', ':'), ensure_ascii=False)}]})
    commit = api('git/commits', 'POST', {'message': 'Update live dashboard snapshot',
                                     'tree': tree['sha'], 'parents': [parent] if parent else []})
    if parent:
        # Non-fast-forward updates fail rather than overwrite a concurrent publisher.
        api(f'git/refs/heads/{BRANCH}', 'PATCH', {'sha': commit['sha'], 'force': False})
    else:
        api('git/refs', 'POST', {'ref': f'refs/heads/{BRANCH}', 'sha': commit['sha']})
    print(f'Published {commit["sha"][:8]} to {BRANCH}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Directory containing the five generated JSON feeds')
    parser.add_argument('--repo', default='shinycake/quill-dashboard')
    parser.add_argument('--dry-run', action='store_true', help='Validate and assemble without writing to GitHub')
    args = parser.parse_args()
    try:
        data = snapshot(args.directory)
        if args.dry_run:
            print(f'Valid snapshot: {len(data["feeds"]["areas.json"]["areas"])} areas, {len(data["feeds"]["loops.json"]["loops"])} loops')
        else:
            publish(data, args.repo)
    except (KeyError, TypeError, ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f'Publish failed; previous snapshot preserved: {error}\n')


if __name__ == '__main__':
    main()
