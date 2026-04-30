---
name: trs-development-preflight
description: 在识别到用户提出 TRS 前端开发需求、功能、新页面、交互改造、接口联调、表单、Store、组件拆分或重构时使用，用于作为开发前置检查，判断流程边界、补齐必要上下文，并声明后续 Superpowers 流程和 writing-plans 必须结合的 TRS 领域 skills；不替代 brainstorming。
---

# TRS 开发需求前置规则

## 定位

本技能是 TRS 前端开发任务的前置检查，不是需求清单模板库，也不替代 Superpowers 后续流程。

它负责在识别到开发类需求时完成三件事：

1. 判断任务是否属于完整开发流程。
2. 补齐继续推进所必需的上下文。
3. 提前声明 `writing-plans` 阶段必须结合哪些 TRS 领域 skills。

本技能只决定“接下来该怎么走”。方案探索、设计收敛和需求文档交给 `superpowers:brainstorming`；实施计划交给 `superpowers:writing-plans`，并在计划阶段结合 TRS 领域 skills；执行后按计划使用 `chrome-devtools-mcp` 做浏览器运行时验证；最后用 `trs-code-review` 收尾审查。

## 何时使用

- 识别到用户提出需求、功能、新页面、交互改造、接口联调、表单、Store、组件拆分或重构。
- 开发前需要判断是否进入 `brainstorming -> writing-plans -> 执行 -> chrome-devtools-mcp -> review`。
- 用户给的信息不足，需要一次性补齐页面、接口、权限、交互、状态或验收边界。
- `writing-plans` 前需要明确本次计划必须结合哪些 TRS 领域 skills。

## 何时不要使用

- 普通问答，不涉及 TRS 前端开发流程判断。
- 纯文档、纯类型、纯配置、纯脚本、纯 skill 文案，且没有业务运行时影响。
- 明确 Bug 修复：优先使用 `superpowers:systematic-debugging` 查根因。
- 用户明确只要求代码审查、提交前检查或验收：使用 `trs-code-review`。
- 用户明确只要求发版、打 tag 或版本号处理：使用 `git-tag-release`。

## TRS 开发流程边界

- 不用“改动大小”判断是否走流程；按任务性质判断。
- 需求、功能、新页面、交互、接口、表单、Store、组件拆分和业务重构，默认按完整流程推进：

```text
trs-development-preflight -> brainstorming -> writing-plans -> 执行 -> chrome-devtools-mcp -> review
```

- `brainstorming` 只负责收敛需求和产出设计，不直接写代码。
- TRS 开发需求必须执行增强版 `brainstorming`，不得以“需求简单”“已有代码可复用”“用户已给一句确认”为理由压缩确认步骤。
- 增强版 `brainstorming` 在写设计文档前，至少完成：现状复述、范围确认、交互确认、数据来源确认、非目标确认、验收标准确认。任一项未确认时，不得写设计文档或进入 `writing-plans`。
- `writing-plans` 必须声明 `Required TRS skills`，并先读取对应 TRS 领域 skill，再把约束写进实施步骤。
- 计划中的每个任务必须标注适用的 TRS skill；执行阶段不得跳过计划中已声明的 skill 约束。
- 涉及页面、组件、样式、交互、接口联调或性能问题时，执行后必须按计划使用 `chrome-devtools-mcp` 完成浏览器运行时验证。
- 明确 Bug 修复必须先用 `superpowers:systematic-debugging` 确认根因，再做最小修复和验证。
- 项目开发完成后，Codex 必须先向用户确认是否提交本次修改；未经用户明确确认，不得自作主张执行 `git add`、`git commit`、`git push` 或创建 PR。
- 纯文档、纯类型、纯配置、纯脚本、纯 skill 文案且无业务运行时影响的任务，可以走轻量流程。

## Required TRS skills 路由

- 组件设计、组件拆分、组件重构、Props/Emits、composable：`vue-component-design`
- 样式、布局、响应式、UnoCSS/Less、样式覆盖、z-index：`css-patterns`
- HTTP 请求、API 层、loading/error/empty、轮询、防重复提交：`api-integration`
- 新增/编辑表单、筛选表单、弹窗表单、校验、提交、回显：`form-validation`
- Pinia、跨组件/跨路由共享状态、全局状态：`pinia-store-design`
- 打 tag、发版、RC tag、版本号、回写 `package.json.tag`：`git-tag-release`
- 代码审查、提交前检查、MR/PR 检查、完成验收：`trs-code-review`

## writing-plans 约束

当任务进入 `superpowers:writing-plans` 时，计划必须包含：

- `Required TRS skills`：列出本次任务涉及的 TRS 领域 skills。
- `Skill constraints`：把每个领域 skill 的关键约束写入对应实施步骤。
- `Files and ownership`：说明要改哪些文件、每个文件负责什么。
- `Validation`：列出 lint、typecheck、单测、运行时验证或不能执行的原因。
- `Browser Runtime Verification`：涉及页面、组件、样式、交互、接口联调或性能问题时必须包含。
- `Commit Confirmation`：开发和验证完成后，必须询问用户是否提交本次修改；用户确认前不得执行提交、推送或 PR 操作。

`Browser Runtime Verification` 需要写清：

- 页面路径。
- 核心操作。
- Console 检查点。
- Network 检查点。
- 布局、遮挡、溢出和响应式检查点。

Codex 不得默认执行 `pnpm build`。只有用户明确确认后才执行；如果判断必须通过 build 才能验证，应先说明必要性并等待确认。

## 与 Superpowers 配合

- 开发类需求：先用本技能判断流程和 TRS skill 路由，再进入 `superpowers:brainstorming`；进入后必须按增强版 `brainstorming` 完成六项确认，不能把一次方案选择当作完整需求确认。
- 需求已清楚但实现复杂：用本技能声明 `Required TRS skills` 后进入 `superpowers:writing-plans`。
- 明确 Bug：跳过本技能，使用 `superpowers:systematic-debugging`。
- 执行完成：先按计划使用 `chrome-devtools-mcp` 做运行时验证，再使用 `superpowers:verification-before-completion` 和 `trs-code-review`，最后询问用户是否提交本次修改；用户明确确认前，不得提交、推送或创建 PR。不要在本技能里做收尾审查。
