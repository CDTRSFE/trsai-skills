# Vue 约定参考

本文件保存团队 Vue 约定的参考内容。脚手架项目已有 ESLint、Prettier 和提交校验，能自动检查的规则优先交给工具。

## `<script setup>` 组织

推荐顺序：

1. 类型定义：`interface` / `type`
2. Props / Emits / Model
3. 响应式状态：`ref` / `reactive`
4. 计算属性：`computed`
5. 监听：`watch` / `watchEffect`
6. 方法：事件处理、业务函数、请求函数
7. 生命周期和清理逻辑

## 组件与模板

- 自研组件使用 PascalCase。
- 第三方组件按项目约定前缀使用，例如 `a-`、`van-`、`icons-`。
- 普通 HTML 非 void 元素不要自闭合。
- `v-for` 必须有稳定 key。
- 避免同一个元素同时写 `v-if` 和 `v-for`。
- 有 slot 内容的组件使用成对标签。

## 自动导入

- 不要手动 import 已由 `unplugin-auto-import` 或 `unplugin-vue-components` 注入的 API 和组件。
- Vue 核心 Composition API、Vue Router API、自动注册组件以项目配置为准。
- Pinia、VueUse 是否自动导入，以具体项目脚手架配置为准。

## 组件设计

详细组件拆分、Props/Emits、composable 抽取仍使用 `vue-component-design` 技能。
