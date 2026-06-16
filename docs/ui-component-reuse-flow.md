# UI 组件复用图谱流程说明

本文档给维护者查看，安装 skill 的使用者不需要主动阅读。实际执行规则以 `skills/ui-component-reuse/SKILL.md` 为准。

## 总流程

```mermaid
flowchart TD
  A[收到 UI / 组件 / 设计稿开发需求] --> B[识别页面结构和业务区域]
  B --> C[检查 ant-design-vue 是否已有能力]
  C --> D{是否已有 antd 组件可覆盖?}
  D -->|是| E[优先使用 ant-design-vue]
  E --> F{是否只是样式差异?}
  F -->|是| G[使用 styles 公共重置或局部样式覆盖]
  F -->|否| H[组合 antd 组件并补业务逻辑]
  D -->|否| I[读取 docs/component-map.md]
  I --> J{项目公共组件是否可复用?}
  J -->|可直接用| K[复用 src/components 公共组件]
  J -->|可组合/轻扩展| L[组合或轻量扩展公共组件]
  J -->|不可用| M[判断是否值得抽组件]
  M --> N{有独立职责/Props/Emits/状态/复用价值?}
  N -->|否| O[留在页面内作为普通结构或样式]
  N -->|是| P{是否明确跨页面复用?}
  P -->|是| Q[放入 src/components]
  P -->|否或不确定| R[放入 src/views/**/components]
  G --> S[开发后更新 docs/component-map.md]
  H --> S
  K --> S
  L --> S
  Q --> S
  R --> S
  O --> S
```

## 设计稿拆组件判断

1. 先拆页面区域，不急着新建组件。
2. 对每个区域先判断 ant-design-vue 是否已有组件。
3. 样式差异优先走 `styles` 公共重置或局部覆盖，不因为圆角、间距、颜色不同而新建组件。
4. 再查 `docs/component-map.md`，优先复用项目公共组件。
5. 只有具备独立职责、清晰数据边界、独立状态或明确复用价值时才抽组件。
6. 可跨页面复用放 `src/components`；当前页面专用或不确定放 `src/views/**/components`。

## 初始建图

老项目第一次接入时，运行：

```bash
node skills/ui-component-reuse/scripts/scan-vue-components.mjs /path/to/project
```

脚本会自动创建 `docs/`；当 `docs/component-map.md` 不存在时自动初始化正式索引，存在时不覆盖。
