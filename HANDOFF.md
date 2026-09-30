# Build-machine publishing handoff

Update Quill's dashboard publishing job so routine data refreshes no longer trigger a GitHub Pages deployment. Complete the running-job integration and verify it in production.

Repository: https://github.com/shinycake/quill-dashboard

Implementation branch: [`codex/dashboard-cleanup`](https://github.com/shinycake/quill-dashboard/tree/codex/dashboard-cleanup)

Production dashboard: https://shinycake.github.io/quill-dashboard/

This implementation branch contains the updated `index.html`, `scripts/publish-data.py`, `scripts/check.cjs`, `README.md`, and this handoff. The UI was checked locally at widths from 320px to 1920px, including long checklist modals, blocked-only and near-complete bars, keyboard navigation, reduced motion, and offline recovery. The publisher was tested with mocked GitHub writes and a real local dry run. These checks do not prove that the running build-machine job has been switched or that the production UI has been deployed.

## Obtain the implementation

Fetch the branch into the dashboard repository:

```sh
git fetch origin codex/dashboard-cleanup
```

Use an isolated checkout/worktree to inspect and test it. Do not switch or reset a checkout while the existing publishing job is using it. The JSON files in this branch are historical development fixtures; do not republish them as current build-machine data.

## Inspect the existing job

The publisher is referenced as `~/workspace/bin/quill-loops-publish`. Locate and inspect that script, its helpers, and its scheduler. The existing setup appears to regenerate dashboard JSON files and push them to `main` approximately every two minutes, triggering recurring Pages builds. Confirm the actual behavior. Find every job that can push generated dashboard data to `main`, including explicit deployment commands.

GitHub Pages was verified to serve the root of `main`. Keep that configuration.

## Target architecture

- `main` contains the deployed dashboard UI.
- Routine snapshots go to the separate branch `codex/dashboard-data`.
- That branch contains one atomic `data.json` with `generated_at` and a `feeds` object containing all five feeds.
- The updated browser reads `https://raw.githubusercontent.com/shinycake/quill-dashboard/codex/dashboard-data/data.json` and polls while visible.
- Data publication must not move `main` or trigger a Pages deployment.
- UI changes are published separately, when the UI changes.

**The implementation branch and data branch are different:** `codex/dashboard-cleanup` is code to integrate; `codex/dashboard-data` is the publisher's runtime output. Do not deploy Pages from either branch.

## Integrate the publisher

Reuse `scripts/publish-data.py` from the implementation branch. It uses Python's standard library and the build machine's existing authenticated `gh` CLI. Determine the actual persistent script location and generated-feed directory, then invoke:

```sh
python3 /actual/path/to/scripts/publish-data.py /actual/generated-feed-directory
```

The input directory must contain `github.json`, `loops.json`, `parity-history.json`, `areas.json`, and `inprogress.json`.

Preserve the existing authenticated GitHub snapshot generation, loop tracking, checklist extraction, in-progress mapping, and history generation. Preserve unrelated consumers of those outputs. Generate all five successfully before publishing; use a coherent staging directory if necessary. The script rejects inconsistent area/GitHub parity totals.

Replace the routine dashboard commit/push/deploy step with this invocation. Ensure no duplicate scheduled job continues the old deployment path. Install the script where it survives later deployments and job executions; do not depend on a temporary worktree that will be removed.

The publisher creates the data branch on its first successful publication, skips identical feed contents, and atomically advances the branch after assembling the complete snapshot. It refuses non-fast-forward updates rather than overwrite a concurrent publisher. Generation/publication failures must preserve the last published snapshot, surface through existing logs, and retry on the next scheduled run. Do not suppress errors, force-push around failures, or stamp stale work as newly active. Publication time and loop work-evidence time are distinct.

Keep credentials on the build machine. Never put tokens into HTML, public JSON, logs, or the data branch.

## Deploy the UI once

Integrate the code changes from `codex/dashboard-cleanup` into current `main` through the normal repository process. Preserve newer generated data and other unrelated changes on `main`; do not reset it to this branch's old base. Publish the updated UI once and leave Pages serving `main` at `/`.

Until the data branch is available, the updated UI has a compatibility fallback to individual raw JSON files on `main` and checks for the data branch every five minutes. Once the combined feed succeeds, errors retain the last good snapshot rather than downgrade to older files. A working fallback is not evidence that the new publisher is connected. Raw GitHub hosting can be eventually consistent; the polling interval is not a guaranteed publication latency.

## Verify end to end

1. Run `node scripts/check.cjs` from the implementation checkout. Its GitHub writes are mocked; it does not publish.
2. Run `python3 scripts/publish-data.py /actual/generated-feed-directory --dry-run`.
3. Publish freshly generated build-machine data and verify `codex/dashboard-data/data.json` contains all five feeds, a truthful publication timestamp, and consistent parity totals.
4. Verify production loads the combined feed successfully, rather than only using the fallback. Check the actual request URL and response and compare the displayed snapshot timestamp/counts.
5. Observe at least two scheduled publication cycles. Meaningful data changes should reach the dashboard while `main` remains unchanged and no new Pages deployments are created by those publications.
6. Verify identical input skips publication and a failed publication preserves the last good snapshot.
7. Verify heartbeat/evidence timestamps, overdue warnings, and blocked counts remain truthful.

Report the changed job and scheduler, actual publisher command and feed directory, one-time UI deployment commit, a successful data publication commit, evidence that scheduled data publications did not trigger Pages deployments, and any remaining blocker.

The task is complete when the running build-machine job publishes data independently of UI deployments and production consumes that feed—not merely when the replacement script exists.
