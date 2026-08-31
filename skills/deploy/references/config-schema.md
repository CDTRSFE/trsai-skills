# Deployment Config Schema

Deployment configuration lives in project-root `deploy.json`.

## Shared Shape

```json
{
  "provider": "apollo",
  "defaultTarget": "dev",
  "environments": {
    "dev": {
      "envName": "开发环境",
      "applicationName": "my-app",
      "imagePattern": "harbor.example.com/team/my-app:",
      "syncImage": true
    }
  },
  "confirmBeforeStart": false,
  "confirmBeforeSyncImage": false
}
```

Required top-level fields:

- `provider`: deployment provider adapter, such as `apollo` or `jenkins`.
- `defaultTarget`: environment key used when the user does not name a target.
- `environments`: object keyed by target names such as `dev`, `test`, `prod`, or project-specific names.

Standard target meanings:

- `dev`: development / `开发环境`.
- `prod`: production / `生产环境`.

Optional top-level fields:

- `confirmBeforeStart`: when `true`, ask before starting a build or pipeline.
- `confirmBeforeSyncImage`: when `true`, ask before changing the deployed image.

Recommended environment fields:

- `envName`: user-facing environment name.
- `applicationName`: application/service name.
- `imagePattern`: accepted image prefix. Reject mismatched images unless the user explicitly confirms.
- `syncImage`: whether `build-and-sync` should sync the produced image after build success.

## Provider Extension Fields

Providers may add fields under each environment. Keep extensions close to the target they affect.

Apollo commonly uses:

```json
{
  "provider": "apollo",
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
    }
  }
}
```

Jenkins commonly uses:

```json
{
  "provider": "jenkins",
  "defaultTarget": "dev",
  "jenkinsUrl": "https://jenkins.example.com",
  "environments": {
    "dev": {
      "envName": "开发环境",
      "jobName": "folder/my-app-build",
      "jobUrl": "https://jenkins.example.com/job/folder/job/my-app-build",
      "buildWithParameters": true,
      "buildParams": {
        "BRANCH": "develop"
      },
      "applicationName": "my-app",
      "imagePattern": "harbor.example.com/team/my-app:",
      "syncImage": false
    }
  },
  "confirmBeforeStart": false,
  "confirmBeforeSyncImage": false
}
```

For Jenkins jobs triggered by Git tags instead of direct Jenkins `/build` calls, use:

```json
{
  "provider": "jenkins",
  "defaultTarget": "dev",
  "jenkinsUrl": "http://192.168.210.40:30080",
  "environments": {
    "dev": {
      "envName": "开发环境",
      "trigger": "git-tag",
      "remote": "origin",
      "tagPrefix": "cq-dev-v",
      "versionType": "patch",
      "editPkg": true,
      "jobName": "cqwx-dual-grid-h5",
      "jobUrl": "http://192.168.210.40:30080/job/cqwx-dual-grid-h5",
      "applicationName": "cqwx-dual-grid-h5",
      "imagePattern": "harbor.example.com/team/cqwx-dual-grid-h5:",
      "syncImage": false
    }
  },
  "confirmBeforeStart": true,
  "confirmBeforeSyncImage": true
}
```

Jenkins `git-tag` target fields:

- `trigger`: set to `git-tag`.
- `remote`: Git remote to push the tag to, usually `origin`.
- `tagPrefix`: selected tag prefix, such as `cq-dev-v` for `dev` or `cq-prod-v` for `prod`. Infer this from `package.json#tagPrefix` when possible.
- `versionType`: `major`, `minor`, `patch`, or `RC`; default to `patch`.
- `editPkg`: whether the tag helper should update `package.json#tag`; default to `true`.
- `jobUrl`: Jenkins job URL used for polling the automatically triggered build.
- `imagePattern`: preferred when known. If missing, try to infer it from the correlated successful Jenkins console log and ask only when extraction is ambiguous.

Jenkins authentication may be configured with environment variables instead of `deploy.json`:

- `JENKINS_USERNAME`
- `JENKINS_PASSWORD`
- `JENKINS_API_TOKEN`
- `JENKINS_BEARER_TOKEN`

Do not write secrets to `deploy.json`.

## Writeback Rules

- Preserve existing unrelated keys.
- Add or update only the selected target unless the user asks for multiple environments.
- Prefer stable target order: `dev`, `test`, `stage`, `staging`, `prod`, followed by any custom keys in existing order.
- Keep provider-specific fields under the environment unless the value is truly shared across all targets.
- Do not leave placeholder strings such as `TODO` or `TBD` in a created config. Ask for the missing value instead.
