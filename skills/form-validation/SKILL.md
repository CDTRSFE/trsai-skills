---
name: form-validation
description: 在规划或实现新增/编辑表单、筛选表单、弹窗表单、校验规则、提交和回显逻辑时使用；TRS 开发计划涉及表单任务时必须使用。
---

# 表单验证与处理规范

## 概述

规范项目中表单的结构设计、校验规则写法、提交流程及数据回显模式。

**核心原则**：表单状态本地管理，提交后统一走 api-integration 规范，校验规则集中定义不散落。Ant Design Vue 优先集中定义规则；Vant 可按组件库模式写在 `van-field` 上，复杂或复用规则再抽常量。

## writing-plans 阶段要求

当本技能用于实施计划阶段时，计划必须写清：

- 本技能约束适用于哪些任务。
- 计划的 `Required TRS skills` 中必须列出 `form-validation`；表单提交涉及接口时必须同时列出 `api-integration`。
- 需要创建或修改的文件。
- 表单场景、字段类型、校验规则、提交参数、回显映射、防重复提交和成功/失败反馈。
- 验证方式：开发中优先 `pnpm lint:eslint` / `pnpm lint`，涉及页面交互必须做页面运行时、表单校验与 Network/Console 检查；不得默认安排 `pnpm build`，只有用户明确确认后才执行。
- 若任务涉及页面、组件、样式、交互或接口联调，计划中必须增加 `Browser Runtime Verification` 小节，声明使用 `chrome-devtools-mcp`，并列出页面路径、核心操作、Console、Network、布局检查点。

## 何时激活

- 实现新增 / 编辑表单
- 处理表单提交与校验
- 表单数据回显（编辑场景）
- 实现自定义校验规则

---

## 一、Ant Design Vue 表单（PC 端）

### 标准结构

```vue
<script setup lang="ts">
import type { FormInstance } from 'ant-design-vue'

interface FormState {
  name: string
  roleId: number | undefined
  status: 0 | 1
  remark?: string
}

// 表单响应式数据
const formState = reactive<FormState>({
  name: '',
  roleId: undefined,
  status: 1,
  remark: '',
})

// 表单实例引用（用于触发校验）
const formRef = ref<FormInstance | null>(null)

// 校验规则（集中定义，不写在模板里）
const rules = {
  name: [
    { required: true, message: '请输入姓名', trigger: 'blur' },
    { min: 2, max: 20, message: '长度 2-20 个字符', trigger: 'blur' },
  ],
  roleId: [
    { required: true, message: '请选择角色', trigger: 'change' },
  ],
}

// 提交
const submitting = ref(false)

async function handleSubmit() {
  await formRef.value?.validate()     // 校验不通过会抛出异常，自动中断
  if (submitting.value) return        // 防重复提交
  submitting.value = true
  try {
    const { data } = await axios.post('/api/user/create', formState)
    if (data?.code !== 200) return
    message.success('创建成功')
    emit('success')
  } finally {
    submitting.value = false
  }
}

// 重置
function handleReset() {
  formRef.value?.resetFields()
}
</script>

<template>
  <a-form
    ref="formRef"
    :model="formState"
    :rules="rules"
    :label-col="{ span: 6 }"
    :wrapper-col="{ span: 16 }"
    @finish="handleSubmit"
  >
    <a-form-item label="姓名" name="name">
      <a-input v-model:value="formState.name" placeholder="请输入姓名"></a-input>
    </a-form-item>

    <a-form-item label="角色" name="roleId">
      <a-select v-model:value="formState.roleId" placeholder="请选择角色">
        <a-select-option v-for="item in roleList" :key="item.id" :value="item.id">
          {{ item.name }}
        </a-select-option>
      </a-select>
    </a-form-item>

    <a-form-item label="状态" name="status">
      <a-radio-group v-model:value="formState.status">
        <a-radio :value="1">启用</a-radio>
        <a-radio :value="0">禁用</a-radio>
      </a-radio-group>
    </a-form-item>

    <a-form-item :wrapper-col="{ offset: 6 }">
      <a-button type="primary" html-type="submit" :loading="submitting">提交</a-button>
      <a-button class="ml-2" @click="handleReset">重置</a-button>
    </a-form-item>
  </a-form>
</template>
```

---

## 二、编辑场景：数据回显

编辑时用 `watch` 监听传入的 `id` 或数据对象，加载完成后赋值给 `formState`：

```typescript
interface Props {
  userId?: string   // 有值=编辑，无值=新增
}
const props = defineProps<Props>()

const isEdit = computed(() => !!props.userId)

// 编辑时回显数据
watch(
  () => props.userId,
  async (id) => {
    if (!id) {
      formRef.value?.resetFields()  // 新增时确保表单干净
      return
    }
    const { data } = await axios.get(`/api/user/detail/${id}`)
    if (data?.code !== 200) return
    // ✅ 用 Object.assign 覆盖，保留 reactive 响应式
    Object.assign(formState, data.data)
  },
  { immediate: true },
)

// ❌ 禁止直接赋值替换 reactive 对象
// formState = data.data  → 丢失响应式
```

---

## 三、弹窗表单模式（新增 + 编辑合一）

```vue
<!-- UserFormModal.vue -->
<script setup lang="ts">
const visible = defineModel<boolean>('open', { default: false })

interface Props {
  userId?: string
}
const props = defineProps<Props>()
const emit = defineEmits<{ success: [] }>()

const isEdit = computed(() => !!props.userId)
const title = computed(() => isEdit.value ? '编辑用户' : '新增用户')

// 弹窗关闭时重置表单
watch(visible, (val) => {
  if (!val) formRef.value?.resetFields()
})
</script>

<template>
  <a-modal
    v-model:open="visible"
    :title="title"
    :confirm-loading="submitting"
    @ok="handleSubmit"
    @cancel="visible = false"
  >
    <!-- 表单内容 -->
  </a-modal>
</template>
```

---

## 四、自定义校验规则

```typescript
// ✅ 异步自定义校验（如校验用户名是否重复）
const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      validator: async (_rule: unknown, value: string) => {
        if (!value) return
        const { data } = await axios.get('/api/user/check-name', { params: { name: value } })
        if (data?.data?.exists) {
          return Promise.reject(new Error('用户名已存在'))
        }
      },
      trigger: 'blur',
    },
  ],

  // ✅ 同步自定义校验
  phone: [
    {
      validator: (_rule: unknown, value: string) => {
        if (!value) return Promise.resolve()
        if (!/^1[3-9]\d{9}$/.test(value)) {
          return Promise.reject(new Error('手机号格式不正确'))
        }
        return Promise.resolve()
      },
      trigger: 'blur',
    },
  ],
}
```

---

## 五、Vant 表单（移动端 H5）

```vue
<script setup lang="ts">
import type { FormInstance } from 'vant'

const formRef = ref<FormInstance | null>(null)

const formState = reactive({
  name: '',
  phone: '',
})

// Vant 校验规则格式不同，可直接写在 van-field 上；复杂或复用规则再抽成常量
async function handleSubmit() {
  await formRef.value?.validate()
  // 提交逻辑...
}
</script>

<template>
  <van-form ref="formRef" @submit="handleSubmit">
    <van-cell-group inset>
      <van-field
        v-model="formState.name"
        name="name"
        label="姓名"
        placeholder="请输入姓名"
        :rules="[{ required: true, message: '请填写姓名' }]"
      ></van-field>

      <van-field
        v-model="formState.phone"
        name="phone"
        label="手机号"
        type="tel"
        placeholder="请输入手机号"
        :rules="[
          { required: true, message: '请填写手机号' },
          { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确' },
        ]"
      ></van-field>
    </van-cell-group>

    <div class="p-4">
      <van-button round block type="primary" native-type="submit" :loading="submitting">
        提交
      </van-button>
    </div>
  </van-form>
</template>
```

---

## 六、常用校验规则速查

```typescript
// 统一维护在 src/utils/validators.ts（复用规则）

// 必填
{ required: true, message: '请输入 xxx', trigger: 'blur' }

// 长度限制
{ min: 2, max: 50, message: '长度 2-50 个字符', trigger: 'blur' }

// 手机号
{ pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' }

// 邮箱
{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }

// 正整数
{ pattern: /^[1-9]\d*$/, message: '请输入正整数', trigger: 'blur' }

// 数字范围
{ type: 'number', min: 1, max: 999, message: '请输入 1-999 之间的数字' }

// 仅汉字
{ pattern: /^[\u4e00-\u9fa5]+$/, message: '只能输入中文', trigger: 'blur' }

// URL
{ type: 'url', message: 'URL 格式不正确', trigger: 'blur' }
```

---

## 七、反模式检查清单

- [ ] ❌ 校验规则写在模板属性里（散乱难维护）→ 统一定义 `const rules = {}` 对象
- [ ] ❌ 提交前没有调用 `formRef.value?.validate()` → 用户绕过必填直接提交
- [ ] ❌ 编辑回显用 `formState = data.data` 整体替换 → 用 `Object.assign`
- [ ] ❌ 弹窗关闭后没有 `resetFields()` → 下次打开残留上次数据
- [ ] ❌ loading 位置不符合 `api-integration` → 出错时按钮永远 loading
- [ ] ❌ 防重复提交只靠按钮 disabled → 补充 `if (submitting.value) return` 守卫
