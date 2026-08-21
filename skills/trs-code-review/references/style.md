# 样式约定参考

脚手架项目已有 stylelint、Prettier 和提交校验。本文件记录 stylelint 无法完全表达的团队判断。

只要在写样式，无论是普通页面、小卡片、组件局部细节，还是复杂布局，都应先按这里的判断处理。不是只有大屏、响应式或大型布局场景才需要关注样式方案。

## UnoCSS 优先

优先用 UnoCSS 处理：

- 布局：flex、grid、positioning
- 间距：margin、padding、gap
- 尺寸：width、height
- 颜色：text、bg、border
- 排版：font-size、font-weight、line-height
- 响应式、hover/focus/disabled、过渡动画

## CSS / Less 适用场景

- `:deep()` 覆盖第三方组件内部结构。
- `::before` / `::after` 伪元素。
- `@keyframes` 动画。
- CSS 变量声明与复杂动态样式。
- UnoCSS 不便表达的 grid area 或复杂选择器。

## 文本溢出审查

审查页面、组件和大屏改动时，必须检查真实业务文案变长后的表现，尤其是列表项、卡片、标题行、说明文案、标签组、图表旁信息和弹窗内容。

- flex / grid 子项承载文本时，文本所在项以及必要父级是否有 `min-w-0`；纵向滚动区域是否有 `min-h-0`。
- 单行文本是否使用 `truncate` 或等价样式，并具备可收缩宽度。
- 多行文本是否明确换行或限制行数；连续英文、URL、数字串是否能用 `break-words` / `overflow-wrap:anywhere` 等策略处理。
- 同一行左侧长文本 + 右侧时间、按钮、状态标签时，左侧是否 `flex-1 min-w-0`，右侧是否 `shrink-0`。
- 是否避免用单纯外层 `overflow-hidden` 掩盖内部布局问题。

## 样式穿透

- 优先缩小父级作用域，再写 `:deep()`。
- 不要写全局污染式覆盖。
- 不要为了覆盖组件库滥用 `!important`。

## z-index

- 优先遵循组件库弹层层级。
- 局部层级只在当前组件作用域内处理。
- 避免魔法大数，例如 `999999`。
