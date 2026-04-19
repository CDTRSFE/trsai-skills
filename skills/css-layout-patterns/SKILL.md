---
name: css-layout-patterns
description: CSS 布局与样式架构指导。在处理页面布局、响应式设计、常见 CSS 布局问题时使用。
---

# CSS 布局与样式模式

## 概述

指导选择合适的 CSS 布局方案，提供常见布局模式的实现，帮助解决布局问题。

## 何时激活

- 构建页面布局
- 实现响应式设计
- 解决 CSS 布局问题（对齐、溢出、层叠等）
- 讨论 CSS 架构和组织方式

## 布局方案选择

### Flexbox vs Grid 决策

```
需要的布局是...
├── 一维排列（一行或一列）→ Flexbox
│   ├── 导航栏
│   ├── 按钮组
│   ├── 表单行
│   └── 卡片列表（单行/换行）
│
├── 二维布局（行 + 列同时控制）→ Grid
│   ├── 页面整体结构（header/sidebar/main/footer）
│   ├── 仪表盘（多个面板）
│   ├── 图片画廊
│   └── 复杂的表单布局
│
└── 不确定 → 先用 Flexbox，不够再换 Grid
```

## 常见布局模式

### 1. 管理后台经典布局

```css
/* Grid 实现 */
.admin-layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  grid-template-rows: 64px 1fr;
  grid-template-areas:
    "sidebar header"
    "sidebar main";
  height: 100vh;
}

.header { grid-area: header; }
.sidebar { grid-area: sidebar; overflow-y: auto; }
.main { grid-area: main; overflow-y: auto; padding: 24px; }
```

### 2. 粘性底部（Sticky Footer）

```css
/* 内容不够时 footer 依然在底部 */
.page {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.page-content {
  flex: 1; /* 撑满剩余空间 */
}

.page-footer {
  /* 自然排列在底部 */
}
```

### 3. 等高卡片列表

```css
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.card {
  display: flex;
  flex-direction: column;
}

.card-body {
  flex: 1; /* 内容区撑满，让底部按钮对齐 */
}
```

### 4. 居中方案速查

```css
/* 1. Flexbox 居中（最常用） */
.center-flex {
  display: flex;
  justify-content: center;
  align-items: center;
}

/* 2. Grid 居中（最简洁） */
.center-grid {
  display: grid;
  place-items: center;
}

/* 3. 绝对定位居中（脱离文档流） */
.center-absolute {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}
```

### 5. 响应式断点

```css
/* Mobile First 策略 */

/* 默认：手机（< 768px） */
.container { padding: 16px; }

/* 平板（≥ 768px） */
@media (min-width: 768px) {
  .container { padding: 24px; max-width: 720px; margin: 0 auto; }
}

/* 桌面（≥ 1024px） */
@media (min-width: 1024px) {
  .container { max-width: 960px; }
}

/* 大屏（≥ 1280px） */
@media (min-width: 1280px) {
  .container { max-width: 1200px; }
}
```

## UnoCSS / Tailwind 常用布局速查

```html
<!-- Flexbox 水平居中 -->
<div class="flex items-center justify-center">

<!-- Flexbox 两端对齐 -->
<div class="flex items-center justify-between">

<!-- Grid 三列自适应 -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

<!-- 粘性元素 -->
<div class="sticky top-0 z-10">

<!-- 文字截断 -->
<p class="truncate">            <!-- 单行截断 -->
<p class="line-clamp-2">        <!-- 多行截断 -->

<!-- 滚动容器 -->
<div class="h-full overflow-y-auto">
```

## 常见问题排查

### 元素溢出

```css
/* 问题：文字超出容器 */
/* 原因：长单词/URL 不会自动换行 */
.text-container {
  overflow-wrap: break-word;   /* 长单词换行 */
  word-break: break-all;       /* 更激进的换行 */
}

/* 问题：Flex 子元素不缩小 */
/* 原因：min-width 默认为 auto */
.flex-child {
  min-width: 0;   /* 允许缩小到 0 */
  overflow: hidden;
}
```

### 层叠上下文（z-index）

```css
/* 规范化 z-index 层级 */
:root {
  --z-dropdown: 100;
  --z-sticky: 200;
  --z-overlay: 300;
  --z-modal: 400;
  --z-popover: 500;
  --z-toast: 600;
}

/* ⚠️ 注意：以下属性会创建新的层叠上下文 */
/* transform / filter / opacity<1 / position:fixed/sticky */
/* 子元素再高的 z-index 也无法超越父层叠上下文 */
```

### 滚动穿透

```css
/* 弹窗打开时禁止背景滚动 */
body.modal-open {
  overflow: hidden;
}

/* 移动端可能还需要 */
body.modal-open {
  position: fixed;
  width: 100%;
  top: calc(-1 * var(--scroll-top));
}
```

## CSS 架构建议

| 方案 | Vue 中推荐度 | 场景 |
|------|-------------|------|
| **Scoped Styles** | ⭐⭐⭐⭐⭐ | 默认选择 |
| **UnoCSS/Tailwind** | ⭐⭐⭐⭐⭐ | 快速开发 |
| **CSS Modules** | ⭐⭐⭐⭐ | 需要 JS 中引用类名 |
| **BEM** | ⭐⭐⭐ | 大型团队统一规范 |
| **全局样式** | ⭐⭐ | 仅用于重置/主题变量 |
