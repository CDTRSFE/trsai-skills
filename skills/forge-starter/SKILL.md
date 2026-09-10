---
name: forge-starter
description: Use when the user wants to create, scaffold, initialize, or generate a new Vue/Vite front-end project, 前端项目创建, or 项目初始化.
version: 0.1.0
---

# Forge Starter

## 概览

根据用户需求创建 Vue/Vite 前端项目。确认项目目录名后，使用 `vite-tpl` 文档中的命令生成项目目录，并在成功后告诉用户如何初始化、安装依赖和启动开发服务。

项目模板地址：https://github.com/CDTRSFE/vite-tpl

## 运行环境

- 推荐 Node.js `20.9.0+`。
- 生成的项目使用 `pnpm`，不要改用 npm/yarn，除非用户明确要求。
- 本 skill 可在 Codex、Claude Code、OpenCode 等支持读取 `SKILL.md` 的 Agent 中使用。

## 创建前确认

创建前确认或推断以下信息：

1. 项目目录名，例如 `my-project`。
2. 目标目录是否已存在。

项目目录名规则：

1. 如果用户明确给出目录名，直接使用。
2. 如果用户没有明确给出目录名，但可以从需求中推断，生成一个 kebab-case 的目录名并直接使用，不要再让用户选择或确认。
3. 根据需求生成的目录名最多包含 3 个英文单词，例如 `chongqing-monitor`、`opinion-monitor`，不要生成过长目录名。
4. 如果无法从需求中推断目录名，直接使用默认目录名 `my-project`，不要再询问用户输入。

确定目录名后，必须检查目标目录是否已存在。如果目标目录已存在且非空，不要覆盖，先询问用户如何处理。

## 创建命令

`vite-tpl` 文档指定的创建方式：

```shell
npx degit CDTRSFE/vite-tpl my-project
```

执行时将 `my-project` 替换为用户指定的目录名：

```shell
npx degit CDTRSFE/vite-tpl <project-dir>
```

命令成功后进入目录并初始化 Git：

```shell
cd <project-dir>
git init
```

不要默认执行依赖安装或启动服务，除非用户明确要求；创建完成后把后续命令告诉用户即可。

## 成功后的用户提示

创建成功后，用中文告诉用户项目已创建，并给出后续步骤：

```shell
cd <project-dir>
pnpm i
pnpm dev
```

同时补充：

- 推荐 Node.js `20.9.0+`。
- 项目使用 `pnpm`，不要改用 npm/yarn，除非用户明确要求。

## 模板能力速查

`vite-tpl` 包含：

- Vue 3、Vite、TypeScript
- ant-design-vue
- axios
- pnpm
- UnoCSS、Less
- Pinia
- VueUse
- unplugin-vue-components
- unplugin-auto-import
- vite-plugin-import-icons
- ESLint、Stylelint、Prettier
- Vitest、@vue/test-utils

## 示例

用户：创建一个叫 `demo-app` 的项目。

执行：

```shell
npx degit CDTRSFE/vite-tpl demo-app
cd demo-app
git init
```

回复用户：

```text
项目 demo-app 已创建。后续可以执行：

cd demo-app
pnpm i
pnpm dev
```

## 常见错误

| 错误 | 正确做法 |
| --- | --- |
| 创建命令写成 npm create vite | 使用 `npx degit CDTRSFE/vite-tpl <project-dir>` |
| 默认执行 `pnpm i` | 只在用户明确要求时执行，否则只告知命令 |
| 目标目录非空仍覆盖 | 停止并询问用户 |
| 忽略启动说明 | 创建成功后必须告诉用户 `cd`、`pnpm i`、`pnpm dev` |
