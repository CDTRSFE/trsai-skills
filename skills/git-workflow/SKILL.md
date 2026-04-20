---
name: git-workflow
description: 在创建分支、提交代码、发起 MR/PR、Code Review、以及处理合并冲突时使用。
---

# Git 工作流规范

## 概述

规范团队 Git 使用方式，确保分支清晰、提交可追溯、合并安全。

**核心原则**：主干分支永远可发布，功能开发在独立分支进行，合并前必须自测通过。

## 何时激活

- 开始一个新功能或 Bug 修复
- 准备发起 MR / PR 前
- 进行 Code Review
- 处理合并冲突
- 准备发布版本

---

## 一、分支结构

```
main / master       → 生产环境，永远可发布，禁止直接推送
  └── develop       → 集成分支，日常开发合入点
        ├── feature/xxx     → 功能开发
        ├── fix/xxx         → Bug 修复
        ├── refactor/xxx    → 重构（不影响功能）
        └── chore/xxx       → 构建/依赖/配置调整
```

---

## 二、分支命名规范

格式：`类型/简短描述`，全小写，用 `-` 连接单词

| 类型 | 用途 | 示例 |
|------|------|------|
| `feature/` | 新功能 | `feature/user-management` |
| `fix/` | Bug 修复 | `fix/login-redirect-error` |
| `refactor/` | 代码重构 | `refactor/order-composable` |
| `chore/` | 依赖/配置/构建 | `chore/upgrade-vite-5` |
| `release/` | 版本发布准备 | `release/v1.2.0` |
| `hotfix/` | 生产紧急修复 | `hotfix/payment-crash` |

```bash
# 从 develop 创建功能分支
git checkout develop
git pull origin develop
git checkout -b feature/user-management
```

---

## 三、提交规范（Conventional Commits）

格式：`类型(范围): 描述`

```
feat(user): 新增用户管理列表页
fix(login): 修复登录后跳转路径错误
refactor(order): 将订单逻辑提取为 composable
perf(table): 大列表改用虚拟滚动
style(home): 修复按钮间距不一致
chore: 升级 vite 至 5.x
docs: 补充组件 props 注释
```

### 类型对照

| 类型 | 含义 | 是否影响版本号 |
|------|------|-------------|
| `feat` | 新功能 | minor ↑ |
| `fix` | Bug 修复 | patch ↑ |
| `perf` | 性能优化 | patch ↑ |
| `refactor` | 重构（不改功能） | 不影响 |
| `style` | 格式/样式（不改逻辑） | 不影响 |
| `docs` | 文档 | 不影响 |
| `test` | 测试 | 不影响 |
| `chore` | 构建/依赖/配置 | 不影响 |

### 提交前检查

```bash
# 提交前确认
git diff --staged    # 检查暂存内容是否符合预期
git status           # 确认没有意外文件被加入

# ❌ 禁止大而全的提交
git commit -m "feat: 完成用户模块"   # 模糊，难以追溯

# ✅ 小而准的提交，每次提交只做一件事
git commit -m "feat(user): 新增用户列表筛选功能"
git commit -m "feat(user): 新增用户新增/编辑弹窗"
git commit -m "fix(user): 修复用户状态切换后列表未刷新"
```

---

## 四、MR / PR 发起前自查清单

> 发起合并请求前必须全部确认，不通过不发起。

### 代码质量

- [ ] 删除所有 `console.log`
- [ ] 无 TypeScript 报错（`any` 已全部替换）
- [ ] 无 ESLint 报错
- [ ] 函数长度未超过 20 行
- [ ] 图片已压缩

### 功能自测

- [ ] 主流程正常（新增、编辑、删除、查询）
- [ ] 表单校验正常（必填、格式校验、防重复提交）
- [ ] Loading 状态正常（请求中按钮不可点击，结束后关闭）
- [ ] 空数据状态正常（列表为空有提示）
- [ ] 错误场景正常（接口失败有提示，不白屏）
- [ ] 移动端适配（如涉及 H5）

### 代码规范

- [ ] 组件代码顺序正确（类型 → Props/Emits → 响应式 → computed → composable → 方法 → 生命周期）
- [ ] 无多余 import（自动导入的 API 未手动引入）
- [ ] 路径使用 `@/` 别名
- [ ] CSS 无 `!important`（业务代码）、无魔法 z-index

### MR 描述规范

```markdown
## 改动内容
- 新增用户列表页，支持姓名和状态筛选
- 新增用户新增/编辑弹窗
- 新增用户删除（带二次确认）

## 接口变动
- 新增：GET /api/user/list
- 新增：POST /api/user/create

## 测试说明
- [x] 列表页正常展示
- [x] 新增/编辑保存后列表刷新
- [x] 删除后列表刷新
- [x] 必填校验正常

## 注意事项（给 Reviewer 的提示）
- UserFormModal 同时处理新增和编辑，通过 userId prop 区分
```

---

## 五、Code Review 规范

### Reviewer 必查点

**逻辑正确性**
- 边界条件是否处理（空数组、undefined、接口失败）
- 异步操作是否有 loading 保护和 finally 兜底
- 权限判断是否遗漏

**规范符合性**
- 是否违反 rules.md 中的规范（重点：自动导入、loading 位置、any 类型）
- 组件拆分是否合理（单组件是否过大）
- 是否引入了不必要的依赖

**可维护性**
- 函数命名是否见名知意
- 复杂逻辑是否有注释
- 是否有明显的重复代码可以抽取

### Review 反馈用语规范

```
# 必须修改（阻塞合并）
[阻塞] loading 没有放在 finally 中，请求失败时会一直转圈

# 建议修改（不阻塞合并，但推荐改）
[建议] 这段逻辑在 GoodsList 里也有，可以提取成 composable

# 提问 / 确认
[问题] 这里 status 为 0 时的处理是产品需求还是临时处理？

# 肯定
[✓] 这里用 readonly 保护 store 状态，写法很好
```

---

## 六、合并策略

```
功能分支 → develop：   Squash Merge（合并压缩为一个提交，保持主线简洁）
develop  → main：      Merge Commit（保留完整的 develop 历史）
hotfix   → main：      Cherry-pick 或直接 Merge，同步合回 develop
```

### 处理合并冲突

```bash
# 1. 更新 develop
git checkout develop
git pull origin develop

# 2. 回到功能分支，rebase 到最新 develop（推荐 rebase 而不是 merge）
git checkout feature/user-management
git rebase develop

# 3. 解决冲突后
git add .
git rebase --continue

# 4. 强制推送（rebase 后必须）
git push origin feature/user-management --force-with-lease
# 注意：--force-with-lease 比 --force 安全，若远端有新提交会拒绝推送
```

---

## 七、版本发布流程

```bash
# 1. 从 develop 创建 release 分支
git checkout develop
git checkout -b release/v1.2.0

# 2. 更新版本号（package.json）并提交
git commit -m "chore: release v1.2.0"

# 3. 合并到 main
git checkout main
git merge release/v1.2.0 --no-ff
git tag v1.2.0

# 4. 同步回 develop（release 分支可能有最后修改）
git checkout develop
git merge release/v1.2.0 --no-ff

# 5. 删除 release 分支
git branch -d release/v1.2.0
```

---

## 反模式检查清单

- [ ] ❌ 直接向 main / develop 推送代码 → 必须通过 MR
- [ ] ❌ 一个提交包含多个无关改动 → 拆分成多个小提交
- [ ] ❌ 提交信息写"修改"、"更新"、"fix bug" → 按 Conventional Commits 规范写
- [ ] ❌ 分支名用拼音或无意义字母 → 按命名规范起名
- [ ] ❌ 合并冲突用 `--force` 强推（覆盖他人代码）→ 用 `--force-with-lease`
- [ ] ❌ 长期不合入 develop 的功能分支 → 每天同步一次 develop，避免大量冲突
