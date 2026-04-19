---
name: script-setup-structure
description: Vue `<script setup lang="ts">` 内部代码组织规范。在写新组件或重构组件 script 部分时使用，涵盖代码块顺序、Props/Emits 定义、响应式类型等。
---

# `<script setup>` 代码组织规范

## 代码块顺序（7步，必须遵守）

```typescript
<script setup lang="ts">
// ① 类型定义（interface / type）
interface UserInfo { ... }

// ② Props / Emits
const props = withDefaults(defineProps<{ list: UserInfo[] }>(), { list: () => [] })
const emit = defineEmits<{ success: []; 'update:open': [val: boolean] }>()

// ③ 响应式状态（ref / reactive）
const loading = ref(false)
const formState = reactive<FormState>({ name: '' })

// ④ 计算属性（computed）
const isEdit = computed(() => !!props.userId)

// ⑤ 组合式函数调用（useXxx()）
const router = useRouter()
const userStore = useUserStore()

// ⑥ 方法函数
function handleSubmit() { ... }
async function fetchList() { ... }

// ⑦ 生命周期钩子
onMounted(() => { fetchList() })
onUnmounted(() => { clearInterval(timer) })
</script>
```

---

## Props 定义规范

使用 `withDefaults` + `defineProps` 泛型语法，确保有默认值：

```typescript
// ✅ 标准写法
const props = withDefaults(defineProps<{
  list: UserInfo[]
  loading?: boolean
  userId?: string
}>(), {
  list: () => [],    // 数组/对象默认值必须用工厂函数
  loading: false,
})

// ❌ 不要用 defineProps({ ... }) 运行时声明方式（类型不够精确）
const props = defineProps({
  list: Array,
  loading: Boolean,
})
```

### Props 设计原则

- 只声明当前组件确实需要的 prop，避免过度封装
- 可选 prop 加 `?`，并在 `withDefaults` 中给出合理默认值
- 数组和对象类型的默认值必须用工厂函数，不能直接写字面量

---

## Emits 定义规范

使用泛型语法，严格定义事件名和参数类型：

```typescript
// ✅ 标准写法
const emit = defineEmits<{
  success: []                           // 无参数事件
  select: [item: UserInfo]              // 带参数事件
  delete: [id: string]
  'update:modelValue': [val: string]    // v-model 事件
}>()

// ❌ 不要用数组形式（无类型保障）
const emit = defineEmits(['success', 'select'])
```

---

## 响应式状态声明

所有响应式状态必须**显式声明泛型类型**：

```typescript
// ✅ 显式类型
const list = ref<UserInfo[]>([])
const detail = ref<UserDetail | null>(null)
const formState = reactive<FormState>({ name: '', status: 1 })
const loading = ref(false)        // boolean 可推断，可不写

// ❌ 无类型，AI 和 IDE 无法推断
const list = ref([])
const detail = ref(null)
```

---

## 函数定义顺序

`const` 箭头函数没有提升，**被调用的函数必须在调用者之前定义**：

```typescript
// ✅ 正确：fetchDetail 在 handleEdit 之前定义
async function fetchDetail(id: string) {
  const { data } = await axios.get(`/api/user/${id}`)
  ...
}

function handleEdit(id: string) {
  fetchDetail(id)     // 此时 fetchDetail 已定义
}

// ❌ 错误：const 箭头函数无提升，调用时 fetchDetail 还未定义
function handleEdit(id: string) {
  fetchDetail(id)     // ReferenceError
}

const fetchDetail = async (id: string) => { ... }
```

---

## 组件文件命名规范

- **文件名**：PascalCase，且必须是多单词，例如 `UserTable.vue`、`OrderFilterPanel.vue`
- **公共组件**（`src/components/`）：以 `Base`、`The` 或模块名开头，例如 `BaseButton.vue`、`TheHeader.vue`
- **Views 目录**：文件夹名 camelCase，例如 `src/views/coordinatedDisposal/`

---

## DOM / 组件 Ref 命名

Ref 引用必须加 `Ref` 后缀：

```typescript
// ✅ 加 Ref 后缀
const chartRef = ref<HTMLDivElement | null>(null)
const formRef = ref<InstanceType<typeof Form> | null>(null)
const tableRef = ref(null)

// ❌ 没有后缀，与普通数据混淆
const chart = ref(null)
const form = ref(null)
```

---

## defineModel（弹窗 visible / v-model）

弹窗的显隐状态推荐用 `defineModel`：

```typescript
// ✅ 弹窗组件中
const visible = defineModel<boolean>('open', { default: false })

// 父组件使用
// <user-modal v-model:open="showModal"></user-modal>
```

---

## 清理逻辑（必须）

所有在 `onMounted` 中注册的监听器、定时器，必须在 `onUnmounted` 中清理：

```typescript
// ✅ 正确：成对出现
onMounted(() => {
  window.addEventListener('resize', handleResize)
  timer = setInterval(pollStatus, 5000)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  clearInterval(timer)
})

// ✅ 更简洁：使用 VueUse（已自动导入）
useEventListener(window, 'resize', handleResize)   // 自动清理
```
