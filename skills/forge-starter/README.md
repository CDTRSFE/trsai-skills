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

Agent 会自动加载本 skill 并执行对应流程。

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
