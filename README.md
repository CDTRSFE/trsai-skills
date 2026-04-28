# trsai-skills

TRS 前端团队 AI 规则与技能集。脚手架项目已内置 ESLint、stylelint、Prettier 和 commit 阶段校验，本仓库只保留 AI 每次都应遵守的短规则，以及需要上下文判断或工具执行的条件技能。

## 文件分工

| 位置 | 用途 |
|------|------|
| `AGENTS.md` | Codex 常驻项目规范，放短规则 |
| `CLAUDE.md` | Claude Code 项目记忆入口，通过 `@AGENTS.md` 复用同一套规则 |
| `skills/*/SKILL.md` | 条件触发技能，处理需求澄清、接口、表单、Store、组件、样式、发版和 Review |
| `docs/conventions/*` | 团队规范参考，基础格式和风格优先交给脚手架校验 |
| `.codex-plugin/plugin.json` | Codex 插件声明，技能目录指向 `./skills/` |
| `.claude-plugin/marketplace.json` | Claude skills 安装声明 |

## Claude Code 使用

Claude Code 读取当前项目的 `CLAUDE.md`，不会直接读取 `AGENTS.md`。推荐做法：

1. 在当前要开发的业务项目中打开 Claude Code，不要把 `trsai-skills` 当作业务项目打开。
2. 安装本仓库 skills：

```bash
npx skills add CDTRSFE/trsai-skills --global
```

3. 业务项目如已有 `AGENTS.md`，在项目根目录放一个很薄的 `CLAUDE.md`：

```md
@AGENTS.md

## Claude Code 补充

- 通用规则维护在 `AGENTS.md`，Claude Code 通过本文件导入。
```

4. Claude 专属补充才写在 `CLAUDE.md`；通用团队规则优先维护在 `AGENTS.md`。

## Codex 使用

Codex CLI / App 默认读取 `AGENTS.md`。推荐做法：

1. 把团队通用规则放到 Codex 全局配置，一台电脑做一次即可：

```bash
mkdir -p ~/.codex
cp /path/to/trsai-skills/AGENTS.md ~/.codex/AGENTS.md
```

2. 在当前要开发的业务项目中打开 Codex CLI 或 Codex App。
3. 业务项目特殊规则写在该项目根目录的 `AGENTS.md`；子目录强约束可用 `AGENTS.override.md`。
4. 如 Codex 环境支持本地插件源，可加载本仓库的 `.codex-plugin/plugin.json`，技能目录已指向 `./skills/`。

验证是否读取规则，可直接问：

```text
请总结当前加载的 AGENTS.md 项目规范，并说明你会如何处理验证。
```

## Agent 与 Skill 分工

- `AGENTS.md` / `CLAUDE.md`：常驻短规则，每次都应遵守。
- `skills/*/SKILL.md`：特定场景才触发，避免把基础格式、命名、模板细节都做成 skill。
- Superpowers：负责规划、TDD、系统调试、验证、请求代码审查等流程纪律。
- TRS skills：负责团队领域规范、前端实现判断、发版工具和收尾审查。

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

## 推荐提示词

```text
分析这个需求，结合 Superpowers 的规划/验证流程，并按 TRS 前端技能规范给出实现方案。
```

```text
请用 TRS Code Review 检查本次改动，并说明验证情况。
```

Superpowers 结合方式见 `docs/superpowers-codex.md`。

## 更新规范

- 每次都要遵守的短规则：改 `AGENTS.md`。
- Claude Code 入口或专属补充：改 `CLAUDE.md`。
- 特定场景技能：改 `skills/<skill-name>/SKILL.md`。
- 可被 lint/stylelint/commit 校验覆盖的规范：改 `docs/conventions/*` 或脚手架规则。
- Codex 插件元信息：改 `.codex-plugin/plugin.json`。
- Claude skills 安装声明：改 `.claude-plugin/marketplace.json`。

```bash
npx skills update trsai-skills --global
```

## 目录结构

```text
AGENTS.md                 ← Codex 常驻项目规范
CLAUDE.md                 ← Claude Code 项目记忆入口，导入 AGENTS.md
skills/
  <skill-name>/
    SKILL.md              ← 条件触发技能
docs/
  conventions/            ← 团队规范参考文档
.codex-plugin/
  plugin.json             ← Codex 插件声明
.claude-plugin/
  marketplace.json        ← Claude 插件声明
```
