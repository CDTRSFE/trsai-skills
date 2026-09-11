# Forge Starter

用于创建 TRS Vue/Vite 前端项目的 Agent Skill。项目模板：https://github.com/CDTRSFE/vite-tpl 。

## 安装

Codex：安装到 `~/.codex/skills`

```shell
npx skills add CDTRSFE/forge-starter --global --agent codex
```

Claude Code：安装到 `~/.claude/skills`

```shell
npx skills add CDTRSFE/forge-starter --global --agent claude-code
```

OpenCode：安装到 `~/.config/opencode/skills`

```shell
npx skills add CDTRSFE/forge-starter --global --agent opencode
```

## 使用

安装后，直接向 Agent 提出创建前端项目的需求，例如：

```text
创建一个叫 ops-admin 的前端项目
```

或：

```text
帮我初始化一个舆情管理前端项目
```

用户未说明工程类型时，优先使用可点击的选择控件：标题为“请问你创建工程的类型”，选项为“1. 大屏”和“2. PC”。展示后等待用户选择，不再追加文字追问。没有可用控件时，才用以下文字询问：

```text
请问你创建工程的类型
1. 大屏
2. PC
```

回复 `1` 或“大屏”选择大屏，回复 `2` 或“PC”（不区分大小写）选择 PC，随后继续。类型已明确时跳过询问，随后展示工程类型、工程名和存放路径。工程名默认 `my-project`，存放路径可由用户指定，未指定时默认放在当前工作目录下。

信息补齐后，Agent 会下载模板、初始化 Git 并自动安装依赖。成功回复提供可点击的工程文件夹链接、模板、Git 与依赖状态及启动命令；省略大屏接入细节、检查通过汇总及非阻塞警告。影响使用的问题仍会如实说明。

PC 和大屏均使用 `npx degit CDTRSFE/vite-tpl <project-dir>` 下载模板。PC 保留默认入口；大屏会在 `App.vue` 根部接入模板自带的 `ScaleLayout`，默认画布为 `1920×1080`、缩放方式为 `fill`，并执行构建验证。画布尺寸和缩放方式可按用户要求调整。

## 更新

Codex：

```shell
npx skills update forge-starter --global --agent codex
```

Claude Code：

```shell
npx skills update forge-starter --global --agent claude-code
```

OpenCode：

```shell
npx skills update forge-starter --global --agent opencode
```
