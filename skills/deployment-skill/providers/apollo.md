# Apollo Provider

Use this provider when `deploy.json` has `"provider": "apollo"` or the user selects Apollo deployment. `部署` means build the selected Apollo pipeline, get the pushed image, then update the selected environment application image. `更新镜像` means update the selected environment application image without starting a build. When the user inputs exactly or clearly `部署生产`, run the production deployment flow.

This provider file is the source of truth for Apollo-specific APIs, authentication, discovery, polling, and reporting inside `deployment-skill`.

If the user only says a generic `部署`/`发布` and the project has no `deploy.json` or no configured `provider`, do not assume Apollo and do not ask for an Apollo pipeline name yet. Return to `deployment-skill` routing so the user can choose Apollo or Jenkins.

## Language

When the user writes in Chinese, all user-facing progress updates, questions, and final reports must be in Chinese. Keep API paths, field names, image tags, branch names, commit hashes, and status constants such as `SUCCESS` in their original form.

## Configuration

Read only `deploy.json` from the project root. Do not search `.codex/` and do not infer deployment config from `package.json`.

Select the target environment before reading environment-specific configuration:

- If the user says `部署生产`, `生产部署`, `prod`, or otherwise clearly asks for production, use `prod`.
- In TRS projects, a bare `部署`, `发布`, `build`, or `运行流水线` means `dev` / `云哨开发环境`. Use `dev` even when `deploy.json.defaultTarget` is `prod` or only `environments.prod` exists.
- Use `defaultTarget` only for non-TRS projects or when the user explicitly asks to use the configured default target.
- Do not create, discover, or require `dev` configuration while handling `prod`; do not create, discover, or require `prod` configuration while handling `dev`. Each target owns its own configuration.

Known Apollo environment mapping:

- `dev`: `云哨开发环境` / `trs-police-yunshao`
- `prod`: `云哨测试环境` / `trs-police-yunshao-test`

When switching Apollo systems, match the selected target exactly by configured namespace/system code. For example, `dev` must select `systemCode === "trs-police-yunshao"` and `prod` must select `systemCode === "trs-police-yunshao-test"`. Never select systems with fuzzy checks such as `systemName.includes("云哨")`, because both development and test environments contain that text.

If `deploy.json` is missing, do not open Apollo UI, search pages, or infer the target from the repository/package name. First ask the user to provide the exact Apollo pipeline name for the selected target from `http://10.18.20.131:90/apollo-web/#/pipeline`. Use this fixed prompt, replacing `<目标环境>` and `<namespace>` with the selected target's known mapping when available:

```text
项目根目录没有找到 deploy.json。

当前目标环境：<目标环境>（<namespace>）

请提供这个项目在当前目标环境对应的 Apollo 精确流水线名称：
http://10.18.20.131:90/apollo-web/#/pipeline

收到后我会先做 Apollo 登录预检；预检通过后再通过 Apollo API 校验流水线，生成 deploy.json，然后继续部署。
```

Do not continue to discovery, build, or image sync until the user confirms the exact pipeline name. After the pipeline name is confirmed, discover the remaining fields through Apollo APIs, create a small deterministic `deploy.json` containing only the selected target's `environments.<target>` entry, and continue through APIs. After `deploy.json` exists, trust its configured mapping instead of re-discovering by project name.

If `deploy.json` exists but the selected target environment is missing or incomplete, ask only for that target's missing production/development configuration. If a bare `部署` selected `dev` and the file only contains `prod`, treat that as missing `dev` configuration; do not run or modify `prod`, and do not rewrite the existing `prod` entry into `dev`. For `dev`, use `云哨开发环境` / `trs-police-yunshao`; for `prod`, use `云哨测试环境` / `trs-police-yunshao-test`. Use this prompt:

```text
deploy.json 里没有找到当前目标环境的完整配置。

当前目标环境：<目标环境>（<namespace>）

请提供这个项目在当前目标环境对应的 Apollo 精确流水线名称：
http://10.18.20.131:90/apollo-web/#/pipeline

收到后我会先做 Apollo 登录预检；预检通过后再通过 Apollo API 校验流水线，补齐 deploy.json，然后继续部署。
```

Do not add or modify the other target as part of that run.

Use this provider only when `provider` is `apollo`. If `provider` is another value such as `jenkins`, return to `deployment-skill` routing.

When creating or updating `deploy.json`, preserve a stable JSON shape:

1. Top-level keys: `provider`, `defaultTarget`, `apolloUrl`, `apiBaseUrl`, `environments`, `confirmBeforeStart`, `confirmBeforeSyncImage`.
2. Environment keys must always be ordered `dev` first, then `prod`, when both are present.
3. If only one target exists because the other target has never been configured, write only that target. When the other target is added later, insert it into the stable `dev` then `prod` order instead of appending based on discovery time.
4. Within each environment, keep the field order shown in the config template below.

## API Authentication

Authentication priority:

1. Prefer `APOLLO_TEST_USERNAME` + `APOLLO_TEST_PASSWORD` from the current process environment.
2. If those environment variables are absent, load them from the local private file for the current OS when it exists:
   - macOS/Linux: `~/.codex/secrets/apollo.env`
   - Windows PowerShell/CMD: `%USERPROFILE%\.codex\secrets\apollo.env`
3. Use an existing logged-in Codex in-app browser Apollo session only when local credentials are absent or API login fails. Use it only for authentication/session reuse and same-origin API requests; do not click UI controls for deployment operations.
4. If API login, local secret loading, and browser-session API authentication all fail, report the failing endpoint/status/message and stop. Do not use UI deployment fallback unless the user explicitly asks after seeing the API failure.

Apollo authentication preflight is mandatory before validating a pipeline, creating or updating `deploy.json`, starting a pipeline build, extracting the current build image, or syncing an image. If credentials are missing or login/session validation fails, stop immediately. Do not start a build and do not let a pipeline produce an image before discovering that Apollo authentication is unavailable.

Do not ask the user for copied request headers as the normal path.

Do not store Apollo credentials in project `deploy.json`, deployment logs, Git commits, final reports, or the skill itself. Team-shared credentials should be distributed out of band and placed by each user in their own local secrets file.

Recommended local secret file:

```text
macOS/Linux: ~/.codex/secrets/apollo.env
Windows:     %USERPROFILE%\.codex\secrets\apollo.env
```

When asking the user to configure Apollo credentials, provide copy-paste scripts, not only the env file path or a separate "content format" block.

Default to editable-at-the-top scripts, not interactive prompts. The user should only need to change the username and password assignment lines, then paste the matching block into their terminal.

If the current OS cannot be reliably detected from the active workspace or tool environment, provide both the macOS/Linux script and the Windows CMD script in the same response. Do not ask the user whether they are on macOS or Windows just to choose a credentials script.

For macOS/Linux, provide this shell script:

```bash
# 只需要改下面两行，然后整段复制到终端运行
APOLLO_TEST_USERNAME='你的 Apollo 账号'
APOLLO_TEST_PASSWORD='你的 Apollo 密码'

mkdir -p "$HOME/.codex/secrets"
chmod 700 "$HOME/.codex/secrets"

cat > "$HOME/.codex/secrets/apollo.env" <<EOF
APOLLO_TEST_USERNAME=$APOLLO_TEST_USERNAME
APOLLO_TEST_PASSWORD=$APOLLO_TEST_PASSWORD
EOF
chmod 600 "$HOME/.codex/secrets/apollo.env"
echo "已写入 $HOME/.codex/secrets/apollo.env"
```

For Windows CMD, provide this script:

```bat
:: 只需要改下面两行，然后整段复制到 CMD 运行
set "APOLLO_TEST_USERNAME=你的 Apollo 账号"
set "APOLLO_TEST_PASSWORD=你的 Apollo 密码"

mkdir "%USERPROFILE%\.codex\secrets" 2>nul
(
  echo APOLLO_TEST_USERNAME=%APOLLO_TEST_USERNAME%
  echo APOLLO_TEST_PASSWORD=%APOLLO_TEST_PASSWORD%
) > "%USERPROFILE%\.codex\secrets\apollo.env"

echo 已写入 %USERPROFILE%\.codex\secrets\apollo.env
```

If the user specifically asks for PowerShell, provide this script:

```powershell
# 只需要改下面两行，然后整段复制运行
$APOLLO_TEST_USERNAME = "你的 Apollo 账号"
$APOLLO_TEST_PASSWORD = "你的 Apollo 密码"

New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\secrets" | Out-Null
@"
APOLLO_TEST_USERNAME=$APOLLO_TEST_USERNAME
APOLLO_TEST_PASSWORD=$APOLLO_TEST_PASSWORD
"@ | Set-Content -Encoding utf8 "$env:USERPROFILE\.codex\secrets\apollo.env"
icacls "$env:USERPROFILE\.codex\secrets\apollo.env" /inheritance:r /grant:r "${env:USERNAME}:(R,W)" | Out-Null
Write-Host "已写入 $env:USERPROFILE\.codex\secrets\apollo.env"
```

Do not put this file inside a project repository.

## API Login

When credentials are present, use code-level HTTP requests from Node/Python, not browser URL navigation and not page `fetch`. Maintain a cookie jar/session between requests. Support both GET query requests and POST JSON requests with the same authenticated client.

Known login flow:

1. `GET <apiBaseUrl>/apollo/config/login/public/key` to obtain the login public key string from `result.data[0]`.
2. Convert the public key to PEM and encrypt with RSA public-key encryption using PKCS#1 v1.5 padding, matching the Apollo frontend `$rsa.encrypt(...)`.
3. Build the login payload exactly as:
   - `tel`: RSA encrypt `base64(encodeURIComponent(APOLLO_TEST_USERNAME))`
   - `password`: RSA encrypt `base64(APOLLO_TEST_PASSWORD)`
   - `rememberMe`: `false`
4. `POST <apiBaseUrl>/apollo/user/login` as JSON with the encrypted payload and the shared cookie jar.
5. Read `token` from `result.data[0].token`. Send `X-User-Token: <token>` on later API calls.
6. Query `/devops/system/1.0/queryAllSystems`, select the configured namespace system when possible, call `/devops/system/1.0/switchSystem?systemId=<systemId>`, and send `System-Id` from the selected system's `systemIdCipher` (fall back to `systemId`) on DevOps calls.
7. Validate the authenticated session by calling `/devops/pipeline/list`.

System selection is part of authentication setup and must be exact: choose the row where `systemCode === environments.<target>.namespace` when present. Only fall back to another exact configured identifier, such as the configured `envName`, after reporting why `systemCode` was unavailable. Do not use the first "云哨" row or any partial-name match.

Node encryption reference:

```js
const { publicEncrypt, constants } = await import("node:crypto");

const publicKeyPem = `-----BEGIN PUBLIC KEY-----\n${publicKey.match(/.{1,64}/g).join("\n")}\n-----END PUBLIC KEY-----`;
const encryptForApollo = (value) =>
  publicEncrypt(
    { key: publicKeyPem, padding: constants.RSA_PKCS1_PADDING },
    Buffer.from(value, "utf8")
  ).toString("base64");

const payload = {
  tel: encryptForApollo(Buffer.from(encodeURIComponent(APOLLO_TEST_USERNAME), "utf8").toString("base64")),
  password: encryptForApollo(Buffer.from(APOLLO_TEST_PASSWORD, "utf8").toString("base64")),
  rememberMe: false
};
```

Do not store or reuse a pre-encrypted username/password ciphertext. RSA PKCS#1 encryption may produce different ciphertext for the same input; generate fresh encrypted fields for each login attempt. If Apollo says the account or password is wrong, first verify the encoding/encryption order above before assuming the temporary credentials are invalid.

Do not rediscover the login endpoint, public-key endpoint, or encryption rule on every deployment. Use the known login flow directly. Rediscover from Apollo frontend assets only if the known login flow fails with a concrete HTTP/API error indicating the login contract changed. If login fails, report the login endpoint, HTTP status/business code, and sanitized message; never print the password.

Default target:

- If the user says `部署生产`, `生产部署`, `prod`, or otherwise clearly asks for production, use `prod`.
- If the user does not name an environment, use `defaultTarget`, then `dev`.
- Handle `dev` and `prod` with the same API-first workflow. The only difference is which `environments.<target>` mapping is used.
- Do not ask for confirmation unless `confirmBeforeStart` or `confirmBeforeSyncImage` is explicitly `true`.

Apollo config fields:

```json
{
  "provider": "apollo",
  "defaultTarget": "dev",
  "apolloUrl": "http://10.18.20.131:90/apollo-web",
  "apiBaseUrl": "http://10.18.20.131:90",
  "environments": {
    "dev": {
      "envName": "云哨开发环境",
      "namespace": "trs-police-yunshao",
      "pipelineName": "gzbigscreen",
      "jobName": "gzbigscreen",
      "jenkinsId": 3,
      "applicationName": "gzbigscreen",
      "imagePattern": "harbor.trscd.com.cn/trs-police-yunshao/gzbigscreen:",
      "syncImage": true,
      "appId": null,
      "resourceType": 3
    },
    "prod": {
      "envName": "云哨测试环境",
      "namespace": "trs-police-yunshao-test",
      "pipelineName": null,
      "jobName": null,
      "jenkinsId": null,
      "applicationName": null,
      "imagePattern": null,
      "syncImage": true,
      "appId": null,
      "resourceType": 3
    }
  },
  "confirmBeforeStart": false,
  "confirmBeforeSyncImage": false
}
```

`appId` is optional in the template but required for API-first image sync. When it is missing, discovering it during the current run is mandatory before treating config discovery as complete. Write it back to `deploy.json`. Do not use UI fallback for image sync unless the user explicitly approves UI after an API failure has been reported. The next run should use APIs.

When `appId` exists, API-first is mandatory for image discovery and image sync. Do not go to the system topology UI to change images unless the relevant API call has failed with a concrete error or the user explicitly asks to use the UI.

## Action Selection

- `部署`: start the selected target pipeline, wait for the current build to finish, extract the pushed image, then sync the selected target app image when `syncImage` is true.
- `部署生产`: use target `prod`, then run the same build/poll/extract/sync workflow as `部署`.
- `更新镜像 <image>` or `变更镜像 <image>`: do not build; sync the selected target app to the provided image.
- `更新镜像` with no image: do not build; use the latest successful pushed image. Prefer Apollo image options marked `最新版本`; otherwise use the latest image matching `imagePattern` from the pipeline log.

Reject images that do not start with `imagePattern` unless the user explicitly confirms the mismatch.

## API-First Workflow

Prefer Apollo APIs when the required identifiers are known and the current browser session is logged in. Do not use Apollo UI for deployment operations. Browser control is allowed only to access an existing logged-in session or, if necessary, to execute same-origin API requests from that session context. Same-origin browser `fetch` is considered API-first; clicking buttons, selecting rows, opening dialogs, or paginating tables is UI operation.

Use temporary credentials as the default authentication path. Do not inspect Apollo frontend bundles during normal deployments just to rediscover login details that are already listed in this skill.

Derive API base URL before making requests:

- Page routes use `apolloUrl`, for example `http://10.18.20.131:90/apollo-web/#/pipeline`.
- API requests use `apiBaseUrl`, for example `http://10.18.20.131:90/devops/pipeline/list`.
- If `apiBaseUrl` is absent, derive it by removing `/apollo-web` and everything after it from `apolloUrl`.
- Never call APIs under `/apollo-web/devops/...`; that path is a wrong frontend-prefixed API URL and may return 404.

Hard rules:

- API request means a code-level HTTP request with explicit method, URL, query params, headers, cookies, and body. Do not implement API calls by navigating the browser to a URL.
- Prefer using a maintained reusable deployment script when one exists or after repeated Apollo deployment runs reveal stable behavior. Do not re-create ad hoc polling, terminal-state, and image-parsing logic from memory when a project or skill script can encode those rules deterministically.
- Do not use plain `curl` for Apollo APIs unless the request includes all required Apollo session cookies and headers. Prefer same-origin `fetch` from the logged-in browser context, or reuse headers/cookies captured from Apollo network requests.
- If same-origin browser `fetch`/`XMLHttpRequest` fails with a client-side browser error such as `net::ERR_BLOCKED_BY_CLIENT`, do not treat the Apollo API as unavailable and do not ask to use UI fallback. Switch request transport: use the browser automation request context when available, or export the logged-in session cookies and required headers from existing Apollo Network requests and call the API with Node/Python HTTP client. Only treat it as an API failure after the non-page request transport returns an actual HTTP/API error.
- When `deploy.json` is missing, the user-confirmed pipeline name is mandatory. Do not paginate or search the Apollo UI to guess it.
- After the pipeline name is known, use Apollo APIs to discover `pipelineName`, `jobName`, `namespace`, `jenkinsId`, `applicationName`, `appId`, `resourceType`, and image fields.
- Validate the user-confirmed pipeline name with `/devops/pipeline/list` before any side effect. If the API returns no exact matching pipeline, multiple exact candidates that cannot be distinguished, or only fuzzy/partial matches, stop immediately and tell the user the provided pipeline name is not valid enough to deploy. Do not start a build or sync an image.
- If `appId` is present, use `queryAppImages`, `deployByImage`, and `getStatus` for image sync.
- Do not silently fall back to UI after one failed attempt to call an API. First identify and report the failing endpoint and error. Then retry with the correct session/headers or ask the user whether to use UI fallback.
- UI fallback for deployment, build start, or image sync is not allowed unless the user explicitly asks to use UI after an API failure has been reported.
- Browser control may still be used to access the logged-in session, but the operation should be an API call from that session, not manual clicking, when API prerequisites are present.

Known Apollo endpoints:

- Pipeline list: `GET /devops/pipeline/list?buildTimeType=&autoBuild=&projectType=&jobState=&pipelineName=&sortField=&sort=&pageNo=1&pageSize=10&random=<n>`
- Pipeline start: `GET /devops/pipeline/start?jobName=<jobName>&namespace=<namespace>&jenkinsId=<jenkinsId>&random=<n>`
- Pipeline log: `GET /devops/pipeline/log`
- System topology app list: `GET /devops/app/list?...` returns `result.data[].deployApps[]`; each deploy app can include `appId`, `appName`, `repositoryName`, `deployTag`, `deployTags`, `appType`, `projectName`, and `operation`.
- App image options: `GET /devops/basicEnvConf/1.0/application/queryAppImages?appId=<appId>`
- Change image: `POST /devops/cicd/v1.0/job/deployByImage` with body `{ "appId": <appId>, "image": "<full image>" }`
- Image deploy status: `GET /devops/cicd/v1.0/job/getStatus?appId=<appId>&resourceType=<resourceType>`
- App pods after sync: `GET /devops/k8s/pod/getAppPods?appId=<appId>`

## Config Discovery and Writeback

When config is missing or incomplete, discover fields in this order and write them back to project-root `deploy.json`:

1. Confirmed pipeline name:
   - If `deploy.json` is missing and the user has not provided the exact Apollo pipeline name, stop and ask for it.
   - If the selected target entry is missing or has no `pipelineName`, stop and ask for the exact Apollo pipeline name for that target only.
   - Query `/devops/pipeline/list` with the confirmed pipeline name.
   - Require exactly one exact matching pipeline result before starting a build.
   - If there is no exact match, terminate and report `未找到流水线：<name>` without trying UI search or fuzzy alternatives.
   - If there are multiple exact matches and the API fields cannot distinguish the target safely, terminate and ask the user to clarify the target.
   - Use the pipeline result or log API to store `pipelineName`, `jobName`, `namespace`, `jenkinsId`, `envName`, and `applicationName` under the selected target only.
   - For `prod`, default `envName` to `云哨测试环境` and `namespace` to `trs-police-yunshao-test` when the API does not return clearer values.
2. System topology API:
   - Query `/devops/app/list` with the confirmed `applicationName` or pipeline/application name.
   - Prefer the `/devops/app/list` response over DOM scraping. Find the exact app under `result.data[].deployApps[]`.
   - Match by exact `appName === applicationName`; if needed also verify `repositoryName`, `deployTag`, or `deployTags` starts with `imagePattern`.
   - Store `appId` and `appType`/`resourceType` from the matched deploy app in `deploy.json`.
   - If the matched `/devops/app/list` `deployApps[]` item contains `appId`, writing `"appId": null` is invalid.
3. Apollo read APIs, when callable from the current browser session:
   - Find the app in `/devops/app/list` or related app list responses by exact `appName`/`applicationName`.
   - Store its `appId` and `resourceType` in `deploy.json`.
   - Then use `queryAppImages`, `deployByImage`, and `getStatus`.

Before leaving `"appId": null`, explicitly verify and report that `/devops/app/list` was unavailable, unauthorized, or returned no exact matched deploy app. If `appId` still cannot be discovered safely, do not perform image sync through UI unless the user explicitly approves UI fallback after seeing the API failure.

During pipeline build polling on first setup, concurrently use `/devops/app/list` to discover and write back `appId`/`resourceType` so image sync can use `deployByImage` immediately after the pushed image is known.

## Interface Discovery

When an API is unknown, use Apollo Network requests as a discovery surface, not as the permanent execution path:

1. Prefer inspecting existing Network requests from the logged-in browser session.
2. Do not click UI controls to discover build/deploy/change-image requests unless the user explicitly asked to use UI after an API failure.
3. Read the Network request method, URL, query/body, and response shape.
4. Update `deploy.json` if the request reveals stable project fields, and update this skill only when a reusable Apollo rule is learned.
5. Subsequent runs should call the discovered API directly through `apiBaseUrl`.

Examples already observed:

- Clicking pipeline run calls `GET <apiBaseUrl>/devops/pipeline/start?jobName=<jobName>&namespace=<namespace>&jenkinsId=<jenkinsId>&random=<n>`.
- Pipeline list calls `GET <apiBaseUrl>/devops/pipeline/list?...`.
- System topology search/list calls `GET <apiBaseUrl>/devops/app/list?...` and returns app metadata under `result.data[].deployApps[]`.

For image options, Apollo returns entries containing `image`, `deployItem`, `tag`, `latest`, `currentTag`, `pushInfo`, and `pushTime`. Use `latest` for default `更新镜像`; use `currentTag` to report the previous/current image.

Image sync status values observed from Apollo:

- `getStatus` returns status rows under `result.data[]`; read the first row, usually `result.data[0].status`. Do not look only at top-level fields such as `result.status`, `data.status`, or response `status`, because that misses successful syncs and causes false timeouts.
- `2`: success. Treat `getStatus` success as the deployment completion signal. Pod queries are optional diagnostics only and must not be included in the successful final report.
- `3`: failed. Report `log` from the status response if present.
- Other values: still running. Continue polling.

When parsing `getStatus`, normalize the response before deciding whether to continue:

```js
const rows = response?.result?.data ?? response?.data ?? [];
const row = Array.isArray(rows) ? rows[0] : rows;
const status = row?.status;
```

When `getStatus` returns a terminal success such as `result.data[0].status === 2`, stop polling immediately and verify the current image with `queryAppImages` or `/devops/app/list` before reporting success. When it returns a terminal failure such as `result.data[0].status === 3`, stop immediately. Do not keep polling, do not retry in a loop, and do not silently switch to UI fallback. Report the image sync failure, the sanitized `log` when present, and the Apollo topology or application URL where the user can inspect and repair the failed image deployment.

When interpreting build logs, only explicit terminal markers decide the build result. Treat `Finished: SUCCESS` as success, and `Finished: FAILURE`, `Finished: ABORTED`, or an Apollo terminal failure status as failure. Do not fail a build merely because log text contains broad words such as `ERROR`, `error`, `failure`, `warning`, `failed`, or command output that includes those substrings; those may appear in harmless tool messages, URLs, dependency warnings, or cleanup logs.

When the current build log reaches an explicit terminal failure marker such as `Finished: FAILURE` or `Finished: ABORTED`, stop immediately. Do not keep polling, do not extract images from that failed build, do not look for an older successful image, and do not sync any image. Report that image construction failed, include a concise sanitized failure snippet when useful, and provide the direct Apollo log URL so the user can inspect and fix the build.

## Current Build Correlation

Never take an image from an older successful build when handling `部署`.

For every triggered build:

1. Record the local trigger time and any row/build identifiers visible after starting the pipeline.
2. Poll until the current build is terminal. A cached pipeline row saying `构建成功` is not enough if the opened log shows a newer build still running.
3. Query the log for the same current build. If the list's last build time and the log start time conflict, treat the list as stale and keep polling the log/current build instead of extracting an image.
4. Extract an image only after the same log contains a terminal success marker such as `Finished: SUCCESS`.
5. Prefer image tags whose timestamp matches the current build/log time. If the image tag timestamp is older than the current log start, reject it as an old image.
6. If Apollo exposes build number, queue id, or log id, use that identifier as the primary correlation key instead of time.

For `更新镜像` without building, the image may come from `queryAppImages` marked `latest`. For `部署`, the image must come from the build just triggered or a verified current-build image option after the build finishes.

If the current build fails, never continue by using `queryAppImages` or the latest older successful image. That fallback is only valid for `更新镜像` without building, not for a failed `部署`.

## Polling

Do not constantly refresh the page. Use targeted API or UI state checks.

- Pipeline build: after starting, record the trigger time and wait until at least 3 minutes after the build start before checking for build result, log output, or image output. After that, poll every 60 seconds. Normal frontend/image builds usually take at least 3 minutes and can take around 20 minutes; use a 30-minute timeout unless the user specifies otherwise. After the first 3-minute check, adapt if the API/log shows clear stage transitions, stalls, failure, or image push progress. Stop at terminal states: success, failure, aborted/stopped, or timeout. On failure or aborted/stopped, report promptly with the direct log URL instead of continuing to poll.
- User-facing build progress updates should be sparse: report the first confirmed current build, major stage changes, image push appearance, terminal success/failure, or no-progress warnings. Do not send a new progress message for every poll when the build is still in the same stage.
- Image sync: poll `getStatus` every 3-5 seconds for the first minute, then 10 seconds. Read sync status from `result.data[0].status`. Stop when status is `2` or `3`, or after a reasonable timeout such as 10 minutes.
- If the user explicitly approves UI fallback after an API failure, refresh only the relevant page/list, not the whole browser, unless the UI is stale.

## Browser Session

Use Browser for Apollo only to access a logged-in session or to run same-origin API requests from that session context.

Do not use Browser UI to start pipelines or change images unless the user explicitly asks to use UI after an API failure. If UI fallback is used by explicit request, state the failed API endpoint and reason before proceeding.

Pipeline API:

1. Call `GET ${apiBaseUrl}/devops/pipeline/start?jobName=<jobName>&namespace=<namespace>&jenkinsId=<jenkinsId>&random=<n>`.
2. Poll the current build through `GET ${apiBaseUrl}/devops/pipeline/log` or another discovered log API.
3. Extract the image only after current-build success.

Topology image sync API:

1. Query `/devops/app/list` to discover `appId` and `resourceType`.
2. Query `queryAppImages` to verify image options/current image when needed.
3. If `confirmBeforeSyncImage` is true, ask before calling `deployByImage`.
4. Call `deployByImage`, then poll `getStatus` until success/failure.

The direct log URL is:

```text
<apolloUrl>/#/log?pipelineName=<pipelineName>&jobName=<jobName>&namespace=<namespace>&jenkinsId=<jenkinsId>&type=pipeline
```

## Image Extraction

Extract only the project image, not base images or credentials. Prefer images starting with `imagePattern`, for example:

```text
harbor.trscd.com.cn/trs-police-yunshao/gzbigscreen:65957d8-20260824_0327
```

If multiple images match, use the last matching image in the current successful build log, especially lines around `docker buildx build`, `pushing manifest`, or `--push`.

Normalize accepted and reported images to `repository:tag`. If an API returns a digest-qualified reference such as `repository:tag@sha256:<digest>`, strip the `@sha256:<digest>` suffix before reporting the image or the previous/new image transition. Prefer the exact `-t repository:tag` value from the build command when present.

Before accepting an image for `部署`, verify it belongs to the build just triggered:

- The log containing the image must have started after the recorded trigger time, or match the current build id if one exists.
- The same log must show success after the image push.
- The tag timestamp must not be older than the current build/log start time.
- If any of these checks fail, continue polling or report uncertainty; do not deploy or report that image.

Do not include credentials, tokens, Docker login passwords, or unrelated log secrets in the answer.

Redact all raw Apollo/Jenkins log snippets before showing them in progress updates or final failure reports. At minimum mask `docker login ... -p <value>`, authorization headers, cookies, tokens, and password-like key/value pairs. This applies to intermediate commentary as well as final answers.

## Reporting

Successful final reports must use the fixed templates below with no extra narrative paragraphs. Keep internal API/login/debug details in progress updates only when useful for troubleshooting; do not include them in the success final report.

For a successful `部署`, use this concise default format:

```text
部署完成：<project> / <environment>

构建状态：SUCCESS
打镜像耗时：<duration>

镜像：
<full image>

<环境名称>已同步：
<previous short image> 变更为 <new short image>
```

Use the selected target's configured `envName` in user-facing text when available. For `dev`, this is usually `云哨开发环境`; for `prod`, use `云哨测试环境`. Compute `打镜像耗时` from the build/log start and end timestamps when available, formatted like `3分38秒`. If exact timestamps are unavailable, omit the duration instead of guessing.

For `更新镜像`, omit build state and duration:

```text
更新完成：<project> / <environment>

镜像：
<full image>

<环境名称>已同步：
<previous short image> 变更为 <new short image>
```

Do not include Pod status, node IP, raw Apollo/Jenkins status text such as `Finished: SUCCESS`, login details, endpoint discovery details, digest suffixes such as `@sha256:...`, or internal details such as `appId` in successful default output. Mention `appId`, UI fallback, or config writeback only when the user needs to act on it or something remains incomplete.

If `deploy.json` was created or updated, append one concise line after the default success output, for example `已新增 deploy.json` or `已更新 deploy.json`. Do not commit or push `deploy.json` unless the user explicitly asks for it. Do not report Pod status such as `1/1 Running` in the success output.

On failure, report the failed phase, terminal state, the most relevant sanitized failure log snippet, and a URL for user inspection. For pipeline build failures, use the direct log URL. For image sync failures, provide the configured Apollo application/topology page URL when available; otherwise provide `apolloUrl` plus the failing API endpoint and app/application identifiers needed to locate the failure.

If `更新镜像` without building uses an older successful image because the latest build failed, clearly say the image came from an older successful build. This fallback is not allowed for `部署`; a failed current build must end the run.
