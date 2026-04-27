# TypeScript 约定参考

脚手架项目已有 ESLint 与 TypeScript 校验，本文件只记录团队偏好。

## 命名

| 类型 | 规则 | 示例 |
| --- | --- | --- |
| 组件名 | PascalCase | `UserTable` |
| interface / type | PascalCase，不加 `I` 前缀 | `UserInfo` |
| 变量 / 函数 | camelCase | `userList`、`getUserList` |
| 常量 | UPPER_SNAKE_CASE | `MAX_PAGE_SIZE` |
| boolean | `is` / `has` / `can` / `should` 前缀 | `isVisible` |
| 事件处理 | `handle` 前缀 | `handleSubmit` |

## 类型边界

- 接口响应、表单模型、Props、Emits 应有明确类型。
- 避免 `any`、过宽类型和不必要的类型断言。
- 复杂联合值优先定义字面量联合类型或枚举映射。
- 不要在多个文件重复定义同一业务类型。
