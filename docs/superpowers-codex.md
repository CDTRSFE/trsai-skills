# Codex + Superpowers 接入建议

本仓库同时兼容 Claude 插件格式和 Codex 插件格式：

- 常驻规范：`AGENTS.md`
- Claude：`.claude-plugin/marketplace.json`
- Codex：`.codex-plugin/plugin.json`
- 技能目录：`skills/*/SKILL.md`
- 规范参考：`docs/conventions/*`

## 分工原则

TRS 脚手架项目已内置 ESLint、stylelint、Prettier 和 commit 阶段校验，所以不要把可自动检查的行业/团队基础规范都做成 skill。

- `AGENTS.md`：每次默认遵守的短规则。
- `skills/*/SKILL.md`：需要判断、上下文或工具执行的场景。
- `docs/conventions/*`：规范参考和团队约定说明。
- Superpowers：规划、TDD、系统化调试、验证、代码审查流程。
- `chrome-devtools-mcp`：打开真实 Chrome 页面收集运行时证据，例如页面状态、Console、Network、截图和性能信息。
- `trs-code-review`：TRS 前端团队收尾审查清单。

## 标准开发流程

复杂需求、新页面、新组件体系、跨多个模块的改动，默认按下面流程推进：

```text
brainstorming -> writing-plans -> 执行 -> review
```

### 1. brainstorming：产出设计

`superpowers:brainstorming` 负责把模糊想法收敛成设计，不直接写代码。设计文档通常保存到：

```text
docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md
```

设计阶段重点明确：

- 业务目标、功能范围和不做的边界。
- 页面结构、组件边界、交互规则、状态归属。
- 接口、表单、权限、异常态、空态和加载态。
- 验收标准和验证方式。

如果用户给的信息不足，先用 `ai-collaboration` 给出 TRS 前端信息清单，再进入 brainstorming。

### 2. writing-plans：结合 TRS skills 产出实施计划

`superpowers:writing-plans` 负责把设计转成可执行计划。计划文档通常保存到：

```text
docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md
```

这一阶段应根据任务类型把 TRS skills 的要求写进计划：

- 接口请求、loading、error、empty、重试、防重复提交：结合 `api-integration`。
- 新增/编辑表单、校验、回显、提交和重置：结合 `form-validation`。
- 跨组件共享状态、异步 action、缓存或刷新保留：结合 `pinia-store-design`。
- 新组件、组件拆分、Props/Emits、composable 抽取：结合 `vue-component-design`。
- 样式编写、样式调整、UnoCSS 与 Less 取舍、样式覆盖：结合 `css-patterns`。
- 发版、tag、版本号：结合 `git-tag-release`。

计划里应写清楚要改哪些文件、每个文件负责什么、具体实现步骤、验证命令、是否需要浏览器运行时验证。

### 3. 执行：按计划落地

执行阶段优先按计划直接改代码。若计划已经覆盖对应领域，不需要重复调用同一个 TRS skill。

如果执行中发现计划外问题，例如原计划没涉及 Store 但实际需要跨组件共享状态，或样式方案需要 `:deep()` / CSS 变量兜底，应暂停补充调用对应 TRS skill，再继续实现。

### 4. review：验证后收尾审查

完成开发后先用 `superpowers:verification-before-completion` 做验证，再用 `trs-code-review` 按 TRS 团队标准检查 diff、功能逻辑、Vue/TS/样式/API/表单/Store 和交付质量。

## 小需求轻量流程

小型 bug、文案、类型、配置、样式微调或低风险重构，不强制产出完整 spec/plan。

- bug 修复：用 `superpowers:systematic-debugging` 先查根因，再做最小修复和验证。
- 行为改动或重构：优先用 `superpowers:test-driven-development` 保护行为；没有测试条件时说明原因并给出替代验证。
- 涉及样式、接口、表单、Store、组件拆分时，仍按需调用对应 TRS skill。
- 完成后说明实际验证；用户要求验收或提交前检查时使用 `trs-code-review`。

## 浏览器运行时验证

开发完成后不要只停在 `build` 通过。涉及页面、组件、样式、交互、接口联调或性能问题的改动，应优先使用 `chrome-devtools-mcp` 打开真实页面检查证据：

- 页面路径是否可访问，首屏是否正常渲染。
- Console 是否有新增 error / warning。
- 核心操作是否能完成，例如查询、提交、弹窗、分页、状态切换。
- Network 中关键请求的地址、方法、参数、状态码和响应结构是否符合预期。
- 主要布局是否有明显错位、遮挡、溢出；性能问题需结合 trace 或性能面板信息。

纯文档、纯类型、脚本配置、无 UI/运行时影响的改动不强制浏览器验证，但最终回复或 Review 结果需要说明判断理由。

## 冲突处理原则

1. 用户明确指令最高优先级。
2. 脚手架自动校验优先于文档描述，文档落后时应更新文档或脚手架规则。
3. `AGENTS.md` 负责常驻短规范。
4. TRS skills 负责团队业务上下文、实现判断和收尾审查。
5. Superpowers 负责流程纪律，例如先澄清、先写计划、先写测试、先验证。
6. `chrome-devtools-mcp` 只负责真实浏览器证据，不替代 lint、typecheck、单测、构建或团队规范审查。

## 维护建议

- 新增 skill 前先判断：它是否需要上下文判断、流程方法或工具执行？如果只是格式/命名/基础规范，优先放到脚手架校验或 `docs/conventions/*`。
- 每次都要遵守的短规则放到 `AGENTS.md`。
- Review/验收规则优先维护在 `skills/trs-code-review/SKILL.md`，不要分散到每个技能里。
- Codex 侧 `.codex-plugin/plugin.json` 的 `skills` 指向 `./skills/`，无需逐个维护技能列表。
- Claude 侧 `.claude-plugin/marketplace.json` 需要维护显式技能列表。
