# discover-config

Use when `deploy.json` is missing, the selected target is absent, or required provider fields are incomplete.

1. Determine the selected target first.
2. Ask only for missing values that cannot be safely discovered.
3. Before writing provider configuration, complete any provider authentication or authorization preflight that is possible with the discovered user-supplied locator, such as Jenkins `<jobUrl>/api/json` or Apollo login/session validation.
4. Prefer provider APIs or CLIs to discover stable IDs, job names, application names, and image prefixes.
5. Write back only the selected target configuration after the provider preflight succeeds.
6. Re-read `deploy.json` after writing it before continuing.

Do not infer a production deployment target from repository names or fuzzy UI text. Production configuration must be explicit enough to avoid mutating the wrong system.

For TRS projects, a bare `部署`, `发布`, `build`, or `运行流水线` selects `dev`. If `deploy.json` already has `prod` but lacks `dev`, treat only `dev` as missing configuration and continue discovery for `dev`; never use the existing `prod` entry as a fallback or template unless the user explicitly asks to configure production.

## deploy.json Git Follow-Up

Use only after a deployment or image update has succeeded. Never commit `deploy.json` after a failed or ambiguous deployment state.

1. Check whether project-root `deploy.json` is new or changed.
2. If there is no `deploy.json` change, skip the Git follow-up silently unless reporting it would clarify a user-visible configuration action.
3. Stage only `deploy.json`.
4. Commit with a concise message such as `chore(deploy): update deploy config`.
5. Push the current branch to its upstream. If there is no upstream but a single obvious remote such as `origin` exists, push the current branch to that remote and set upstream only when that matches the project's normal Git workflow.
6. Include the commit hash and remote branch in the success report.

If the working tree contains unrelated changes, leave them untouched. If `deploy.json` already had user edits before the workflow and the deployment workflow adds more changes to the same file, commit the resulting `deploy.json` only when the combined file content is the intended deployment configuration; otherwise stop and ask before committing.
