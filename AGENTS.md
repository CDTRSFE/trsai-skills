# TRS 前端 Codex 常驻规范

本文件是 Codex 在本仓库中的默认项目指令。TRS 脚手架项目已内置 ESLint、stylelint、Prettier 和 commit 阶段校验；这里仅保留 AI 每次都应遵守的短规则。

## 基础协作

- 默认使用中文沟通，回答简洁、直接、可执行。
- 修改代码前先查看现有同类实现，优先沿用项目已有结构、命名和风格。
- 不要为了小改动制造复杂流程；明确的小型修改直接执行。
- 涉及复杂需求、实现计划、Bug 排查、完成验收时，优先匹配 Superpowers 对应流程技能。
- 完成前必须说明已执行的验证；未验证时明确说明原因和建议验证命令。
- 开发流程分工：Superpowers 负责“怎么分析和验证”，TRS skills 负责“按团队规范怎么写”，`chrome-devtools-mcp` 负责“打开真实页面检查证据”。
- 涉及页面、组件、样式、交互、接口联调或性能问题的改动，完成后应优先用 `chrome-devtools-mcp` 做浏览器运行时验证；纯文档、纯类型、脚本配置、无 UI/运行时影响的改动可不做，但需说明原因。
- 浏览器运行时验证重点关注：页面是否能打开、Console 是否有新增错误、核心交互是否可完成、关键 Network 请求参数/响应是否符合预期、主要布局是否明显错位。

## Vue / TypeScript

- Vue 组件默认使用 Vue 3、`<script setup lang="ts">` 和组合式 API。
- 自研组件在模板中使用 PascalCase；第三方组件按项目约定前缀使用，例如 `a-`、`van-`、`icons-`。
- TypeScript 类型、接口、组件名使用 PascalCase；变量和函数使用 camelCase；常量使用 UPPER_SNAKE_CASE。
- 避免 `any`、魔法字符串和过度泛化；优先用清晰的业务类型表达数据结构。

## 样式与自动导入

- 模板布局、间距、尺寸、颜色、排版、交互状态优先使用 UnoCSS。
- 只有 UnoCSS 不适合表达时，再使用 `<style scoped>`、`<style module>` 或 Less。
- 不要手动 import 已由 `unplugin-auto-import` 或 `unplugin-vue-components` 自动注入的 API 和组件。
- Pinia、VueUse 等是否需要手动 import，以具体项目脚手架配置为准。

## Skill 使用边界

- 模糊需求使用 `ai-collaboration` 补齐信息。
- 接口、表单、Store、组件拆分、复杂样式、发版分别使用对应 skill。
- 用户要求审查、提交前检查、MR/PR 前检查、完成后验收时，使用 `trs-code-review`。
- 基础格式、命名、模板、样式细节优先相信脚手架 lint/stylelint/commit 校验，不为这些规则单独加载 skill。
