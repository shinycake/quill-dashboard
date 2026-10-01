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
