---
name: frontend-performance
description: 前端性能优化指导。在处理页面加载慢、渲染卡顿、打包体积大等性能问题时使用。
---

# 前端性能优化

## 概述

系统化的前端性能优化指导，覆盖加载性能、运行时性能和构建优化三个维度。先度量后优化，避免过度优化。

**核心原则**：不要凭感觉优化，先用工具度量确认瓶颈。

## 何时激活

- 页面加载速度慢
- 滚动/操作时卡顿
- 打包体积过大
- 需要性能评估和优化

## 性能优化决策树

```
性能问题是...
├── 首屏加载慢
│   ├── 检查打包体积 → 代码分割 / 懒加载
│   ├── 检查网络瀑布 → 预加载 / 并行请求
│   └── 检查大资源 → 图片优化 / CDN
│
├── 操作卡顿（点击、输入、滚动）
│   ├── 频繁触发 → 防抖 / 节流
│   ├── 大量 DOM → 虚拟滚动
│   └── 计算量大 → Web Worker / 缓存
│
└── 内存增长（长时间使用后变慢）
    ├── 未清理定时器/监听器 → 生命周期清理
    ├── 闭包持有大对象 → 释放引用
    └── 缓存无限增长 → 设置上限 / LRU
```

## 加载性能

### 路由懒加载

```typescript
// router/index.ts

// ✅ 路由级别懒加载
const routes = [
  {
    path: '/dashboard',
    component: () => import('@/views/Dashboard.vue'),
  },
  {
    path: '/users',
    component: () => import('@/views/UserList.vue'),
  },
]

// ❌ 全部同步引入
import Dashboard from '@/views/Dashboard.vue'
import UserList from '@/views/UserList.vue'
```

### 组件懒加载

```vue
<script setup lang="ts">
import { defineAsyncComponent } from 'vue'

// ✅ 重型组件异步加载
const HeavyChart = defineAsyncComponent(() =>
  import('@/components/HeavyChart.vue')
)

const RichTextEditor = defineAsyncComponent({
  loader: () => import('@/components/RichTextEditor.vue'),
  loadingComponent: () => h('div', 'Loading...'),
  delay: 200,     // 延迟显示 loading，避免闪烁
  timeout: 10000, // 超时
})
</script>

<template>
  <HeavyChart v-if="showChart" :data="chartData" />
</template>
```

### 图片优化

```vue
<template>
  <!-- ✅ 懒加载图片 -->
  <img v-lazy="imageUrl" alt="description" />

  <!-- ✅ 响应式图片 -->
  <picture>
    <source media="(min-width: 1024px)" srcset="large.webp" />
    <source media="(min-width: 768px)" srcset="medium.webp" />
    <img src="small.webp" alt="description" loading="lazy" />
  </picture>

  <!-- ✅ 指定尺寸防止布局偏移 -->
  <img src="photo.webp" width="300" height="200" alt="description" />
</template>
```

## 运行时性能

### 防抖与节流

```typescript
// ✅ 搜索输入 - 防抖
const keyword = ref('')
const debouncedKeyword = refDebounced(keyword, 300) // VueUse

watch(debouncedKeyword, (val) => {
  fetchSearchResults(val)
})

// ✅ 滚动事件 - 节流
const { y: scrollY } = useScroll(window) // VueUse 内置节流
```

### 虚拟滚动

```vue
<!-- 大列表（> 100 项）使用虚拟滚动 -->
<script setup lang="ts">
// 使用 @vueuse/components 或 vue-virtual-scroller
import { useVirtualList } from '@vueuse/core'

const { list: virtualList, containerProps, wrapperProps } =
  useVirtualList(allItems, {
    itemHeight: 48,
  })
</script>

<template>
  <div v-bind="containerProps" class="h-[400px] overflow-auto">
    <div v-bind="wrapperProps">
      <div v-for="{ data, index } in virtualList" :key="index" class="h-12">
        {{ data.name }}
      </div>
    </div>
  </div>
</template>
```

### 计算缓存

```typescript
// ✅ 使用 computed 缓存派生数据
const sortedList = computed(() =>
  [...list.value].sort((a, b) => b.score - a.score)
)

const filteredList = computed(() =>
  sortedList.value.filter(item => item.status === activeStatus.value)
)

// ❌ 不要在模板中直接排序/过滤
// <div v-for="item in list.sort(...).filter(...)"> ← 每次渲染都重新计算
```

### 避免不必要的渲染

```vue
<!-- ✅ v-once：只渲染一次的静态内容 -->
<header v-once>
  <h1>{{ staticTitle }}</h1>
</header>

<!-- ✅ v-memo：条件缓存 -->
<div v-for="item in list" :key="item.id" v-memo="[item.id, item.status]">
  <ExpensiveComponent :item="item" />
</div>

<!-- ✅ shallowRef：大对象列表不需要深层响应式 -->
<script setup lang="ts">
const bigList = shallowRef<BigItem[]>([])

// 更新时需要整体替换
bigList.value = newList // ✅
bigList.value.push(item) // ❌ 不会触发更新
bigList.value = [...bigList.value, item] // ✅
</script>
```

## 构建优化

### 打包分析

```bash
# Vite 项目
npx vite-bundle-visualizer

# 或使用 rollup-plugin-visualizer
# vite.config.ts 中配置后运行 npm run build
```

### 常见优化

```typescript
// vite.config.ts

export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        // ✅ 手动分包 - 把大依赖独立打包
        manualChunks: {
          'vendor-vue': ['vue', 'vue-router', 'pinia'],
          'vendor-ui': ['ant-design-vue'],
          'vendor-utils': ['lodash-es', 'date-fns'],
          'vendor-charts': ['echarts'],
        },
      },
    },
    // ✅ 启用压缩
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,   // 生产环境移除 console
        drop_debugger: true,
      },
    },
  },
})
```

### 按需引入

```typescript
// ✅ 按需引入 lodash
import { debounce } from 'lodash-es'   // tree-shakable

// ❌ 全量引入
import _ from 'lodash'   // 打包整个 lodash

// ✅ 按需引入 date-fns
import { format, parseISO } from 'date-fns'

// ✅ ECharts 按需引入
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer])
```

## 性能检查清单

在上线前确认：
- [ ] 路由已配置懒加载
- [ ] 大组件使用 `defineAsyncComponent`
- [ ] 图片有 `loading="lazy"` 和明确的宽高
- [ ] 搜索/输入有防抖处理
- [ ] 长列表（> 100 项）使用虚拟滚动
- [ ] 打包体积分析过，没有意外的大依赖
- [ ] 第三方库按需引入
- [ ] 生产环境移除了 `console.log`
