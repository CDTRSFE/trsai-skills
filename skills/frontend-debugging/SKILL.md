---
name: frontend-debugging
description: 前端系统化调试方法论。在排查 UI 渲染问题、状态异常、网络请求失败、样式错乱等前端 bug 时使用。
---

# 前端系统化调试

## 概述

系统化排查前端问题，避免"猜测式修复"。遵循四阶段流程：**现象定位 → 根因分析 → 假设验证 → 精确修复**。

**核心原则**：找到根因再修复。不要在没弄清原因之前就"试试看"。

## 何时激活

- 排查 UI 渲染异常
- 调试状态管理问题
- 分析网络请求失败
- 解决样式错乱
- 任何前端 bug 修复

## 铁律

```
不要在不理解问题根因的情况下修改代码。
"先改了再说" = 埋下更多 bug。
```

## 四阶段调试流程

### 第一阶段：现象定位

**目标**：精确描述问题，缩小范围。

1. **复现问题**
   - 记录精确的复现步骤
   - 确认是否 100% 可复现
   - 确定浏览器 / 设备 / 分辨率

2. **分类问题**

| 问题类型 | 首先查看 |
|---------|---------|
| 白屏/崩溃 | 浏览器控制台 → 错误信息 |
| 数据不显示 | Network 面板 → 请求是否发出、响应是否正确 |
| 样式错乱 | Elements 面板 → 计算样式、盒模型 |
| 交互无响应 | Console → 是否有错误；Elements → 事件监听 |
| 性能卡顿 | Performance 面板 → 长任务、重排重绘 |
| 状态异常 | Vue DevTools → 组件树、Pinia 状态 |

3. **收集关键信息**
   - 控制台错误和警告
   - 网络请求状态码和响应体
   - 组件内当前的 props、state 值
   - 最近一次正常工作的时间/提交

### 第二阶段：根因分析

**目标**：从现象追溯到引起问题的代码。

**原则**：从出错点向上追溯数据流。

```
显示错误 ← 渲染数据 ← 状态/store ← API 响应 ← 请求参数 ← 用户操作
（从左往右逐步检查，找到第一个出错的环节）
```

**常用工具**：

```javascript
// 1. 在关键位置打断点或 console
console.log('[DEBUG] fetchList params:', params)
console.log('[DEBUG] API response:', response.data)
console.log('[DEBUG] computed value:', computedList.value)

// 2. Vue DevTools 检查
// - 组件树中找到目标组件
// - 检查 props 传入值是否正确
// - 检查 reactive/ref 状态是否符合预期
// - 检查 Pinia store 的值

// 3. 使用 watch 追踪状态变化
watch(suspiciousRef, (newVal, oldVal) => {
  console.log('[DEBUG] state changed:', { oldVal, newVal })
  console.trace()  // 打印调用栈
})
```

### 第三阶段：假设验证

**目标**：验证你的假设是否正确，而不是直接改代码。

1. 提出明确假设："问题是因为 X"
2. 设计验证实验（不修改生产代码）
3. 确认假设

```javascript
// ✅ 正确做法 - 先验证假设
// 假设："列表数据因为分页参数错误而为空"
// 验证：在 Console 中手动发请求
await axios.get('/api/list', { params: { page: 1, size: 10 } })
// → 如果返回数据，说明假设成立

// ❌ 错误做法 - 直接改代码"试试"
// "可能是分页参数的问题，我改一下试试"
```

### 第四阶段：精确修复

**目标**：最小化修改，只修复根因。

1. **只改根因** — 不要顺手"优化"无关代码
2. **验证修复** — 用原始复现步骤确认问题已解决
3. **检查副作用** — 确认修复没有破坏其他功能
4. **编写测试** — 为该 bug 补充测试用例防止回归

## 前端常见陷阱速查

### 异步竞态

```typescript
// ❌ 快速切换 tab 导致旧请求覆盖新数据
async function fetchData(tabId: string) {
  const data = await api.getList(tabId)
  list.value = data  // 旧请求可能后于新请求返回
}

// ✅ 使用标记取消过期请求
let currentRequestId = 0
async function fetchData(tabId: string) {
  const requestId = ++currentRequestId
  const data = await api.getList(tabId)
  if (requestId === currentRequestId) {
    list.value = data
  }
}

// ✅ 或使用 AbortController
const controller = new AbortController()
const data = await axios.get(url, { signal: controller.signal })
```

### 响应式丢失

```typescript
// ❌ 解构丢失响应式
const { count, name } = storeToRefs(useUserStore())  // ✅
const { count, name } = useUserStore()  // ❌ 丢失响应式

// ❌ 整体赋值丢失响应式
const state = reactive({ list: [] })
state = { list: newData }  // ❌ 丢失
Object.assign(state, { list: newData })  // ✅

// ❌ ref 忘记 .value
const count = ref(0)
count = 1      // ❌ 覆盖了 ref 本身
count.value = 1  // ✅
```

### 闭包陷阱

```typescript
// ❌ setTimeout/setInterval 捕获旧值
const count = ref(0)
setInterval(() => {
  console.log(count.value)  // 始终是最新值（ref 是对象引用）
  console.log(localVar)      // ⚠️ 如果 localVar 是基本类型，会捕获旧值
}, 1000)
```

### 内存泄漏

```typescript
// ❌ 忘记清理
onMounted(() => {
  window.addEventListener('resize', handleResize)
  const timer = setInterval(pollData, 5000)
})

// ✅ 必须在 onUnmounted 清理
onMounted(() => {
  window.addEventListener('resize', handleResize)
  const timer = setInterval(pollData, 5000)

  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    clearInterval(timer)
  })
})
```

## 红旗信号 — 立刻停下

- 🚩 修改了代码但不知道为什么能修好 → 回到第二阶段
- 🚩 "在我电脑上没问题" → 检查环境差异（Node 版本、浏览器版本、数据差异）
- 🚩 修一个 bug 引出两个新 bug → 根因分析不充分，回到第一阶段
- 🚩 改了 3 次还没修好 → 停下来，完整走一遍四阶段流程
