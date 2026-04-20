---
name: typescript-naming-conventions
description: 在编写新代码、做 Code Review、或修正命名/类型问题时使用。
---

# TypeScript 命名与类型规范

## 命名规范速查

| 类型 | 规则 | 示例 |
|------|------|------|
| Interface | PascalCase，**不加 I 前缀** | `UserInfo`、`OrderDetail` |
| Type alias | PascalCase | `StatusType`、`ApiResponse<T>` |
| 常量 | UPPER_SNAKE_CASE | `MAX_PAGE_SIZE`、`BASE_URL` |
| 变量/函数 | camelCase | `userList`、`fetchData` |
| 获取数据函数 | `get` 开头 | `getList`、`getUserDetail` |
| 事件处理函数 | `handle` 开头 | `handleSubmit`、`handleDelete` |
| DOM/组件 Ref | `Ref` 后缀 | `chartRef`、`formRef` |
| Composable | `use` 开头 | `useTablePagination`、`useListFilter` |
| CSS 类名 | kebab-case | `.main-container`、`.user-card` |
| 组件文件名 | PascalCase，多单词 | `UserTable.vue`、`OrderFilterPanel.vue` |
| Views 文件夹名 | camelCase | `coordinatedDisposal/`、`userManagement/` |

---

## Interface 规范

```typescript
// ✅ PascalCase，不加 I 前缀
interface UserInfo {
  id: string
  name: string
  status: 0 | 1
}

interface PageResult<T> {
  list: T[]
  total: number
}

// ❌ 加 I 前缀（Java 风格，禁止）
interface IUserInfo { ... }
interface IPageResult<T> { ... }
```

### interface vs type

**优先用 `interface`，type 仅用于联合类型、工具类型等 interface 无法表达的场景：**

```typescript
// ✅ 对象类型用 interface
interface UserInfo { id: string; name: string }

// ✅ 联合类型、工具类型用 type
type Status = 'active' | 'inactive' | 'pending'
type ApiResponse<T> = { code: number; data: T; msg: string }
type Nullable<T> = T | null

// ❌ 对象类型用 type（可以但不推荐）
type UserInfo = { id: string; name: string }
```

---

## 避免 any

```typescript
// ❌ 禁止裸用 any
function process(data: any) { ... }
const result: any = await fetchData()

// ✅ 用 unknown（需要收窄类型后才能使用）
function process(data: unknown) {
  if (typeof data === 'string') { ... }
}

// ✅ 用具体接口类型
const result: UserInfo = await fetchData()

// ✅ 确实无法确定类型时，加注释说明原因
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const legacyData: any = parseLegacyFormat(raw)
```

---

## 索引类型

```typescript
// ✅ 用 Record<K, V>
const statusMap: Record<string, string> = {
  '0': '禁用',
  '1': '启用',
}

const userCache: Record<string, UserInfo> = {}

// ❌ 不推荐（可读性差）
const statusMap: { [key: string]: string } = { ... }
```

---

## import type

仅用于类型的符号必须用 `import type`：

```typescript
// ✅ 类型只在类型位置使用，用 import type
import type { UserInfo, OrderDetail } from '@/api/types'
import type { ComponentPublicInstance } from 'vue'

// ✅ 值和类型混用时，用普通 import（或 import { type X }）
import { defineStore } from 'pinia'
import { ref, type Ref } from 'vue'

// ❌ 把类型当值 import（会被打包进 bundle）
import { UserInfo } from '@/api/types'   // UserInfo 只是个类型
```

---

## ts-ignore / ts-expect-error

```typescript
// ✅ 用 @ts-expect-error，附说明注释
// @ts-expect-error: 第三方库类型定义不完整，实际支持该参数
echarts.init(el, null, { renderer: 'svg' })

// ❌ 裸用 @ts-ignore（无说明，难以排查）
// @ts-ignore
doSomething()
```

---

## 安全访问

```typescript
// ✅ 可选链（?.）和空值合并（??）
const name = user?.profile?.name ?? '匿名'
const list = response?.data?.list ?? []
const count = pagination?.total ?? 0

// ❌ 不安全访问（可能报 TypeError）
const name = user.profile.name
const list = response.data.list
```

---

## 严格相等

```typescript
// ✅ 始终用 ===
if (data?.code === 200) { ... }
if (status === 0) { ... }
if (value === null) { ... }

// ❌ 禁止 ==（隐式类型转换，行为不可预期）
if (data?.code == 200) { ... }
if (value == null) { ... }   // 本意可能是 null 或 undefined
```

---

## JS / ES6+ 编码规范

### 模板字面量（禁止字符串拼接）

```typescript
// ✅ 模板字面量
const url = `/api/user/${userId}`
const msg = `欢迎，${userName}！您有 ${count} 条消息`

// ❌ 字符串拼接
const url = '/api/user/' + userId
const msg = '欢迎，' + userName + '！您有 ' + count + ' 条消息'
```

### 对象简写

```typescript
// ✅ ES6 简写
const name = 'Alice'
const user = { name, age: 18, greet() { return `Hi, ${this.name}` } }

// ❌ 冗余写法
const user = { name: name, greet: function() { ... } }
```

### 数组方法

```typescript
// ✅ 精确语义
const target = list.find(item => item.id === id)          // 找单个
const flat = nestedList.flat()                             // 展开一层
const result = list.flatMap(item => item.children)        // 展开+映射
const hasHttp = url.startsWith('http')                    // 前缀判断
const isCss = filename.endsWith('.css')                   // 后缀判断

// ❌ 冗余写法
const target = list.filter(item => item.id === id)[0]
const flat = [].concat(...nestedList)
const hasHttp = /^http/.test(url)
```

### 其他规范

```typescript
// ✅ 剩余参数
function log(...args: unknown[]) { console.log(...args) }

// ❌ arguments 对象
function log() { console.log(arguments) }

// ✅ 回调函数用箭头函数
list.forEach((item) => { ... })
setTimeout(() => fetchData(), 1000)

// ✅ import 顺序：第三方库 → 内部模块，同组按字母序
import { message } from 'ant-design-vue'
import debounce from 'lodash/debounce'
import type { UserInfo } from '@/api/types/user'
import { useUserStore } from '@/stores/user'

// ✅ 多行对象/数组/参数的最后一项加尾逗号
const config = {
  timeout: 5000,
  retry: 3,       // ← 尾逗号
}

// ✅ 禁止多层嵌套三目，用 if/else 或提取函数
// ❌
const label = a ? b ? 'x' : 'y' : 'z'
// ✅
function getLabel() {
  if (!a) return 'z'
  return b ? 'x' : 'y'
}

// ✅ 通用规范
import { isArray } from '@/utils'           // 用 Array.isArray()，不用 instanceof Array
path.startsWith('@/')                        // 路径始终用 @/ 别名
import debounce from 'lodash/debounce'      // lodash 按需引入
```
