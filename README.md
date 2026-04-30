# trsai-skills

TRS 前端团队 AI 规则与技能集。脚手架项目已内置 ESLint、stylelint、Prettier 和 commit 阶段校验，本仓库只保留 AI 每次都应遵守的短规则，以及需要上下文判断或工具执行的条件技能。

## Claude Code 使用

新同事在本机做一次：

1. 全局安装本仓库 skills：

```bash
npx skills add CDTRSFE/trsai-skills --global
```

2. 安装 Claude Code 全局记忆：

```bash
mkdir -p ~/.claude
test -f ~/.claude/CLAUDE.md || curl -L https://raw.githubusercontent.com/CDTRSFE/trsai-skills/main/CLAUDE.md -o ~/.claude/CLAUDE.md
```

3. 重新打开 Claude Code，或执行 `/memory` 检查是否加载了 `~/.claude/CLAUDE.md`。

说明：

- `npx skills add` 只安装 skills，不会安装 `CLAUDE.md`。
- `CLAUDE.md` 给 Claude Code 用；`AGENTS.md` 给 Codex 用。
- 如果本机已有 `~/.claude/CLAUDE.md`，上面的命令不会覆盖；手动把本仓库 [CLAUDE.md](CLAUDE.md) 的内容合并进去。
- Claude Code 记忆文件位置参考：[Anthropic 文档](https://code.claude.com/docs/zh-CN/memory)。

## Codex 使用

Codex CLI / App 默认读取 `AGENTS.md`。推荐做法：

1. 如你的 Codex 环境支持 `skills` 安装器，优先直接用：

```bash
npx skills add CDTRSFE/trsai-skills --global --yes
```

更新时直接执行：

```bash
npx skills update trsai-skills --global --yes
```

说明：

- 通过 `npx skills add/update` 安装到 Codex 时，skills 安装器实际通常会把 skill 落到 `~/.agents/skills/`，Codex 会从这里识别，而不一定写入 `~/.codex/skills/`。

2. 把团队通用规则放到 Codex 全局配置，一台电脑做一次即可：

```bash
mkdir -p ~/.codex
cp /path/to/trsai-skills/AGENTS.md ~/.codex/AGENTS.md
```

3. 在当前要开发的业务项目中打开 Codex CLI 或 Codex App。
4. 业务项目特殊规则写在该项目根目录的 `AGENTS.md`；子目录强约束可用 `AGENTS.override.md`。

验证是否读取规则，可直接问：

```text
请总结当前加载的 AGENTS.md 项目规范，并说明你会如何处理验证。
```

## 技能列表

| 技能 | 触发场景 |
|------|---------|
| `trs-development-preflight` | 开发前置检查，判断流程边界、补齐必要上下文，并声明后续 Superpowers 流程和 writing-plans 要结合的 TRS skills |
| `api-integration` | 封装 HTTP 请求、设计 API 层、处理错误和加载状态 |
| `css-patterns` | 任意页面或组件样式编写/调整、样式覆盖、局部布局、响应式、z-index、UnoCSS 与 CSS/Less 取舍 |
| `form-validation` | 新增/编辑表单、表单提交、校验规则（Ant Design Vue / Vant） |
| `git-tag-release` | 打 tag、发版、推 RC tag、管理 package.json tag 前缀 |
| `pinia-store-design` | 决定是否建 store、设计 store 结构、跨组件状态共享 |
| `vue-component-design` | 设计新组件、重构组件、组件拆分策略 |
| `trs-code-review` | TRS 前端代码审查、提交前检查、MR/PR 前检查、完成验收 |

## 标准开发流程

识别到开发类需求、新页面、新组件体系或跨接口/表单/Store/权限的改动时，先使用 `trs-development-preflight` 判断 TRS 流程边界和领域 skill 路由，再按下面流程推进：

```text
trs-development-preflight -> brainstorming -> writing-plans -> 执行 -> chrome-devtools-mcp -> review
```

- `brainstorming`：产出需求 / 设计文档，明确目标、范围、交互、数据流、组件边界和验收标准。
- `writing-plans`：结合 TRS skills 产出实施计划，必须声明 `Required TRS skills`，例如接口用 `api-integration`，表单用 `form-validation`，样式用 `css-patterns`，Store 用 `pinia-store-design`，组件拆分用 `vue-component-design`。
- 执行：按计划修改代码；如果遇到计划外的新领域问题，再补充调用对应 TRS skill。
- `chrome-devtools-mcp`：涉及页面、组件、样式、交互、接口联调或性能问题时，按计划完成浏览器运行时验证。
- `review`：完成验证后用 `trs-code-review` 做 TRS 前端收尾审查。

轻量例外只适用于明确 bug 修复、纯文案、纯类型、纯配置、纯脚本、纯文档等非需求/非功能任务；不得用“改动很小”跳过完整流程。样式调整若属于需求、功能或页面体验改造，仍按完整流程执行。处理轻量任务时应先确认范围或根因，按需调用领域 skill，直接修改并说明验证结果。

Superpowers 结合方式见 `docs/superpowers-codex.md`。

## 更新规范

- Codex 常驻短规则：改 `AGENTS.md`。
- Claude Code 全局记忆模板：改 `CLAUDE.md`。
- 特定场景技能：改 `skills/<skill-name>/SKILL.md`。
- 可被 lint/stylelint/commit 校验覆盖的规范：优先改脚手架规则；若对应 skill 需要读取团队规范，维护该 skill 的 `references/`。
- Codex 插件元信息：改 `.codex-plugin/plugin.json`。
- Claude skills 安装声明：改 `.claude-plugin/marketplace.json`。

## 目录结构

```text
AGENTS.md                 ← Codex 常驻项目规范
CLAUDE.md                 ← Claude Code 全局记忆模板
skills/
  <skill-name>/
    SKILL.md              ← 条件触发技能
docs/
  superpowers-codex.md    ← Codex + Superpowers 协作流程说明
.codex-plugin/
  plugin.json             ← Codex 插件声明
.claude-plugin/
  marketplace.json        ← Claude 插件声明
```
