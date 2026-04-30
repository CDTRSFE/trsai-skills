---
name: api-integration
description: 在规划或封装 HTTP 请求、设计 API 层、处理 loading/error/empty、轮询、防重复提交时使用；TRS 开发计划涉及接口任务时必须使用。
---

# 前端 API 集成模式

## 概述

规范化前端与后端 API 的交互方式。默认允许把请求代码就近写在页面/组件内；当接口被多处复用或需要统一处理时，再抽成公共 API 模块。

## writing-plans 阶段要求

当本技能用于实施计划阶段时，计划必须写清：

- 本技能约束适用于哪些任务。
- 计划的 `Required TRS skills` 中必须列出 `api-integration`；若同时涉及组件、样式、表单或 Store，也必须列出对应 TRS skill。
- 需要创建或修改的文件。
- 接口路径、请求参数、响应结构、loading/error/empty、防重复提交或轮询方案。
- 验证方式：开发中优先 `pnpm lint:eslint` / `pnpm lint`，涉及页面交互必须做页面运行时、Network/Console 检查；不得默认安排 `pnpm build`，只有用户明确确认后才执行。
- 若任务涉及页面、组件、样式、交互或接口联调，计划中必须增加 `Browser Runtime Verification` 小节，声明使用 `chrome-devtools-mcp`，并列出页面路径、核心操作、Console、Network、布局检查点。

## 何时激活

- 封装 HTTP 请求
- 设计前端 API 层
- 处理请求错误和加载状态
- 实现轮询、防重复提交等模式

## 核心约定

- `axios` 的来源以项目实际工程为准（可能是全局可用，也可能来自你们的请求封装模块）
- `.then().finally()` 和 `async/await + try/finally` 均可，根据场景灵活选择
- 通过 `data?.code === 200` 判断业务成功，不成功直接 `return`
- loading 在请求前设 `true`，必须在 `finally` 中设 `false`，不能漏关
- 需要提示用户时才加 `.catch()` / `catch` 块，不强制每个请求都写

## 标准写法

### 链式写法（适合逻辑简单的场景）

```typescript
const fetchList = () => {
    listData.value = [];           // 请求前重置，避免旧数据闪烁
    listLoading.value = true;
    axios.get('/api/xxx', { params: { id: route.query.id } })
        .then(({ data }) => {
            if (data?.code !== 200) return;
            listData.value = data?.data || [];
        })
        .catch(({ data }) => {
            message.error(data?.msg || '加载失败');  // 需要时才加
        })
        .finally(() => {
            listLoading.value = false;
        });
};
```

### async/await 写法（适合多个请求串行、逻辑复杂的场景）

```typescript
const fetchDetail = async () => {
    detailLoading.value = true;
    try {
        const { data } = await axios.get(`/api/xxx/${id.value}`);
        if (data?.code !== 200) return;
        detailData.value = data?.data;
    } catch {
        message.error('加载失败');
    } finally {
        detailLoading.value = false;
    }
};

// 多请求串行
const initPage = async () => {
    pageLoading.value = true;
    try {
        const { data: user } = await axios.get('/api/user/info');
        if (user?.code !== 200) return;

        const { data: orders } = await axios.get('/api/orders', {
            params: { userId: user.data.id },
        });
        if (orders?.code !== 200) return;

        orderList.value = orders?.data || [];
    } finally {
        pageLoading.value = false;
    }
};
```

## API 目录结构

本团队不强制 `src/api` 结构。按“复用程度”选择放置方式即可：

### 方式 A：页面/组件就近（默认）

- 适用：只在当前页面/组件使用的接口；页面逻辑强绑定
- 放置：直接写在 `.vue` 的 `<script setup>` 内，或同目录的 `api.ts`

示例（同目录 `api.ts`）：

```typescript
export function getUserList(params: { page: number; pageSize: number }) {
  return axios.get('/api/user/list', { params })
}
```

### 方式 B：抽公共 API（可选）

- 适用（满足任一条就建议抽）：
  - 同一接口被 2+ 页面/组件复用
  - 同一套参数/返回类型在多处反复声明
  - 需要统一处理（错误提示、重试、节流、防重复提交、取消请求等）
  - 需要把“接口约束”从 UI 逻辑中剥离，便于测试与复用
- 放置：你们项目约定的公共位置（例如 `src/shared/api/`、`src/services/` 等）

命名建议二选一，保持一致即可：

```typescript
export const API_USER_LIST = '/api/user/list'

export function getUserList(params: { page: number; pageSize: number }) {
  return axios.get(API_USER_LIST, { params })
}
```

## 常用模式

### 防重复提交

```typescript
const submitting = ref(false);

const handleSubmit = () => {
    if (submitting.value) return;
    submitting.value = true;
    axios.post('/api/xxx', formState).then(({ data }) => {
        if (data?.code !== 200) return;
        message.success('提交成功');
    }).finally(() => {
        submitting.value = false;
    });
};
```

### 轮询

```typescript
let pollTimer: ReturnType<typeof setTimeout> | null = null;

const startPoll = () => {
    const poll = () => {
        axios.get('/api/status').then(({ data }) => {
            if (data?.code !== 200) return;
            statusData.value = data?.data;
        }).finally(() => {
            pollTimer = setTimeout(poll, 5000);
        });
    };
    poll();
};

onUnmounted(() => {
    if (pollTimer) clearTimeout(pollTimer);
});
```

## 反模式

```typescript
// ❌ loading 没有放在 finally 中（请求出错时会漏关）
axios.get('/api/xxx').then(({ data }) => {
    listLoading.value = false;  // .catch 时不会执行到这里
});

// ❌ 忽略 code 判断，直接取数据
axios.get('/api/xxx').then(({ data }) => {
    listData.value = data?.data;  // code 非 200 时也会赋值
});

// ❌ async/await 没有 finally，loading 在出错时漏关
const fetchList = async () => {
    listLoading.value = true;
    const { data } = await axios.get('/api/xxx');  // 出错时 loading 永远是 true
    listData.value = data?.data;
    listLoading.value = false;
};
```
