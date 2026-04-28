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

## 推荐组合方式

| 场景 | TRS 侧 | Superpowers |
| --- | --- | --- |
| 模糊前端需求 | `ai-collaboration` 补齐页面、接口、交互、权限和验收上下文 | `superpowers:brainstorming`、`superpowers:writing-plans` |
| 接口联调 | `api-integration` | `superpowers:test-driven-development` |
| 表单开发 | `form-validation` | `superpowers:test-driven-development` |
| 状态设计 | `pinia-store-design` | `superpowers:brainstorming` |
| 组件拆分 | `vue-component-design` | `superpowers:brainstorming`、`superpowers:writing-plans` |
| 样式/布局判断 | `css-patterns` | 按需使用 |
| 完成开发准备交付 | `trs-code-review` | `superpowers:verification-before-completion`、`superpowers:requesting-code-review` |
| 发版打 tag | `git-tag-release` | `superpowers:verification-before-completion` |

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

## 推荐提示词

```text
请先用 ai-collaboration 补齐 TRS 前端需求信息，再结合 superpowers:writing-plans 输出可执行计划。
```

```text
请用 TRS Code Review 检查本次改动，并结合 verification-before-completion 说明验证结果。
```

## 维护建议

- 新增 skill 前先判断：它是否需要上下文判断、流程方法或工具执行？如果只是格式/命名/基础规范，优先放到脚手架校验或 `docs/conventions/*`。
- 每次都要遵守的短规则放到 `AGENTS.md`。
- Review/验收规则优先维护在 `skills/trs-code-review/SKILL.md`，不要分散到每个技能里。
- Codex 侧 `.codex-plugin/plugin.json` 的 `skills` 指向 `./skills/`，无需逐个维护技能列表。
- Claude 侧 `.claude-plugin/marketplace.json` 需要维护显式技能列表。
