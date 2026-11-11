# Read-only operations dashboard

- Public static site hosted by GitHub Pages.
- Dashboard content is aggregated from committed repository records; raw domains, source URLs, task payloads, run logs, credentials, and secrets are not published.
- The dashboard has no production, workflow-dispatch, configuration-edit, queue-edit, or deployment-control UI.
- The dashboard workflow has `contents: read` in its build job and only `pages: write` + `id-token: write` in the deployment job. It does not receive `contents: write` and does not call production workflows.
- Snapshot generation is read-only and writes only the temporary Pages artifact in the runner workspace.
- Metrics are explicitly limited to fields present in current committed state. Missing historical events are displayed as unavailable, never inferred.
- Public site URL: https://instarrys-bit.github.io/default/


## Freshness model

- Every commit pushed to `main` automatically triggers a new dashboard snapshot build and GitHub Pages deployment. There is no path allowlist, so newly added producer data files cannot silently miss the trigger.
- Completion events from the listed production workflows also trigger a rebuild, including runs that finish without a new repository commit.
- A five-minute scheduled run is retained only as a fallback for missed events; it is not the primary update mechanism.
- An open page fetches the latest published snapshot every 5 seconds, bypassing browser cache, and displays the snapshot's actual generation timestamp.
- New data becomes visible after the GitHub Actions build and Pages deployment complete. GitHub Pages is static hosting, so this is event-driven near-real-time, not a guaranteed sub-second push stream.
- The dashboard remains read-only. It does not edit `modules/uu.conf`, rulesets, queues, or production controls.
