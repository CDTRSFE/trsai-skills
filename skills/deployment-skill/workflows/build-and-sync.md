# build-and-sync

Use when the user asks to deploy or run the deployment pipeline.

1. Read `deploy.json` and select the target.
2. Validate the selected target configuration for the provider.
3. Complete the provider authentication or authorization preflight before any build, tag push, image creation, or image sync side effect.
4. For `部署` flows that build a new image, prepare a traceable deployment tag before starting the provider build. Verify runtime tag output capability; if the project lacks it, ask for confirmation, add the smallest project-consistent code, commit it, and push the current branch before tag creation.
5. Run `git-tag-release` preview with the selected `target`, show the computed tag and side effects, and execute only after confirmation. Use `editPkg=true` and push the current branch as part of the release flow so the build can read the final `package.json#tag`.
6. If `confirmBeforeStart` is `true`, ask before starting the build.
7. Start the current target build through the provider. In Jenkins `git-tag` mode, the build side effect is the pushed Git tag, not a direct Jenkins `/build` request. In Apollo mode, start the Apollo pipeline only after the deployment tag commit and tag have been pushed.
8. Correlate all logs, images, and terminal status to the build just triggered. Do not reuse an older successful image for `部署`.
9. Wait for the build to reach a terminal state.
10. Extract the produced image only after build success.
11. If `syncImage` is true, validate the image against `imagePattern`, optionally ask when `confirmBeforeSyncImage` is true, then sync through the provider.
12. Wait for sync completion when the provider supports sync status.
13. If `deploy.json` was created or modified during this workflow, commit and push only that file after deployment success.
14. Report success or failure, including the deployment tag, commit, image, and provider build URL when available.

If the provider supports build but not image sync, stop after build success and report the produced image plus the missing sync capability.

If the current build reaches a terminal failure state, stop immediately. Do not keep polling, do not extract images, do not look for an older successful image, and do not start image sync. Report the failed phase, terminal state, a concise sanitized failure snippet when available, and the provider URL where the user can inspect the failed build.
