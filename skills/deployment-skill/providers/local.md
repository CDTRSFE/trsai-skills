# Local Provider（直接打包）

用于 `deploy.json` 中 `provider: "local"` 的项目。本地执行构建并交付 ZIP，支持部署 Tag，不主动调用 Apollo、Jenkins 或镜像同步接口。

## 配置发现

部署方式以项目根目录 `deploy.json` 为准。首次明确选择本地打包时，可从 `package.json` 的 scripts、packageManager、锁文件、项目文档和构建配置识别构建命令及实际产物目录，然后保存配置。不要一律假定 `pnpm build` 或 `dist`；存在多个命令且无法确定时，只询问缺失的选择。

先按 `config-schema.json` 校验文件结构，再使用其中 `$defs.localEnvironment` 校验所选环境；不将本地必需字段强加给未选中的环境。

所选环境必需字段：

- `buildCommand`：在项目根目录执行的构建命令，必须与目标环境相符。
- `outputDir`：构建产物目录，相对于项目根目录。
- `archiveDir`：ZIP 保存目录，相对于项目根目录；首次配置默认 `artifacts`，必须位于 `outputDir` 外。
- `remote`：可选，沿用已有 Git remote；Tag 规则交给 `git-tag-release`，不写入本配置。

示例（命令和目录须按真实项目发现）：

```json
{
  "provider": "local",
  "defaultTarget": "dev",
  "environments": {
    "dev": {
      "buildCommand": "pnpm build",
      "outputDir": "dist",
      "archiveDir": "artifacts"
    }
  }
}
```

只补所选环境，不从已有 `prod` 配置自动推断开发构建命令。默认请求使用 `dev`，即使 `defaultTarget` 为 `prod`。既有无关环境允许保留，执行时只校验所选环境所需字段。

## 执行边界

- 使用 [../workflows/build-and-package.md](../workflows/build-and-package.md)。Tag、运行时输出和推送要求与其他部署方式一致，本地打包不是免 Tag 模式。
- 无需平台账号或流水线地址，但必须具备完成 Git Tag 流程的仓库及 remote。缺失时先解决，不静默降级为无 Tag 打包。
- 用户请求打包已授权执行配置中的构建命令；`git-tag-release` 对额外“发版前构建验证”的限制，不应造成对本次交付构建的重复询问。显式 `confirmBeforeStart` 仍遵守。
- Git 推送可能触发现有仓库 CI；若发现既有 Tag 触发规则，沿用发版预览说明，不能承诺本地模式的推送不会触发 CI。
- 不支持镜像提取或镜像同步；拒绝该操作时不要先打 Tag 或运行构建。
