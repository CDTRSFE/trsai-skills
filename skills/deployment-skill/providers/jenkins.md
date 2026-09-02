# Jenkins Provider

Use this provider when `deploy.json` has `"provider": "jenkins"`.

Jenkins capability profile depends on the selected target config:

```text
build: true
extractImage: true
syncImage: true only when a sync mechanism is configured
discoverConfig: partial
```

## Required Config

For the selected target, require one of:

- `jobUrl`: full Jenkins job URL.
- `jobName` plus top-level `jenkinsUrl`.

For Jenkins deployments in TRS-style projects, default to `trigger: "git-tag"` unless `deploy.json` explicitly says `trigger: "jenkins-build"` for the selected target or the user says Jenkins should be started directly. Do not rediscover or re-explain the trigger mode for every deployment when `trigger` is omitted; omission means the team default, `git-tag`. In this mode, the required user-supplied deployment address is usually just the exact Jenkins job URL.

Recommended fields:

- `trigger`: `jenkins-build` for direct Jenkins trigger, or `git-tag` when pushing a Git tag automatically starts Jenkins.
- `buildWithParameters`: `true` when the job should be triggered through `/buildWithParameters`; otherwise use `/build`.
- `buildParams`: object of build parameters.
- `imagePattern`: accepted image prefix for extraction and validation.
- `syncImage`: `false` unless this Jenkins job or another configured mechanism safely deploys the image.

Authentication should come from environment variables or the local private secrets file for the current OS, not `deploy.json`:

- macOS/Linux: `~/.codex/secrets/jenkins.env`
- Windows PowerShell/CMD: `%USERPROFILE%\.codex\secrets\jenkins.env`

- Basic auth with password: `JENKINS_USERNAME` + `JENKINS_PASSWORD`.
- Basic auth with API token, only when the user specifically asks to use token: `JENKINS_USERNAME` + `JENKINS_API_TOKEN`.
- Bearer auth: `JENKINS_BEARER_TOKEN`.

Credential loading priority:

1. Use credentials already present in the current process environment.
2. If they are absent, load the local secrets file for the current OS when it exists.
3. If credentials are still absent, stop before any side effect that depends on Jenkins visibility and ask the user to configure local credentials.

Before creating `deploy.json`, updating `deploy.json`, creating or pushing a Git tag, triggering Jenkins, or syncing an image, run a Jenkins authentication preflight as soon as the selected target has a `jobUrl` or resolvable `jobName`:

1. Load credentials using the priority above.
2. Call `<jobUrl>/api/json` with those credentials.
3. If the job API returns `401` or `403`, or if Jenkins requires authentication and no local credentials are configured, stop immediately. Do not create or update `deploy.json`, update `package.json`, create a commit, create a tag, push a tag, trigger a build, or report that the tag/deploy step succeeded.
4. Tell the user the exact missing/failed preflight condition and provide a single copy-pasteable local credentials setup script.
5. Continue only after credentials are configured and the same preflight succeeds.

For discovery flows, this preflight is mandatory before writing any inferred Jenkins configuration. A Jenkins job URL is not considered validated until `<jobUrl>/api/json` succeeds with the configured credentials.

For `git-tag` deployments, this preflight is mandatory even though Jenkins is triggered by Git. Pushing a tag is an external side effect that may start a build; do not defer Jenkins credential problems until after the tag has already been pushed.

Expected local secret file format:

```bash
JENKINS_USERNAME=<jenkins username>
JENKINS_PASSWORD=<jenkins password>
# or, only when the user specifically asks to use token:
JENKINS_API_TOKEN=<jenkins api token>
```

When asking the user to configure Jenkins credentials, provide copy-paste scripts. Do not split the command from a separate "file content format" block.

Default to editable-at-the-top scripts, not interactive `read` scripts. The user should only need to change the username and token/password assignment lines, then paste the matching block into their terminal. Keep the editable lines at the top and label them in nearby prose, for example: "只需要改下面前两行，然后整段复制运行。"

If the current OS cannot be reliably detected from the active workspace or tool environment, provide both the macOS/Linux script and the Windows CMD script in the same response. Do not ask the user whether they are on macOS or Windows just to choose a credentials script.

If the concrete username/password is already known from the user's explicit input, include those values directly in the scripts with shell-safe quoting so the pasted script succeeds without further editing. If the values are not known, use obvious placeholder values in the top assignment lines. Prefer password over API token.

For macOS/Linux, provide this shell script:

```bash
# 只需要改下面两行，然后整段复制到终端运行
JENKINS_USERNAME='你的 Jenkins 用户名'
JENKINS_PASSWORD='你的 Jenkins 密码'

mkdir -p "$HOME/.codex/secrets"
chmod 700 "$HOME/.codex/secrets"

cat > "$HOME/.codex/secrets/jenkins.env" <<EOF
JENKINS_USERNAME=$JENKINS_USERNAME
JENKINS_PASSWORD=$JENKINS_PASSWORD
EOF
chmod 600 "$HOME/.codex/secrets/jenkins.env"
echo "已写入 $HOME/.codex/secrets/jenkins.env"
```

For Windows CMD, provide this script:

```bat
:: 只需要改下面两行，然后整段复制到 CMD 运行
set "JENKINS_USERNAME=你的 Jenkins 用户名"
set "JENKINS_PASSWORD=你的 Jenkins 密码"

mkdir "%USERPROFILE%\.codex\secrets" 2>nul
(
  echo JENKINS_USERNAME=%JENKINS_USERNAME%
  echo JENKINS_PASSWORD=%JENKINS_PASSWORD%
) > "%USERPROFILE%\.codex\secrets\jenkins.env"

echo 已写入 %USERPROFILE%\.codex\secrets\jenkins.env
```

If the user specifically asks to use an API token, provide both the macOS/Linux and Windows CMD scripts with `JENKINS_API_TOKEN` instead of `JENKINS_PASSWORD` unless the current OS is already known.

```bash
# 只需要改下面两行，然后整段复制到终端运行
JENKINS_USERNAME='你的 Jenkins 用户名'
JENKINS_API_TOKEN='你的 Jenkins API token'

mkdir -p "$HOME/.codex/secrets"
chmod 700 "$HOME/.codex/secrets"

cat > "$HOME/.codex/secrets/jenkins.env" <<EOF
JENKINS_USERNAME=$JENKINS_USERNAME
JENKINS_API_TOKEN=$JENKINS_API_TOKEN
EOF
chmod 600 "$HOME/.codex/secrets/jenkins.env"
echo "已写入 $HOME/.codex/secrets/jenkins.env"
```

```bat
:: 只需要改下面两行，然后整段复制到 CMD 运行
set "JENKINS_USERNAME=你的 Jenkins 用户名"
set "JENKINS_API_TOKEN=你的 Jenkins API token"

mkdir "%USERPROFILE%\.codex\secrets" 2>nul
(
  echo JENKINS_USERNAME=%JENKINS_USERNAME%
  echo JENKINS_API_TOKEN=%JENKINS_API_TOKEN%
) > "%USERPROFILE%\.codex\secrets\jenkins.env"

echo 已写入 %USERPROFILE%\.codex\secrets\jenkins.env
```

If the user specifically asks for PowerShell, provide this script. Do not put it inside a project repository:

```powershell
# 只需要改下面两行，然后整段复制运行
$JENKINS_USERNAME = "你的 Jenkins 用户名"
$JENKINS_PASSWORD = "你的 Jenkins 密码"

New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\secrets"
"JENKINS_USERNAME=$JENKINS_USERNAME`nJENKINS_PASSWORD=$JENKINS_PASSWORD" | Set-Content -Encoding utf8 "$env:USERPROFILE\.codex\secrets\jenkins.env"
icacls "$env:USERPROFILE\.codex\secrets\jenkins.env" /inheritance:r /grant:r "${env:USERNAME}:(R,W)"
Write-Host "已写入 $env:USERPROFILE\.codex\secrets\jenkins.env"
```

Use an interactive prompt script only if the user specifically asks for a version that does not require editing the script text.

Do not store Jenkins credentials in project `deploy.json`, deployment logs, Git commits, final reports, or the skill itself. Team-shared credentials should be distributed out of band and placed by each user in their own local secrets file.

If Jenkins requires a crumb, fetch it from:

```text
GET <jenkinsUrl>/crumbIssuer/api/json
```

Send the returned crumb header on mutating requests.

## Trigger Modes

### git-tag

Use this mode when the team's manual process is: create a Git tag, push it to the remote, and let Jenkins automatically build from that tag.

Required selected-target fields:

- `trigger: "git-tag"`
- `remote`
- `tagPrefix`
- `versionType`
- `editPkg`
- `jobUrl` or `jobName` plus top-level `jenkinsUrl`

Defaults and inference:

- `dev` means `开发环境`; `prod` means `生产环境`.
- `remote`: use `origin` when it exists and the target does not configure another remote.
- `versionType`: default to `patch` unless the user asks for `major`, `minor`, or `RC`.
- `editPkg`: default to `true`.
- `tagPrefix`: infer from `package.json#tagPrefix`. For `dev`, prefer the prefix containing `dev`; for `prod`, prefer the prefix containing `prod`. If exactly one matching prefix exists, use it without asking. If multiple match or none match, ask the user to choose.
- Existing tags are handled by `git-tag-release`; do not manually calculate the next tag. Let the script fetch tags and iterate from the latest matching version for the chosen prefix.
- `imagePattern`: use when configured. If it is missing, first try to infer the produced project image from the correlated successful build log; ask only when no confident single project image can be identified.

Use the `git-tag-release` skill for tag creation. Always preview first, show the final tag and actions to the user, and execute only after the user confirms. Do not hand-write the tag calculation or push sequence.

After the tag push succeeds:

1. Record the pushed tag name and push completion time.
2. Poll the Jenkins job through API, not UI clicks.
3. Find the build triggered by that tag. Prefer build causes, parameters, environment metadata, SCM ref text, or console text containing the exact tag. Use build timestamp only as a secondary signal.
4. Once the correlated build number is known, poll `<jobUrl>/<buildNumber>/api/json`.
5. Read `<jobUrl>/<buildNumber>/consoleText` only for that correlated build.
6. Extract the image only after the correlated build result is `SUCCESS`.

Polling is the normal monitoring mechanism after pushing the tag. Poll Jenkins APIs, not pages: check the job/build JSON for status and use `consoleText` for image extraction. Use sparse user-facing progress updates rather than reporting every poll.

If Jenkins authentication is required, use configured Jenkins credentials from environment variables or the current OS local secrets file. If these are absent, stop and ask the user to configure credentials; do not click through Jenkins UI as a workaround.

### jenkins-build

Use this mode when Codex should trigger Jenkins directly through Jenkins HTTP endpoints. Because TRS Jenkins deployments default to `git-tag`, use this mode only when the selected target explicitly sets `trigger: "jenkins-build"` or the user explicitly asks to start Jenkins directly.

## Job URL Rules

Normalize folder jobs carefully:

- `jobName: "folder/my-app"` maps to `<jenkinsUrl>/job/folder/job/my-app`.
- If `jobUrl` is configured, trust it instead of rebuilding from `jobName`.

Trigger endpoints:

- Non-parameterized: `POST <jobUrl>/build`
- Parameterized: `POST <jobUrl>/buildWithParameters`

For parameterized builds, send `buildParams` as form fields unless the job API clearly requires a different encoding.

Only call these trigger endpoints for `trigger: "jenkins-build"` or when the user explicitly asks to start Jenkins directly. For omitted `trigger` or `trigger: "git-tag"`, the side effect is the Git tag push, not a Jenkins `/build` request.

## Build Correlation

After triggering a Jenkins build:

1. Prefer the `Location` response header. It usually points to a queue item.
2. Poll `<queueItemUrl>/api/json` until `executable.number` appears.
3. Use that build number as the primary correlation key.
4. Poll `<jobUrl>/<buildNumber>/api/json` for `building`, `result`, `timestamp`, `duration`, and `url`.
5. Read `<jobUrl>/<buildNumber>/consoleText` only for the correlated build.

Terminal results:

- Treat `SUCCESS` as success.
- Treat `FAILURE`, `ABORTED`, `UNSTABLE`, and other non-success terminal results as failure unless the user explicitly says that result is acceptable.

When the correlated build reaches a non-success terminal result, stop immediately. Do not continue polling, do not extract any image, do not inspect older successful builds, and do not trigger a deploy job. Report the failed Jenkins build URL (`<jobUrl>/<buildNumber>/`), terminal result, and a short sanitized snippet from the correlated console log when helpful.

Do not extract an image from a previous successful build when handling `部署`.

## Image Extraction

Extract only images matching `imagePattern` when it is configured.

Preferred sources:

1. Explicit build artifacts or environment metadata exposed by the Jenkins job API.
2. Correlated `consoleText` lines containing project image pushes or build tags.
3. The last matching `repository:tag` in the successful correlated build log.

Normalize digest-qualified references from `repository:tag@sha256:<digest>` to `repository:tag` before reporting or syncing.

If no image can be safely extracted, report the build as successful but stop before sync.

## Image Sync

Jenkins does not imply image sync by default.

Supported sync patterns may be configured per target:

- `syncImage: false`: build only.
- `syncImage: true` with `deployJobUrl` or `deployJobName`: trigger a second Jenkins job to deploy the selected image.
- `syncImage: true` with provider-specific future fields such as `argocdApp`, `k8sNamespace`, or `apolloTarget`: stop unless that sync provider is documented.

For a Jenkins deploy job:

```json
{
  "syncImage": true,
  "deployJobUrl": "https://jenkins.example.com/job/my-app-deploy",
  "deployBuildWithParameters": true,
  "deployParams": {
    "IMAGE": "{{image}}"
  }
}
```

Replace `{{image}}` in `deployParams` with the normalized image. Trigger the deploy job like any other Jenkins job, correlate its build number, and wait for terminal status.

If the deploy job reaches a non-success terminal result, stop immediately. Do not keep polling or retrying in a loop. Report the failed Jenkins deploy build URL, terminal result, and a short sanitized snippet from the correlated deploy console log when helpful.

If the deploy job exposes the previous image and new image, include both in the final report. Otherwise report the synced image and the deploy job result without inventing a previous image.

## Discovery

If `deploy.json` is missing or the selected target lacks a Jenkins job:

1. First confirm Jenkins has been selected as the provider if the deployment request was generic.
2. Ask for the exact Jenkins job URL for the selected target when it is missing. Avoid asking several setup questions up front, and do not print inferred-field summaries before the question.
3. Load Jenkins credentials from the current process or local secrets file, then validate the job with `<jobUrl>/api/json` before writing `deploy.json`. If credentials are missing or authentication fails, stop and provide the local credentials setup script. Do not generate `deploy.json` yet.
4. Default to `git-tag` trigger. Ask whether Jenkins is directly triggered only when the user has indicated this is not a tag-triggered project.
5. For `git-tag`, inspect `package.json#tagPrefix` and Git remotes. Infer `remote`, `tagPrefix`, `versionType`, and `editPkg` using the defaults above. Ask only when inference is ambiguous.
6. For `jenkins-build`, after the authenticated job API succeeds, discover whether the job is parameterized and list required parameter names.
7. Ask only for required parameter values that cannot be inferred safely. Do not ask for `imagePattern` before the first build if the image can likely be inferred from the successful build log.
8. Write the selected target config back to `deploy.json`.

Preferred question style for a missing dev Jenkins job URL:

```text
请提供这个项目开发环境的 Jenkins Job 完整 URL，例如：[http://192.168.210.40:30080/job/cqwx-dual-grid-h5/](http://192.168.210.40:30080/job/cqwx-dual-grid-h5/)
```

For production, replace `开发环境` with `生产环境`. Use Markdown link syntax for example URLs so the user can click them.

Do not write Jenkins secrets to project files.
