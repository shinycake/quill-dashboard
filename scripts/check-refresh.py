import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('refresh', Path(__file__).with_name('refresh-data.py'))
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)
feeds = {'loops.json': {'loops': [{'updated_at': 'old', 'last_evidence_at': 'older'}]},
         'inprogress.json': {'items': [{'pr': 1}, {'pr': 2}]}, 'parity-history.json': {'points': []}}
main = {'sha': 'abcdef1234', 'commit': {'committer': {'date': '2026-10-01T00:00:00Z'}}}
readme = '### Test\n- [x] Complete <!-- parity:done -->\n- [ ] Pending <!-- parity:pending -->\n- [ ] Blocked: no API <!-- parity:blocked -->\n'
prs = [{'number': 1, 'state': 'closed', 'merged_at': '2026-10-01T00:00:00Z'}, {'number': 2, 'state': 'open'}]
refresh.refresh(feeds, main, readme, prs, [], [])
assert feeds['github.json']['parity'] == {'done': 1, 'total': 3}
assert feeds['areas.json']['areas'][0]['pending'][1]['blocked']
assert feeds['inprogress.json']['items'] == [{'pr': 2}]
assert feeds['loops.json']['loops'][0] == {'updated_at': 'old', 'last_evidence_at': 'older'}
refresh.refresh(feeds, main, readme, prs, [], [])
assert len(feeds['parity-history.json']['points']) == 1
print('Dashboard refresh checks passed')

# GitHub Contents returns no base64 body for files above 1 MB. The publisher reads raw JSON.
import json
import subprocess
publisher = refresh._publisher
calls = []
def large_feed(args, **kwargs):
    calls.append(args)
    if '/git/ref/' in args[2]:
        data = {'object': {'sha': 'parent'}}
    elif '-H' in args:
        assert args[-1] == 'Accept: application/vnd.github.raw+json'
        data = {'feeds': feeds}
    else:
        data = {'encoding': 'none', 'content': ''}
    return subprocess.CompletedProcess(args, 0, json.dumps(data), '')
original = subprocess.run
try:
    subprocess.run = large_feed
    publisher['publish']({'feeds': feeds}, 'example/repo')
    assert len(calls) == 3
finally:
    subprocess.run = original

# Match active work to exact unchecked fragment IDs, never to title keywords.
import base64
pr = {'number': 3, 'title': 'Feature', 'html_url': 'https://github.com/shinycake/quill/pull/3', 'head': {'sha': 'head', 'ref': 'codex/test'}}
def fragments(path):
    if path.startswith('pulls/'):
        return [{'filename': 'parity-fragments/test.txt', 'status': 'added'},
                {'filename': 'parity-fragments/old.txt', 'status': 'removed'}]
    assert 'ref=head' in path
    return {'content': base64.b64encode(b'parity:pending\nparity:done\n# comment').decode()}
refresh.api = fragments
items = refresh.progress_items(readme, [pr])
assert len(items) == 1 and items[0]['item'] == 'Pending' and items[0]['area'] == 'Test'
assert refresh.progress_items(readme, []) == []
