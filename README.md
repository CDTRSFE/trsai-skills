# trsai-skills

TRS 前端团队 Claude Code 技能集。覆盖开发规范、工作流、组件设计、样式约定等场景，安装后 AI 在对话中自动感知并应用对应规范。

## 安装

安装到当前项目：

```bash
npx skills add CDTRSFE/trsai-skills
```

全局安装（所有编辑器、所有项目均可用）：

```bash
npx skills add CDTRSFE/trsai-skills --global
```

## 技能列表

| 技能 | 触发场景 |
|------|---------|
| `ai-collaboration` | 收到模糊需求时，展示结构化信息清单，禁止直接生成 |
| `api-integration` | 封装 HTTP 请求、设计 API 层、处理错误和加载状态 |
| `css-layout-patterns` | 页面布局、响应式设计、常见 CSS 布局问题 |
| `css-style-conventions` | 组件样式、z-index、样式穿透、Code Review |
| `form-validation` | 新增/编辑表单、表单提交、校验规则（Ant Design Vue / Vant） |
| `frontend-debugging` | 排查 UI 渲染、状态异常、网络请求、样式错乱等 bug |
| `frontend-performance` | 页面加载慢、渲染卡顿、打包体积优化 |
| `git-tag-release` | 打 tag、发版、推 RC tag、管理 package.json tag 前缀 |
| `git-workflow` | 创建分支、提交代码、发起 MR、Code Review、处理冲突 |
| `pinia-store-design` | 决定是否建 store、设计 store 结构、跨组件状态共享 |
| `script-setup-structure` | 组件 script setup 内部代码块顺序与组织规范 |
| `typescript-naming-conventions` | 命名规范、类型编写规范、Code Review |
| `vue-auto-imports` | 生成代码时的自动导入白名单，禁止手动 import 已注入的 API |
| `vue-component-design` | 设计新组件、重构组件、组件拆分策略 |
| `vue-template-conventions` | 模板书写规范、组件标签格式、属性顺序、v-for/v-if 规则 |

## 使用方式

安装后无需手动操作。Claude 在对话中识别到匹配场景会自动应用对应规范。

也可以手动触发：

```
/git-workflow
/vue-component-design
/api-integration
```

## 更新规范

**规范维护者**：修改对应 `skills/<skill-name>/SKILL.md`，提交推送到 GitHub：

```bash
git add . && git commit -m "feat: 更新xxx规范" && git push
```

**团队成员**：执行以下命令拉取最新版本（只更新本包，不影响其他 skills）：

```bash
npx skills update trsai-skills --global
```

## 目录结构

```
skills/
  <skill-name>/
    SKILL.md        ← 规范内容（Claude 读取并执行）
    scripts/        ← 可选：需要运行的脚本
.claude-plugin/
  marketplace.json  ← 插件声明
```
