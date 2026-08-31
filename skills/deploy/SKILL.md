---
name: deploy
description: Use when the user asks to deploy, build, run a deployment pipeline, update or sync an image, deploy production, or add deployment configuration for projects using deploy.json with providers such as apollo or jenkins.
metadata:
  short-description: Route project deployments through provider-specific adapters
---

# Deploy

Use this skill as the common deployment entrypoint for project-root `deploy.json` workflows. It separates user intent, shared deployment workflows, configuration shape, and provider-specific behavior.

When the user writes in Chinese, all user-facing progress updates, questions, and final reports must be in Chinese. Keep API paths, field names, image tags, branch names, commit hashes, and status constants such as `SUCCESS` in their original form.

## Routing

Read only `deploy.json` from the project root for deployment configuration. Do not infer deployment configuration from `package.json`.

When the user only says `部署`, `发布`, `build`, or another generic deployment request and `deploy.json` is missing or has no `provider`, ask which provider to use before asking provider-specific setup questions:

```text
当前项目还没有明确部署方式。

请确认这次走哪种部署：
1. Apollo 部署
2. Jenkins 部署

确认后我再按对应方式补齐配置并继续。
```

Do not ask for an Apollo pipeline name before the user has selected Apollo. Do not ask for Jenkins job/tag fields before the user has selected Jenkins.

Select the target environment before reading environment-specific configuration:

- `dev` means development / `开发环境`.
- `prod` means production / `生产环境`.
- If the user says `部署生产`, `生产部署`, `prod`, or otherwise clearly asks for production, use `prod`.
- If the user names another environment, use that target key.
- If the user does not name an environment, use `defaultTarget`, then `dev`.
- Do not create, discover, or require unrelated target configuration while handling the selected target.

Use `provider` to choose the provider reference:

- `apollo`: read [references/providers-apollo.md](references/providers-apollo.md).
- `jenkins`: read [references/providers-jenkins.md](references/providers-jenkins.md).
- Unknown provider: stop and say the configured provider is not supported yet.

If the user selects Apollo, continue with the Apollo provider rules and the existing `apollo-deploy` skill. If the user selects Jenkins, prefer the Jenkins `git-tag` mode and collect the minimum missing information needed for the selected target. For Jenkins `git-tag` projects, one exact Jenkins job URL is usually enough to start configuration when `package.json#tagPrefix` and a Git remote already exist.

When asking for one missing Jenkins job URL, do not print a summary of inferred fields such as target, trigger, remote, tag prefix, version type, `editPkg`, or application name. Ask directly and keep example URLs clickable with Markdown links:

```text
请提供这个项目开发环境的 Jenkins Job 完整 URL，例如：[http://192.168.210.40:30080/job/cqwx-dual-grid-h5/](http://192.168.210.40:30080/job/cqwx-dual-grid-h5/)
```

When creating, updating, or validating `deploy.json`, read [references/config-schema.md](references/config-schema.md).

When executing a user action, read [references/workflows.md](references/workflows.md) and the selected provider reference.

## Action Selection

- `部署`: run `build-and-sync`.
- `部署生产`: use target `prod`, then run `build-and-sync`.
- `build`, `构建`, `运行流水线`: run the provider build flow; sync an image only when the selected target config enables it or the user asks for it.
- `更新镜像 <image>`, `变更镜像 <image>`, `sync image <image>`: run `sync-image-only` with the provided image.
- `更新镜像` with no image: run `sync-image-only` using the provider's latest successful image discovery.
- `添加环境`, `补配置`, missing or incomplete target config: run `discover-config` for only the selected target.

## Safety Boundaries

- Prefer API or CLI execution over UI clicking for deployment operations.
- Do not deploy to production or mutate external deployment state when the required target configuration is missing or ambiguous.
- Do not ask for copied browser headers as the normal path. Prefer configured credentials, tokens, API sessions, or a documented provider authentication path.
- Redact raw build/deploy logs before showing them. At minimum mask authorization headers, cookies, tokens, passwords, and `docker login ... -p <value>`.
- When `deploy.json` is created or changed by this deployment workflow and the deployment or image update succeeds, automatically commit only the `deploy.json` change and push it to the current branch's remote. Do not include unrelated files in that commit.
- If Git is unavailable, the project is not a Git repository, no upstream/remote can be determined, or the push fails, do not treat the deployment as failed. Report the deployment success and the Git follow-up problem separately.

## Reporting

Successful deployment reports should stay concise and user-facing:

```text
部署完成：<project> / <environment>

构建状态：SUCCESS
打镜像耗时：<duration>

镜像：
<full image>

<环境名称>已同步：
<previous short image> 变更为 <new short image>
```

For image-only updates:

```text
更新完成：<project> / <environment>

镜像：
<full image>

<环境名称>已同步：
<previous short image> 变更为 <new short image>
```

If the provider cannot sync images and only builds, report the build result and produced image, then clearly say no image sync was configured.

If `deploy.json` was committed and pushed after success, include the commit hash and pushed branch in the report. If the Git follow-up was skipped or failed, include the reason.

On failure, report the failed phase, terminal state, the most relevant sanitized failure snippet, and a provider URL where the user can inspect or repair the failed build/deployment.
