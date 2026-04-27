# trsai-skills

TRS 前端团队 AI 技能集。脚手架项目已内置 ESLint、stylelint、Prettier 和 commit 阶段校验，因此本仓库只保留 AI 真正需要的判断型、工具型和 Review 型技能。

## 三层模型

| 层级 | 位置 | 用途 |
|------|------|------|
| 常驻规范 | `AGENTS.md` | Codex 每次默认遵守的短规则，避免把基础规范都做成 skill |
| 条件技能 | `skills/*/SKILL.md` | 特定场景才触发，例如需求信息清单、接口、表单、Pinia、组件设计、发版 |
| 参考文档 | `docs/conventions/*` | 被脚手架 lint/stylelint/commit 校验覆盖的团队规范参考 |
| 收尾审查 | `skills/trs-code-review/SKILL.md` | 用户要求 review、提交前检查、MR/PR 前检查或完成验收时使用 |

## 适用工具

| 工具 | 入口文件 | 说明 |
|------|---------|------|
| Claude | `.claude-plugin/marketplace.json` | 兼容 Claude skills 安装方式 |
| Codex | `.codex-plugin/plugin.json` | Codex 插件声明，技能目录指向 `./skills/` |
| Superpowers | Codex 已安装的 Superpowers 插件 | 负责规划、TDD、系统调试、验证等过程规范 |

## 安装

### Claude / skills CLI

```bash
npx skills add CDTRSFE/trsai-skills
```

全局安装：

```bash
npx skills add CDTRSFE/trsai-skills --global
```

### Codex

本仓库已提供 Codex 插件入口：

```text
.codex-plugin/plugin.json
```

如果 Codex 环境支持本地插件源，可直接把本仓库作为本地插件加载；如使用 marketplace，则让 source 指向本仓库路径。

## 技能列表

| 技能 | 触发场景 |
|------|---------|
| `ai-collaboration` | 模糊前端需求的信息清单，补齐页面、接口、交互、权限和验收上下文 |
| `api-integration` | 封装 HTTP 请求、设计 API 层、处理错误和加载状态 |
| `css-patterns` | 布局方案、大屏适配、复杂样式、z-index、UnoCSS 与 CSS/Less 取舍 |
| `form-validation` | 新增/编辑表单、表单提交、校验规则（Ant Design Vue / Vant） |
| `git-tag-release` | 打 tag、发版、推 RC tag、管理 package.json tag 前缀 |
| `pinia-store-design` | 决定是否建 store、设计 store 结构、跨组件状态共享 |
| `vue-component-design` | 设计新组件、重构组件、组件拆分策略 |
| `trs-code-review` | TRS 前端代码审查、提交前检查、MR/PR 前检查、完成验收 |

## 已降级为文档/工具校验的内容

这些内容不再单独做 skill：

| 原内容 | 现在位置 | 原因 |
|------|---------|------|
| `<script setup>` 顺序、模板格式、自动导入 | `AGENTS.md`、`docs/conventions/vue.md` | 属于常驻规则或 lint 可检查 |
| TypeScript 命名与类型基础规范 | `AGENTS.md`、`docs/conventions/typescript.md` | 属于基础规范，脚手架已校验大部分问题 |
| CSS/Less 书写细节 | `docs/conventions/style.md`、`css-patterns` | 格式交给 stylelint，判断型样式问题保留 skill |
| Git 提交/MR 基础规范 | `docs/conventions/git.md` | commit 阶段已有团队校验 |
| 通用调试/性能流程 | `docs/conventions/debugging-performance.md`、Superpowers | 系统流程由 Superpowers 负责 |

## 与 Superpowers 结合

建议把 TRS skills 定位为「团队领域规范」，把 Superpowers 定位为「执行流程规范」。

| 开发阶段 | TRS 技能 | Superpowers |
|---------|---------|-------------|
| 需求不清晰 | `ai-collaboration` 补齐 TRS 前端信息 | `superpowers:brainstorming` |
| 输出实现方案 | 相关业务/前端技能 | `superpowers:writing-plans` |
| 新功能 / Bugfix | 相关业务/前端技能 | `superpowers:test-driven-development` |
| 问题排查 | 参考 `docs/conventions/debugging-performance.md` | `superpowers:systematic-debugging` |
| 完成验收 | `trs-code-review` | `superpowers:verification-before-completion`、`superpowers:requesting-code-review` |
| 发版 | `git-tag-release` | `superpowers:verification-before-completion` |

推荐提示词：

```text
分析这个需求，结合 Superpowers 的规划/验证流程，并按 TRS 前端技能规范给出实现方案。
```

```text
请用 TRS Code Review 检查本次改动，并说明验证情况。
```

更多说明见 `docs/superpowers-codex.md`。

## 更新规范

**规范维护者**：

- 每次都要遵守的短规则：改 `AGENTS.md`。
- 特定场景能力：改 `skills/<skill-name>/SKILL.md`。
- 可被 lint/stylelint/commit 校验覆盖的规范：改 `docs/conventions/*` 或脚手架规则。

提交推送：

```bash
git add . && git commit -m "feat: 更新xxx规范" && git push
```

**团队成员**：

```bash
npx skills update trsai-skills --global
```

## 目录结构

```text
AGENTS.md                 ← Codex 常驻项目规范
skills/
  <skill-name>/
    SKILL.md              ← 条件触发技能
docs/conventions/         ← 团队规范参考文档
.codex-plugin/
  plugin.json             ← Codex 插件声明
.claude-plugin/
  marketplace.json        ← Claude 插件声明
```
