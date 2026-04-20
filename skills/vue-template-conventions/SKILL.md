---
name: vue-template-conventions
description: 在编写或审查 Vue 组件模板时使用，涵盖组件标签格式、属性顺序、v-for/v-if 规则等。
---

# Vue 模板书写规范

## 核心规则速查

| 规则 | ✅ 正确 | ❌ 错误 |
|------|---------|---------|
| 组件标签 | `<MyComponent />` 或 `<MyComponent></MyComponent>` | `<my-component></my-component>` |
| 普通元素自闭合 | 禁止 | `<div />` |
| void 元素 | `<br>` `<img>` `<input>` | `<br></br>` |
| 模板缩进 | 4 个空格 | 2 个空格 |

---

## 一、组件标签格式

自研组件（`src/components`、`src/views/**/components`）在模板中必须用 **PascalCase**。第三方/自动注册的前缀组件按约定使用（如 `a-`、`van-`、`icons-`）。

无子节点的组件允许自闭合；有子节点/slot 时必须成对标签。普通 HTML 非 void 元素不允许自闭合。

```vue
<!-- ✅ 正确 -->
<MyComponent></MyComponent>
<UserTable :data="list"></UserTable>
<BaseButton type="primary">提交</BaseButton>
<a-button type="primary">提交</a-button>
<a-input v-model:value="value" />

<!-- ❌ 错误：kebab-case 形式 -->
<my-component></my-component>
<user-table :data="list"></user-table>

<!-- ❌ 错误：需要子节点/slot 却自闭合 -->
<BaseButton />
```

**void 元素**（HTML 规范内置空元素）始终自闭合：

```vue
<!-- ✅ void 元素自闭合 -->
<br>
<hr>
<img src="..." alt="...">
<input v-model="value">
<meta charset="utf-8">
```

---

## 二、属性书写顺序

**指令（v-model/v-if 等）→ class → 其他属性 → 事件（@xxx）**

```vue
<!-- ✅ 正确顺序 -->
<a-input
    v-model:value="title"
    class="search-input"
    placeholder="请输入"
    :disabled="loading"
    @change="handleChange"
 />

<!-- ❌ 事件写在中间、class 写在最后 -->
<a-input
    @change="handleChange"
    placeholder="请输入"
    class="search-input"
    v-model:value="title"
 />
```

属性类型优先级（从高到低）：

1. `v-model`、`v-if`、`v-else-if`、`v-else`、`v-show`、`v-for`、`v-bind`、`v-slot` 等指令
2. `class`
3. 静态属性 / 动态绑定（`:prop`）
4. 事件（`@click`、`@change` 等）

---

## 三、单行属性上限

**单行最多 5 个属性，超过则每个属性单独一行：**

```vue
<!-- ✅ 3 个属性，单行可接受 -->
<a-button type="primary" :loading="submitting" @click="handleSubmit">提交</a-button>

<!-- ✅ 超过 5 个，每属性单独一行（4 空格缩进） -->
<a-table
    :data-source="list"
    :columns="columns"
    :loading="tableLoading"
    :pagination="pagination"
    row-key="id"
    @change="handleTableChange"
></a-table>

<!-- ❌ 超过 5 个仍写在一行 -->
<a-table :data-source="list" :columns="columns" :loading="tableLoading" :pagination="pagination" row-key="id"></a-table>
```

---

## 四、v-for 与 v-if 规则

### v-for 必须有唯一 key

```vue
<!-- ✅ 使用数据唯一标识 -->
<div v-for="item in list" :key="item.id">{{ item.name }}</div>

<!-- ❌ 用 index 作 key（排序变化时出问题）-->
<div v-for="(item, index) in list" :key="index">{{ item.name }}</div>

<!-- ❌ 没有 key -->
<div v-for="item in list">{{ item.name }}</div>
```

### 禁止 v-if 和 v-for 在同一元素上

```vue
<!-- ❌ 同一元素同时有 v-for 和 v-if -->
<div v-for="item in list" v-if="item.active" :key="item.id">
  {{ item.name }}
</div>

<!-- ✅ 用 computed 过滤后渲染 -->
<script setup lang="ts">
const activeList = computed(() => list.value.filter(item => item.active))
</script>

<template>
  <div v-for="item in activeList" :key="item.id">{{ item.name }}</div>
</template>
```

---

## 五、模板缩进

模板内统一 **4 个空格**缩进：

```vue
<template>
    <div class="page">
        <div class="header">
            <a-button @click="handleAdd">新增</a-button>
        </div>
        <a-table :data-source="list"></a-table>
    </div>
</template>
```

---

## 六、语义化 HTML

禁止用空 DOM 元素实现样式效果，遵循语义化：

```vue
<!-- ❌ 用 div 做按钮，无语义 -->
<div class="btn" @click="handleClick">提交</div>

<!-- ✅ 使用语义标签 -->
<button class="btn" @click="handleClick">提交</button>

<!-- ❌ 空 div 纯粹撑高度/间距 -->
<div style="height: 20px"></div>

<!-- ✅ 用 CSS margin/padding 处理间距 -->
```

常用语义标签对照：

| 场景 | 推荐标签 |
|------|---------|
| 导航 | `<nav>` |
| 页头 | `<header>` |
| 主内容 | `<main>` |
| 侧边栏 | `<aside>` |
| 页脚 | `<footer>` |
| 文章/卡片 | `<article>` / `<section>` |
| 按钮操作 | `<button>` |
| 链接跳转 | `<a>` |

---

## 七、图标使用

使用项目图标系统，格式为 `<icons-{文件名}>`，对应 `src/assets/icons/` 下的 SVG 文件：

```vue
<!-- src/assets/icons/search.svg → icons-search -->
<icons-search></icons-search>

<!-- src/assets/icons/arrow-down.svg → icons-arrow-down -->
<icons-arrow-down></icons-arrow-down>
```
