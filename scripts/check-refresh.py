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
def fragments(path, **kwargs):
    if path.startswith('pulls/'):
        return [{'filename': 'parity-fragments/test.txt', 'status': 'added'},
                {'filename': 'parity-fragments/old.txt', 'status': 'removed'}]
    assert 'ref=head' in path
    return {'content': base64.b64encode(b'parity:pending\nparity:done\n# comment').decode()}
refresh.api = fragments
items = refresh.progress_items(readme.replace("<!-- parity:pending -->", "<!-- parity:pending --> (partial)"), [pr])
assert len(items) == 1 and items[0]['item'] == 'Pending (partial)' and items[0]['area'] == 'Test'
assert refresh.progress_items(readme, []) == []

# A missing/malformed optional snapshot must not prevent first publication.
assert refresh.initial_feeds()['loops.json'] == {'loops': []}
assert refresh.initial_feeds({'feeds': {'loops.json': None, 'parity-history.json': {'points': [{'t': 'bad', 'done': 0, 'total': 1}]}}})['parity-history.json']['points'] == []
assert feeds['github.json']['main_sha'] == main['sha']

# Explicit partial-work markers require a real unchecked ID; duplicate fragment
# mappings collapse, and completed/unknown IDs never create active work.
pr['body'] = '<!-- parity-work:pending --> <!-- parity-work:blocked --> <!-- parity-work:done --> <!-- parity-work:unknown -->'
items = refresh.progress_items(readme, [pr])
assert {item['item'] for item in items} == {'Pending', 'Blocked: no API'}
assert len(items) == 2
assert feeds['github.json']['parity'] == {'done': 1, 'total': 3}
pr['body'] = None
assert len(refresh.progress_items(readme, [pr])) == 1
print('Partial parity work is visible without changing completion counts')

# History stays deduped and ordered; raw done/total are preserved per point.
dup = refresh.initial_feeds({'feeds': {'parity-history.json': {'points': [
    {'t': '2026-10-02T00:00:00Z', 'sha': 'b', 'done': 6, 'total': 10},
    {'t': '2026-10-01T00:00:00Z', 'sha': 'a', 'done': 5, 'total': 10},
    {'t': '2026-10-01T00:00:00+00:00', 'sha': 'a2', 'done': 5, 'total': 10},   # same instant, other spelling
    {'t': '2026-10-03T00:00:00Z', 'sha': 'b', 'done': 6, 'total': 10},        # same commit seen twice
    {'t': '2026-10-04T00:00:00Z', 'sha': 'z', 'done': 0, 'total': 0},         # empty checklist is never a real point
    {'t': '2026-10-05T00:00:00Z', 'sha': 'y', 'done': 11, 'total': 10}]}}})   # done above total
assert [p['sha'] for p in dup['parity-history.json']['points']] == ['a2', 'b'], dup['parity-history.json']['points']
assert dup['parity-history.json']['points'][1]['t'] == '2026-10-03T00:00:00Z'

# A README that parses to nothing, or collapses against the last good point, must not write a point.
def attempt(text, history):
    f = {'loops.json': {'loops': []}, 'inprogress.json': {'items': []}, 'parity-history.json': {'points': list(history)}}
    try:
        refresh.refresh(f, main, text, [], [], [])
    except ValueError:
        return f, True
    return f, False
good = [{'t': '2026-09-30T00:00:00Z', 'sha': 'old', 'done': 80, 'total': 100}]
for bad in ('', '# Quill\nno checklist here\n', '### Area\n- [ ] not a checkbox line\n', '### Area\n- [x] one\n- [ ] two\n'):
    f, refused = attempt(bad, good)
    assert refused and f['parity-history.json']['points'] == good and 'github.json' not in f, repr(bad)
ok = '### A\n' + '- [x] done\n' * 85 + '- [ ] todo\n' * 15
f, refused = attempt(ok, good)
assert not refused and f['parity-history.json']['points'][-1] == {'t': '2026-10-01T00:00:00Z', 'sha': 'abcdef1', 'done': 85, 'total': 100}
# Growth of the checklist is normal (scope was added); the raw total is kept for tooltips.
bigger = '### A\n' + '- [x] done\n' * 90 + '- [ ] todo\n' * 160
f, refused = attempt(bigger, good)
assert not refused and f['parity-history.json']['points'][-1]['total'] == 250

# Losing a publish race re-reads and retries; any other failure is raised immediately.
import sys
calls = []
def flaky(args):
    calls.append(1)
    if len(calls) < 3:
        raise RuntimeError('HTTP 422: Update is not a fast forward')
refresh.observe = flaky
refresh.time.sleep = lambda s: None
sys.argv = ['refresh-data.py']
refresh.main()
assert len(calls) == 3
def broken(args):
    raise RuntimeError('HTTP 500: server error')
refresh.observe = broken
try:
    refresh.main()
    raise AssertionError('non-race failure was swallowed')
except RuntimeError:
    pass
print('History dedupe, malformed-README guard, and publish retry checks passed')
