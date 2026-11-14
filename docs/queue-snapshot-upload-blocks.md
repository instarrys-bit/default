# Exact upload blocks for durable queue snapshot (Issue #421)

Insert the following two blocks immediately after each of the two
"Export durable queue snapshot ..." steps in `.github/workflows/automation-watchdog.yml`.

## Block 1 (health-check path) — name ends with `-health`

```yaml
      - name: Upload durable queue snapshot artifact (recovery insurance)
        if: always()
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4
        with:
          name: durable-queue-snapshot-${{ github.run_id }}-health
          path: ${{ runner.temp }}/task_queue.json
          retention-days: 30
          if-no-files-found: ignore
```

## Block 2 (supervision path) — name ends with `-supervision`

```yaml
      - name: Upload durable queue snapshot artifact (supervision)
        if: always()
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4
        with:
          name: durable-queue-snapshot-${{ github.run_id }}-supervision
          path: ${{ runner.temp }}/task_queue.json
          retention-days: 30
          if-no-files-found: ignore
```

Both use the existing pinned upload-artifact SHA already present in the repository.
`if: always()` ensures the artifact is retained even when later steps fail.

After insertion, the recovery half of the closed loop is complete.
