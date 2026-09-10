# 项目与共享 Nginx 配置

## 目录

1. 项目镜像内 Nginx
2. PUBLIC 共享 Nginx 路由
3. 容器文件 API
4. 备份、检查与平滑加载
5. 验证与回滚
6. 故障定位

## 1. 项目镜像内 Nginx

前端单页应用部署在子路径时，根目录 `nginx.conf` 至少处理：

- 无尾斜杠地址跳转
- 静态目录 alias
- `index.html`
- history fallback
- 和镜像内目录一致的基路径

模板：

```nginx
user  root;
worker_processes  1;

error_log  /var/log/nginx/error.log warn;
pid        /var/run/nginx.pid;

events {
    worker_connections  102400;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout 65;
    gzip_static   on;

    server {
        listen 80;
        server_name _;

        location = /<base-path> {
            return 301 /<base-path>/;
        }

        location /<base-path>/ {
            alias /<base-path>/;
            index index.html;
            try_files $uri $uri/ /<base-path>/index.html;
        }
    }
}
```

如果 Vite 使用相对资源路径（如 `base: './'`），仍需验证二级路由刷新和资源 URL。不要仅检查首页 HTML。

## 2. PUBLIC 共享 Nginx 路由

共享入口修改属于高风险操作，必须获得用户单独确认。操作前动态发现：

1. PUBLIC 系统和 `System-Id`
2. Nginx 拓扑应用和 `appId`
3. 当前 Running/Ready Pod
4. 容器名
5. 实际挂载的 `conf.d` 文件
6. 至少一个现有、可用于回归验证的路由

不要硬编码历史 Pod 名。Pod 重建后名称会改变。

路由模板：

```nginx
    # <项目说明>
    location /<base-path> {
        proxy_pass http://<service-name>.<namespace>/<base-path>/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
```

插入前检查：

- `location /<base-path>` 数量必须为 0；若已有配置，比较内容并让用户决定。
- 上游 Service、命名空间、URI 和尾斜杠必须匹配。
- 选择稳定的相邻注释或路由作为插入锚点，不重排整份配置。
- 保存下载内容的 SHA-256；上传前再次确认当前内容未变化。

## 3. 容器文件 API

认证头遵循 `trs-apollo`，使用 PUBLIC 系统的 `System-Id`。以下是已验证的文件操作形态。

### 3.1 列目录

```text
GET /devops/k8s/pod/container/getFiles
  ?name=<pod>
  &container=<container>
  &path=/etc/nginx/conf.d
```

### 3.2 下载

```http
POST /devops/k8s/pod/container/download
Content-Type: application/json;charset=UTF-8

{
  "name": "<pod>",
  "container": "<container>",
  "filePath": "/etc/nginx/conf.d/<file>.conf"
}
```

下载响应是文件流。先确认 HTTP 状态和内容类型；如果响应看起来是 JSON，解析 Apollo 错误码，不能把错误 JSON 当配置文本上传回去。

### 3.3 上传覆盖

```text
POST /devops/k8s/pod/container/upload
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 值 |
| --- | --- |
| `sourceFile` | 修改后的配置 Blob/File，文件名与目标文件相同 |
| `name` | 当前 Pod 名 |
| `container` | Nginx 容器名 |
| `targetPath` | `/etc/nginx/conf.d` |
| `modifyTimestamp` | 当前文件时间戳（毫秒） |
| `override` | `true` |

只有跨命名空间/通配系统上下文需要额外传 `namespace`；以已确认的上传 API 契约为准。无法确认该字段用法时，暂停上传并报告缺口，不通过页面请求或抓包探查。

上传后立即重新下载并比较完整 SHA-256、目标路由数量和上游地址。任何不一致都禁止执行 `nginx -t` 或 reload。

## 4. 备份、检查与平滑加载

Apollo 容器终端 WebSocket 形态：

```text
ws://<apollo-host>/devops/container/terminal
  ?name=<pod>
  &namespace=<namespace>
  &token=<token>
  &container=<container>
  &cols=120
  &rows=40
```

通过命令行客户端连接上述 WebSocket。Token 只从 `trs-apollo` 指定的钥匙链会话读取，不打印、不写入脚本或 Skill。终端消息采用以下已确认协议：

```json
{"o":"keepAlive","command":true}
{"o":"data","command":"<command>\r"}
```

写入前创建不会被 `*.conf` include 匹配的备份名：

```bash
cp /etc/nginx/conf.d/<file>.conf \
  /etc/nginx/conf.d/<file>.conf.bak-YYYYMMDD-HHMMSS
```

上传并回读成功后执行：

```bash
nginx -t
```

只在退出码为 0 时执行：

```bash
nginx -s reload
```

禁止为了应用一条路由而执行 `nginx -s stop`、停止 Pod、删除 Pod或重启整个共享应用。

## 5. 验证与回滚

### 成功路径

1. 回读配置，确认目标路由恰好 1 条。
2. `nginx -t` 成功。
3. `nginx -s reload` 成功。
4. 新 URL 返回 200 或预期跳转，最终为 HTML。
5. 通过 HTTP 响应中的 HTML `<title>` 或稳定文本标识确认项目。
6. 抽查至少一个旧路由，不能出现 5xx。
7. PUBLIC Nginx Pod 和业务 Pod 仍为 `Running`、Ready。
8. 可选：解析首页静态资源 URL 并抽查关键 JS/CSS 返回 200。

### `nginx -t` 失败

1. 不 reload。
2. 用备份恢复原文件，或上传先前下载的原始内容。
3. 再执行 `nginx -t`，确认旧配置有效。
4. 汇报错误、备份路径和当前实际配置状态。

### reload 失败

1. 保留备份和失败输出。
2. 检查主进程权限、PID、错误日志和配置状态。
3. 不自动 stop/start；这需要新的用户授权。

### 写入竞争

如果上传前当前配置哈希不再等于最初下载哈希：

1. 停止写入。
2. 重新下载最新配置。
3. 在最新内容上重新生成最小变更。
4. 再次备份、上传、回读。

## 6. 故障定位

| 症状 | 检查顺序 |
| --- | --- |
| 502 Bad Gateway | Service DNS → 命名空间 → Endpoint → Pod Ready → containerPort |
| 404 首页 | proxy URI → 项目 location/alias → 镜像内目录 |
| 首页 200、JS/CSS 404 | Vite `base` → 相对路径 → 尾斜杠 → proxy URI |
| 刷新子路由 404 | 项目 Nginx `try_files` history fallback |
| 新路由正常、旧路由异常 | 共享配置差异、重复 location、误改 server 块 |
| reload 成功但配置未生效 | 操作的 Pod/容器/配置文件是否为当前活动实例 |
| 上传接口成功但内容不同 | `targetPath`、文件名、`override`、并发修改 |
