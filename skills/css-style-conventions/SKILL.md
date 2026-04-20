---
name: css-style-conventions
description: 在编写组件样式、处理 z-index、使用样式穿透、或做样式 Code Review 时使用。布局方案参考 css-layout-patterns。
---

# CSS/Less 样式编写规范

## 基本原则

- 组件样式使用 `<style scoped lang="less">`
- **UnoCSS 原子类优先**：布局、间距、排版优先用 UnoCSS，复杂交互样式（动画、伪元素、复杂选择器）才写 Less
- H5 响应式用 `rem` 单位（配合 `lib/rem.js`）

---

## 一、选择器规范

```less
// ✅ 类选择器（推荐）
.user-card { ... }
.main-container { ... }

// ✅ 标签选择器（最多 2 个，且配合类使用）
.user-card span { color: #666; }

// ❌ 禁止通配符选择器
* { box-sizing: border-box; }   // 全局用，不要在组件 scoped 中写

// ❌ 禁止 ID 选择器定义样式
#main-content { ... }

// ❌ 标签选择器超过 2 层
.user-card div p span { ... }   // 用类选择器替代
```

---

## 二、z-index 规范

组件内局部层级可从小值开始（1、2、3…），禁止魔法数字。涉及跨组件的统一层级（弹窗、遮罩、Popover、Toast 等）必须使用全局 `--z-*` 变量。

```less
// ✅ 从小值开始，有意义的递增
.sticky-header { z-index: 1; }
.dropdown-menu { z-index: 2; }
.modal-overlay  { z-index: 3; }
.modal-content  { z-index: 4; }
.toast-message  { z-index: 5; }

// ❌ 禁止魔法数字
.header { z-index: 999; }
.modal  { z-index: 9999; }
.toast  { z-index: 99999; }
```

如需跨组件统一管理，用 CSS 变量（在全局样式中定义）：

```css
/* src/styles/variables.css */
:root {
  --z-dropdown: 100;
  --z-sticky: 200;
  --z-overlay: 300;
  --z-modal: 400;
  --z-popover: 500;
  --z-toast: 600;
}
```

---

## 三、样式穿透（覆盖第三方组件库）

```less
// ✅ 使用 :deep()
.my-table {
  :deep(.ant-table-thead th) {
    background: #f0f4ff;
  }
}

// ❌ 禁止 /deep/ 和 ::v-deep（已废弃）
/deep/ .ant-table-thead th { ... }
::v-deep .ant-table-thead th { ... }
```

---

## 四、!important 使用限制

```less
// ✅ 仅允许在覆盖第三方组件库样式时使用
.custom-button {
  :deep(.ant-btn) {
    border-radius: 8px !important;   // 覆盖 antd 默认值
  }
}

// ❌ 业务代码禁止使用 !important
.main-title {
  font-size: 18px !important;   // 修复层级问题，而不是用 !important
}
```

---

## 五、属性书写顺序

```less
.element {
  // 1. CSS 变量
  --local-color: #333;

  // 2. Less 变量
  @spacing: 16px;

  // 3. 普通属性（布局相关 → 盒模型 → 外观 → 文字）
  display: flex;
  align-items: center;
  position: relative;
  width: 100%;
  height: 48px;
  padding: 0 16px;
  margin: 0 0 8px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #fff;
  color: #333;
  font-size: 14px;
  line-height: 1.5;
  cursor: pointer;
  transition: all 0.2s;

  // 4. 嵌套选择器
  .title { font-weight: 600; }

  // 5. @规则（媒体查询等）
  @media (max-width: 768px) { ... }
}
```

---

## 六、禁止重复属性

```less
// ❌ 同一块内重复声明同一属性
.card {
  padding: 16px;
  color: #333;
  padding: 24px;   // 重复！上面的 padding 无效
}

// ✅ 只保留最终需要的值
.card {
  padding: 24px;
  color: #333;
}
```

---

## 七、属性简写

```less
// ✅ 可合并的属性必须简写
.box {
  margin: 0 16px;              // 而不是 margin-top/bottom: 0; margin-left/right: 16px
  padding: 8px 16px 8px 16px; // 四值都不同时，用全写（但可以简化为 padding: 8px 16px）
  border: 1px solid #e5e7eb;  // 而不是分写 border-width/style/color
  background: #fff url('...') no-repeat center;
}

// ❌ 不必要的分写
.box {
  margin-top: 0;
  margin-right: 16px;
  margin-bottom: 0;
  margin-left: 16px;
}
```

---

## 八、url() 路径引号

```less
// ✅ url() 内路径必须加引号
.bg {
  background-image: url('/images/banner.png');
  background-image: url('@/assets/images/hero.webp');
}

// ❌ 不加引号（部分情况下会解析失败）
.bg {
  background-image: url(/images/banner.png);
}
```

---

## 九、第一层选择器对齐

```vue
<style scoped lang="less">
/* ✅ 第一层选择器与 <style> 顶格对齐，不允许前置缩进 */
.page-container {
    padding: 16px;

    .header {
        margin-bottom: 16px;
    }
}

/* ❌ 第一层选择器有前置缩进 */
  .page-container {
    padding: 16px;
  }
</style>
```

---

## 十、UnoCSS 与 Less 选择原则

| 场景 | 推荐方案 |
|------|---------|
| 布局（flex、grid、gap） | UnoCSS 原子类 |
| 间距（padding、margin） | UnoCSS 原子类 |
| 文字（字号、字重、颜色） | UnoCSS 原子类 |
| 边框、圆角 | UnoCSS 原子类 |
| 动画、过渡 | Less（复杂）或 UnoCSS（简单） |
| 伪类、伪元素 | Less（`&:hover`、`&::before`） |
| 覆盖第三方组件库 | Less（`:deep()`） |
| 响应式媒体查询 | Less（`@media`）或 UnoCSS 前缀（`md:`, `lg:`） |

---

## 十一、图片规范

- 图片提交前必须压缩（推荐 tinypng.com）
- 含文字的图（logo、标题等）必须用 SVG，避免高分屏模糊
- 能用 CSS/SVG/图标实现的效果优先编码，不切图
