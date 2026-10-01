# Make repository events drive dashboard updates

Implementation branch: `codex/repo-driven-dashboard` in `shinycake/quill-dashboard`.

The current production snapshot correctly reports Quill main at 490/525, but the dashboard workflow only has scheduled/manual triggers. Scheduled runs have occurred hours apart despite a five-minute cron. The current projection also requires an existing snapshot and can fail the entire refresh when an optional PR fragment disappears.

This branch provides the replacement using the existing projector and publisher:

- `.github/workflows/project-data.yml`: reusable workflow running in the Quill caller's context with its built-in token.
- `templates/quill-dashboard-data.yml`: the exact source-repository caller to install.
- `scripts/refresh-data.py`: supports publishing in Quill's own data branch, bootstraps without existing data, paginates open PRs/files, isolates optional PR-fragment failures, and records the observed main SHA.
- `index.html`: prefers Quill's snapshot, keeps the previous valid snapshot on failure, rejects older snapshots, and does not let malformed optional feeds freeze parity. Localhost uses live data too; use `?data=local` explicitly for fixtures.

## Required changes by the Quill implementing agent

1. Fetch `codex/repo-driven-dashboard` from `shinycake/quill-dashboard`. Run `node scripts/check.cjs` and `PYTHONDONTWRITEBYTECODE=1 python3 scripts/check-refresh.py`.
2. Merge/deploy these dashboard changes once. Do not replace current data or reset main to an old commit.
3. Copy `templates/quill-dashboard-data.yml` into `shinycake/quill/.github/workflows/dashboard-data.yml`. Replace BOTH `DASHBOARD_COMMIT_SHA` placeholders with the full commit SHA of this dashboard implementation. The reusable workflow and its checked-out scripts must use the same pinned revision.
4. Install that caller on Quill main. It responds to branch pushes, PR changes, and completion of `ci`, `quill-worker`, and `quill-publisher`; an offset 15-minute schedule is recovery only. Exclude `codex/dashboard-data` from push triggers. Keep its concurrency group and `cancel-in-progress: false` so overlapping events reconcile current state without concurrent writes.
5. Run the caller manually once. It publishes `shinycake/quill` branch `codex/dashboard-data` with the normal Quill `GITHUB_TOKEN`; no cross-repository token or new service is needed. The first run optionally imports parity history from the old dashboard feed, but old VM coordinator claims are not imported.
6. Verify production reads `https://raw.githubusercontent.com/shinycake/quill/codex/dashboard-data/data.json`; the UI must show the observed main SHA and repo observation time. A legacy-feed banner means migration is incomplete.
7. Once verified, disable the old dashboard-repo scheduled publisher and any VM publisher of GitHub projection data. Keep one authoritative writer for the new Quill data branch. Optional coordinator reports must not overwrite or gate repo-derived parity/PR state.
8. GitHub suppresses many events created with `GITHUB_TOKEN`. The caller includes workflow-completion triggers for the existing worker/publisher. If another automation mutates main or PRs using that token, explicitly dispatch `dashboard-data.yml` after a confirmed mutation or include that automation's workflow name in `workflow_run`. Do not assume its push/PR event will fire.
9. Do not execute PR code or check out PR heads in the privileged projection workflow. It only checks out pinned dashboard scripts and reads GitHub APIs, including PR fragment text. Retain this boundary when modifying the caller.

## Acceptance

- Open/update/close a PR and merge a real change through the normal process. The event workflow must observe current GitHub state and update the source data branch without waiting for cron.
- The observed main SHA must match Quill main; a PR merge must remove that PR from active work. Zero open PRs must show an empty queue rather than retain old claims.
- Bootstrap must work when the source data branch does not exist. Optional missing history, coordinator records, or an unavailable PR fragment must not freeze core parity and PR updates.
- An offline/invalid/older response keeps the last valid snapshot and displays a clear warning. Browser fetch time is never represented as repository observation time or coordinator evidence.
- Subsequent data publications must not move dashboard main or trigger UI redeployments.
- Report both integration commits, one event-driven run, its published source SHA/counts, and any remaining blocker. Do not call the migration complete after merely copying the template.

GitHub documents that scheduled runs can be delayed/dropped and that built-in token permissions are scoped to the workflow's repository:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
https://docs.github.com/en/actions/concepts/security/github_token
