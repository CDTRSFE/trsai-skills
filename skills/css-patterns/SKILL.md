---
name: css-patterns
description: 在规划或编写页面/组件样式、布局、响应式、UnoCSS/Less 取舍、样式覆盖、z-index 层级时使用；TRS 开发计划涉及样式任务时必须使用。
---

# CSS 布局与样式决策

## 定位

脚手架项目已有 stylelint、ESLint、Prettier 和提交校验。本技能不重复格式规则，只处理需要判断的布局和样式方案。

只要任务涉及样式编写或样式调整，不管是普通卡片、局部组件细节，还是复杂页面布局，都应先使用本技能判断方案，而不是只在大屏或大型布局场景才使用。

## writing-plans 阶段要求

当本技能用于实施计划阶段时，计划必须写清：

- 本技能约束适用于哪些任务。
- 计划的 `Required TRS skills` 中必须列出 `css-patterns`；若同时涉及组件、接口、表单或 Store，也必须列出对应 TRS skill。
- 需要创建或修改的文件。
- 样式方案：UnoCSS、`<style scoped>` / Less、`:deep()`、CSS 变量、响应式和 z-index 处理。
- 样式任务开发中优先使用 `pnpm lint:stylelint` / `pnpm lint` 和浏览器布局检查；不得默认安排 `pnpm build`，只有用户明确确认后才执行。
- 若任务涉及页面、组件、样式、交互或接口联调，计划中必须增加 `Browser Runtime Verification` 小节，声明使用 `chrome-devtools-mcp`，并列出页面路径、核心操作、Console、Network、布局检查点。

## 使用步骤

1. 先读取 `references/style.md`，按团队样式约定判断实现方式。
2. 再决定优先使用 UnoCSS，还是补充 `<style scoped>` / Less / `:deep()` / CSS 变量。
3. 如果问题不只是样式写法，而是页面运行时表现异常，再配合 `references/debugging-performance.md` 和浏览器验证处理。

## 何时使用

- 任何页面或组件的样式编写、样式调整和样式重构。
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

- 开始处理样式前，先读取 `references/style.md`。
- 样式问题涉及运行时异常、性能或浏览器验证时，读取 `references/debugging-performance.md`。
- 通用流程使用 Superpowers；build 触发规则以本技能和 `trs-code-review` 为准。
- 收尾检查见 `trs-code-review`。
