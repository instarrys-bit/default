# Read-only operations dashboard

- Public static site hosted by GitHub Pages.
- Dashboard content is aggregated from committed repository records; raw domains, source URLs, task payloads, run logs, credentials, and secrets are not published.
- The dashboard has no production, workflow-dispatch, configuration-edit, queue-edit, or deployment-control UI.
- The dashboard workflow has `contents: read` in its build job and only `pages: write` + `id-token: write` in the deployment job. It does not receive `contents: write` and does not call production workflows.
- Snapshot generation is read-only and writes only the temporary Pages artifact in the runner workspace.
- Metrics are explicitly limited to fields present in current committed state. Missing historical events are displayed as unavailable, never inferred.
- Public site URL: https://instarrys-bit.github.io/default/


## Freshness model

- Data rebuild is event-driven on completion of the deterministic production audit and Watchdog workflows, and on commits to the monitored data files.
- An hourly schedule is a fallback in case an event is missed.
- An open page polls the latest published snapshot every 30 seconds; this does not trigger production or mutate repository data.
- End-to-end freshness is bounded by GitHub Actions queue time and Pages deployment time, so this is near-real-time rather than a guaranteed sub-second live stream.
