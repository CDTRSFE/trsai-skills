---
name: api-integration
description: 前端 API 集成模式。在封装 HTTP 请求、设计 API 层、处理请求错误和加载状态时使用。
---

# 前端 API 集成模式

## 概述

规范化前端与后端 API 的交互方式。项目使用全局 `axios` 对象，采用 `.then().finally()` 链式调用，手动管理 loading 状态。

## 何时激活

- 封装 HTTP 请求
- 设计前端 API 层
- 处理请求错误和加载状态
- 实现轮询、防重复提交等模式

## 核心约定

- 使用全局 `axios`，**无需 import**
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

```
src/
├── api/
│   ├── user.ts       # 用户相关接口路径常量或函数
│   ├── order.ts
│   └── types/
│       ├── user.ts   # 请求/响应类型定义
│       └── order.ts
```

接口函数命名以动词开头，见名知意：

```typescript
// api/user.ts
export const API_USER_LIST = '/api/user/list'
export const API_USER_DETAIL = '/api/user/detail'
export const API_USER_CREATE = '/api/user/create'
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
