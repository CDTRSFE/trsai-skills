---
name: vue-auto-imports
description: 在生成任何代码时使用，确保不手动 import 已通过 unplugin-auto-import / unplugin-vue-components 自动注入的 API 和组件。
---

# 项目自动导入白名单

## 核心规则

**以下 API 和组件已自动导入，生成代码时禁止手动写 import 语句。**

如果你看到生成的代码里有这些 import，立即删除。

---

## Vue 核心 Composition API（全部自动导入）

```typescript
// ❌ 禁止手动写
import { ref, reactive, computed, watch } from 'vue'

// ✅ 直接使用
const count = ref(0)
const state = reactive({ name: '' })
const double = computed(() => count.value * 2)
```

已自动导入的 Vue API 完整列表：

- 响应式：`ref`、`reactive`、`shallowRef`、`shallowReactive`、`readonly`、`toRef`、`toRefs`、`toRaw`、`markRaw`、`isRef`、`isReactive`
- 计算与监听：`computed`、`watch`、`watchEffect`、`watchPostEffect`、`watchSyncEffect`
- 生命周期：`onMounted`、`onUnmounted`、`onBeforeMount`、`onBeforeUnmount`、`onUpdated`、`onBeforeUpdate`、`onActivated`、`onDeactivated`
- 组件工具：`defineProps`、`defineEmits`、`defineExpose`、`defineModel`、`withDefaults`、`useAttrs`、`useSlots`
- 其他：`provide`、`inject`、`nextTick`、`h`、`resolveComponent`、`defineAsyncComponent`

---

## Vue Router（自动导入）

```typescript
// ❌ 禁止
import { useRouter, useRoute } from 'vue-router'

// ✅ 直接使用
const router = useRouter()
const route = useRoute()
```

---

## Pinia（自动导入）

```typescript
// ❌ 禁止
import { defineStore, storeToRefs } from 'pinia'

// ✅ 直接使用
export const useUserStore = defineStore('user', () => { ... })
```

---

## VueUse（常用 API 已自动导入）

直接使用，无需 import：

- `useStorage`、`useDark`、`useToggle`
- `useEventListener`、`useResizeObserver`、`useMutationObserver`
- `useScroll`、`useIntersectionObserver`
- `refDebounced`、`refThrottled`
- `useVirtualList`
- `useWindowSize`、`useBreakpoints`

---

## UI 组件库（自动注册，无需 import）

### Ant Design Vue（PC 端）

模板中直接使用 `a-` 前缀组件，不需要 import：

```vue
<!-- ❌ 禁止 -->
<script setup>
import { Button, Table, Modal } from 'ant-design-vue'
</script>

<!-- ✅ 直接在模板中使用 -->
<template>
  <a-button type="primary">提交</a-button>
  <a-table :data-source="list" :columns="columns"></a-table>
  <a-modal v-model:open="visible"></a-modal>
</template>
```

### Vant（移动端 H5）

```vue
<!-- ✅ 直接使用，无需 import -->
<van-button type="primary">提交</van-button>
<van-form ref="formRef">...</van-form>
<van-field v-model="value" label="姓名"></van-field>
```

---

## src/components 公共组件（自动注册）

`src/components/` 目录下的所有组件自动全局注册：

```vue
<!-- ❌ 禁止 -->
import BaseButton from '@/components/BaseButton.vue'

<!-- ✅ 直接使用 -->
<base-button>点击</base-button>
```

---

## 需要手动 import 的内容

以下内容**不会自动导入**，必须手动写 import：

```typescript
// 业务 API 层
import { API_USER_LIST } from '@/api/user'

// 类型定义（必须用 import type）
import type { UserInfo } from '@/api/types/user'

// lodash（按需引入）
import debounce from 'lodash/debounce'

// ECharts（按需引入）
import * as echarts from 'echarts/core'

// 业务 composable
import { useTablePagination } from '@/composables/useTablePagination'

// 业务 store
import { useUserStore } from '@/stores/user'
```

---

## 反模式示例

```typescript
// ❌ 以下都是多余的 import，删掉
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { defineStore } from 'pinia'
import { useStorage } from '@vueuse/core'
```
