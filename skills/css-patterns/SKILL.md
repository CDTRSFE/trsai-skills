---
name: css-patterns
description: 在需要选择页面布局方案、处理响应式、大屏布局、复杂样式穿透、z-index 层级或 UnoCSS 与 CSS/Less 取舍时使用。
---

# CSS 布局与样式决策

## 定位

脚手架项目已有 stylelint、ESLint、Prettier 和提交校验。本技能不重复格式规则，只处理需要判断的布局和样式方案。

## 何时使用

- 普通 PC 项目和大屏项目的布局方案选择。
- flex/grid/定位/滚动容器等结构性布局问题。
- UnoCSS、`<style scoped>`、Less、CSS 变量之间的取舍。
- z-index 层级、弹层、吸顶、第三方组件样式覆盖。
- 样式问题无法通过 formatter/stylelint 自动解决。

## 决策原则

1. 优先用 UnoCSS 表达布局、间距、尺寸、颜色、排版、状态和响应式。
2. UnoCSS 不适合表达时，再写 CSS/Less：`:deep()`、伪元素、keyframes、CSS 变量、复杂 grid area。
3. 页面主结构优先 Grid，局部排列优先 Flex。
4. 大屏项目优先明确设计稿基准、缩放策略、图表容器自适应和最小可视范围。
5. 覆盖第三方组件样式时，先缩小作用域，再使用 `:deep()`，避免全局污染。

## 常见方案

| 场景 | 推荐 |
| --- | --- |
| 顶部 + 内容区 + 底部 | flex column，内容区 `flex-1 min-h-0 overflow-auto` |
| 侧边栏 + 内容区 | grid 或 flex，内容区必须处理 `min-w-0` |
| 卡片列表 | grid + `auto-fill/minmax` 或 UnoCSS grid 工具类 |
| 表格页 | 外层 column，筛选区固定，表格区 `flex-1 min-h-0` |
| 大屏看板 | 固定基准尺寸 + 缩放容器 + 图表 resize 监听 |
| 弹层覆盖 | 遵循组件库层级，局部提升 z-index，不写魔法大数 |

## 参考文档

- 详细样式约定见 `docs/conventions/style.md`。
- 常驻规则见 `AGENTS.md`。
- 收尾检查见 `trs-code-review`。
