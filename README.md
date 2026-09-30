# Quill parity dashboard

Static HTML, CSS, inline SVG, and JavaScript. Preview with `python3 -m http.server 8765`, then open http://localhost:8765. Run the logic and publisher checks with `node scripts/check.cjs`.

## Publish data without redeploying the UI

GitHub Pages serves the UI from `main`. The browser reads one atomic `data.json` from `codex/dashboard-data`, which is independent of the Pages source branch. Polling pauses in hidden tabs, resumes immediately when visible, times out after 12 seconds, and preserves the last valid snapshot on failure. A 30-second cache-busting bucket avoids a cached raw-GitHub snapshot; the browser makes no authenticated API calls. Source timestamps and overdue heartbeats remain visible even if refresh requests succeed.

On the build machine, keep the existing feed generation in `quill-loops-publish`. **Replace its dashboard commit/push/deploy step** with:

```sh
python3 /path/to/quill-dashboard/scripts/publish-data.py /path/to/generated-feeds
```

The directory must contain `github.json`, `loops.json`, `parity-history.json`, `areas.json`, and `inprogress.json`. Generate all five before publishing; the publisher rejects inconsistent parity totals. It uses the machine's existing authenticated `gh` CLI, commits all feeds as a single snapshot, skips identical data, and refuses to overwrite a concurrent publisher. On a race or transient failure, the next scheduled run retries. Only push `main` when changing the UI. Do not point Pages at the data branch.

Validate without publishing:

```sh
python3 scripts/publish-data.py . --dry-run
```

The new data branch is created on the first successful publish. Until then, production reads the existing JSON feeds directly from `main`, keeping the dashboard compatible with the current publisher; it checks for the new branch every five minutes. Once an atomic feed has loaded, failures keep that snapshot rather than switch to older deployed files. Local previews always read local JSON.

GitHub raw hosting is eventually consistent: the poll cadence is not a guarantee of publication latency. If guaranteed subsecond delivery becomes necessary, host the same snapshot on a mutable endpoint with conditional requests; the UI does not need another deployment for each update.

## Status and estimates

Each checklist item occupies exactly one segment: complete, inferred in progress, queued, or blocked. Active work is matched conservatively to at most one unblocked pending item per work record; publishers can provide an exact `item` text to remove the keyword inference. Work whose PR closed or branch merged is excluded. Blocked-only areas display a patterned amber bar and “All blocked”; blockers never count toward completion.

The forecast fits a line to observations from the last 24 hours with the current checklist size. It requires three points spanning at least two hours. Nonpositive pace has no ETA; estimates from source observations older than 15 minutes are labeled as snapshot estimates. It shows available-work duration separately from the conditional estimate for 100%; resolving blocked work is a prerequisite for full parity. The graph range does not change the recent forecast window.

Loop heartbeat and work evidence are evaluated independently at view time. A missing/overdue heartbeat is an error; an overdue work-evidence timestamp is an attention state, even when the publisher reports the loop as active. Paused, parked, blocked, and all known phase names remain distinct. Expand work details and blocker lists inside each card.

Publisher protocol: [GitHub Git trees](https://docs.github.com/en/rest/git/trees), [commits](https://docs.github.com/en/rest/git/commits), and [references](https://docs.github.com/en/rest/git/refs).
