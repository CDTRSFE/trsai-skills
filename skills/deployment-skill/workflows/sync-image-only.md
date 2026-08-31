# sync-image-only

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
