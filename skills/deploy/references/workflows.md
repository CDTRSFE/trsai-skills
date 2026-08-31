# Deployment Workflows

## build-and-sync

Use when the user asks to deploy or run the deployment pipeline.

1. Read `deploy.json` and select the target.
2. Validate the selected target configuration for the provider.
3. If `confirmBeforeStart` is `true`, ask before starting the build.
4. Start the current target build through the provider.
5. Correlate all logs, images, and terminal status to the build just triggered. Do not reuse an older successful image for `部署`.
6. Wait for the build to reach a terminal state.
7. Extract the produced image only after build success.
8. If `syncImage` is true, validate the image against `imagePattern`, optionally ask when `confirmBeforeSyncImage` is true, then sync through the provider.
9. Wait for sync completion when the provider supports sync status.
10. If `deploy.json` was created or modified during this workflow, commit and push only that file after deployment success.
11. Report success or failure.

If the provider supports build but not image sync, stop after build success and report the produced image plus the missing sync capability.

If the current build reaches a terminal failure state, stop immediately. Do not keep polling, do not extract images, do not look for an older successful image, and do not start image sync. Report the failed phase, terminal state, a concise sanitized failure snippet when available, and the provider URL where the user can inspect the failed build.

## sync-image-only

Use when the user asks to update, change, or sync an image without building.

1. Read `deploy.json` and select the target.
2. Use the provided image, or ask the provider for the latest successful image when no image was provided.
3. Validate the image against `imagePattern`; reject mismatches unless the user explicitly confirms.
4. If `confirmBeforeSyncImage` is `true`, ask before mutating the deployment.
5. Call the provider image-sync mechanism.
6. Wait for sync completion when available.
7. If `deploy.json` was created or modified during this workflow, commit and push only that file after update success.
8. Report the previous image and new image when the provider exposes both.

If the provider has no image-sync capability, stop and explain that this project can build through the provider but has no configured sync mechanism.

If image sync reaches a terminal failure state, stop immediately. Do not retry indefinitely and do not silently switch to UI fallback. Report the failed phase, terminal state, a concise sanitized failure snippet when available, and the provider URL where the user can inspect or repair the failed deployment.

## discover-config

Use when `deploy.json` is missing, the selected target is absent, or required provider fields are incomplete.

1. Determine the selected target first.
2. Ask only for missing values that cannot be safely discovered.
3. Before writing provider configuration, complete any provider authentication or authorization preflight that is possible with the discovered user-supplied locator, such as Jenkins `<jobUrl>/api/json`.
4. Prefer provider APIs or CLIs to discover stable IDs, job names, application names, and image prefixes.
5. Write back only the selected target configuration after the provider preflight succeeds.
6. Re-read `deploy.json` after writing it before continuing.

Do not infer a production deployment target from repository names or fuzzy UI text. Production configuration must be explicit enough to avoid mutating the wrong system.

## deploy.json Git Follow-Up

Use only after a deployment or image update has succeeded. Never commit `deploy.json` after a failed or ambiguous deployment state.

1. Check whether project-root `deploy.json` is new or changed.
2. If there is no `deploy.json` change, skip the Git follow-up silently unless reporting it would clarify a user-visible configuration action.
3. Stage only `deploy.json`.
4. Commit with a concise message such as `chore(deploy): update deploy config`.
5. Push the current branch to its upstream. If there is no upstream but a single obvious remote such as `origin` exists, push the current branch to that remote and set upstream only when that matches the project's normal Git workflow.
6. Include the commit hash and remote branch in the success report.

If the working tree contains unrelated changes, leave them untouched. If `deploy.json` already had user edits before the workflow and the deployment workflow adds more changes to the same file, commit the resulting `deploy.json` only when the combined file content is the intended deployment configuration; otherwise stop and ask before committing.
