# build-and-sync

Use when the user asks to deploy or run the deployment pipeline.

1. Read `deploy.json` and select the target.
2. Validate the selected target configuration for the provider.
3. Complete the provider authentication or authorization preflight before any build, tag push, image creation, or image sync side effect.
4. If `confirmBeforeStart` is `true`, ask before starting the build.
5. Start the current target build through the provider.
6. Correlate all logs, images, and terminal status to the build just triggered. Do not reuse an older successful image for `部署`.
7. Wait for the build to reach a terminal state.
8. Extract the produced image only after build success.
9. If `syncImage` is true, validate the image against `imagePattern`, optionally ask when `confirmBeforeSyncImage` is true, then sync through the provider.
10. Wait for sync completion when the provider supports sync status.
11. If `deploy.json` was created or modified during this workflow, commit and push only that file after deployment success.
12. Report success or failure.

If the provider supports build but not image sync, stop after build success and report the produced image plus the missing sync capability.

If the current build reaches a terminal failure state, stop immediately. Do not keep polling, do not extract images, do not look for an older successful image, and do not start image sync. Report the failed phase, terminal state, a concise sanitized failure snippet when available, and the provider URL where the user can inspect the failed build.
