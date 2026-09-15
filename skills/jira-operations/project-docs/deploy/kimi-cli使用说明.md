# Jira 清理工具 × Kimi CLI 使用说明（2026-08-10）

## 一、开发状态结论

依据 `project-docs/iterations/jira技能化/2026-08-09-二次设计.md` 与 `2026-08-09-验收.md`：

- **功能开发已完成**：12 个子命令（search / get / count-by / transitions / createmeta / fields / whoami / serverinfo / watch / create / update / apply）、169 个测试全绿（2026-08-11 实测，含 15 个需真实 Jira 的用例默认跳过）、两阶段写门禁（`create --preview` → 人确认 → `apply`）均已落地。
- **部署动作已完成**：技能真身位于 `.claude/skills/zq-jira-query/SKILL.md`，工程根 `SKILL.md` 为软链，配置 `jira_config.json` 在工程根，**含明文凭据且已入库**（2026-08-10 提交 93ff9be 已将其移出忽略列表，早期「凭据不进仓库」的说法已作废）；凭据治理单独立题处理，不在本主题范围内。
- **连通性曾实测通过（该结论已过期）**：2026-08-10 实测 `whoami` 返回已登录账号（即验收项 B3 通过）；Jira2 `http://10.18.20.137:8082` 可达（HTTP 200）。**该连通性结论是 2026-08-10 当次实测的快照，此后两个源均不可达，结论已过期**，不要拿它判断当前环境，用前自己现测一次。
- 验收文档中剩余的 B1/B2/B4 端到端场景与 A3/A12/A15 新会话行为项，属于「联网后补跑 / 新会话观察」类留痕项，不影响工具本身可用。

**结论：工具已完成开发，可以投入使用。**

## 二、是否适用于 Kimi CLI

**适用。** 依据 [Kimi Code 官方文档 — Agent Skills](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)：

- Kimi CLI 的技能就是「带 YAML frontmatter 的 SKILL.md」，本技能的 frontmatter 含必需的 `name` 与 `description`，格式完全兼容。
- Kimi CLI **不扫描 `.claude/skills/`**。它的项目级扫描目录是 **`.kimi-code/skills/` 和 `.agents/skills/`**（项目根 = 向上最近的 `.git` 所在目录）；用户级是 `~/.kimi-code/skills/` 和 `~/.agents/skills/`。优先级：**项目 > 用户 > 内置**。
- 因此本仓库已建好项目级入口：`.agents/skills/zq-jira-query/SKILL.md` 是指向 `.claude/skills/zq-jira-query/SKILL.md` 的软链（同一份文件，双侧等价）。

**与用户级旧版的关系**：`~/.agents/skills/zq-jira-query/` 存在 2026-05-20 的旧版技能（服务 Codex 端，走已废弃的 `jira_query.sh` + 旧配置格式）。由于「项目 > 用户」，**在本仓库内** Kimi 会加载新版技能，旧版被遮蔽；在别的目录下 Kimi 仍会加载旧版。这是有意为之，旧部署未做任何改动。

## 三、使用方法

### 1. 前置条件

| 项 | 说明 |
|---|---|
| 启动目录 | 必须在本工程根 `/Users/cy/MyWorkFactory/workspace/my-ai/zq-jira-query` 启动 `kimi`，否则项目级技能不会被扫描到 |
| 配置文件 | 工程根 `jira_config.json`（**含明文凭据、已入库**；凭据治理单独立题处理）。缺失时对照 `jira_config.example.json` 补齐 |
| 网络 | 两个源平级、没有主备之分：`Jira1`（`https://jira.trscd.com.cn`，自签名证书）与 `Jira2`（`http://10.18.20.137:8082`，需内网可达）各自是独立故障点，任一个不通都不算工具故障。每次操作到底用哪个源，见技能定义 `.claude/skills/zq-jira-query/SKILL.md` 的《选哪个 Jira 源（每次操作前必做）》一节，本文不重复 |
| 生效时机 | 技能列表在**会话启动时**加载。本次新增 `.agents/skills/` 入口后，需**新开一个 Kimi 会话**才会被加载 |

### 2. 日常使用（自然语言即可）

新开 Kimi 会话后，直接用自然语言发问，模型会按技能里的触发词自动唤起并调用 `scripts/jira_cli.py`：

- 「我有哪些 Jira」「当前有哪些待处理 Jira」
- 「看看 XMKFB 项目有哪些逾期任务」
- 「统计一下 TRS 项目各状态的任务数」
- 「TRS-123 这个 Jira 的详情是什么」
- 「帮我建一个 Jira」（走两阶段门禁，见下）

也可以手动唤起：`/skill:zq-jira-query`。

### 3. 创建 issue（两阶段写门禁，强制）

1. 模型先跑 `create --preview` 生成预览并展示（项目、类型、标题、描述、自定义字段）；
2. **你明确说确认后**，模型才用返回的 `plan_id` 执行 `apply --plan-id` 落单；
3. plan 5 分钟过期、一次性消费；被拒就重新 preview。
4. 全生命周期写操作（含建子任务、改字段、流转状态、评论、分配、关联、工时、附件、删除及通用 `api`）均遵循两阶段门禁。

### 4. 常见问题（实测坑）

- **JQL 状态名**：本 Jira 装了中文语言包，但内置状态在 JQL 里必须写英文原始名（`Done` / `Open` / `In Progress`）；团队自建中文状态（测试、联调中）反而按中文名写。报 `JQL_INVALID` 且提示「没有该值」时先怀疑这条。
- **参数位置**：`--source`、`--config` 必须写在子命令**之前**（`jira_cli.py --source Jira1 whoami`），写在后面会直接报参数错误。
- **CAPTCHA 锁定**（`CAPTCHA_LOCKED`）：必须浏览器登录 Jira 解除，期间不要重试，越试锁越久。
- **结果截断**：输出带 `truncated: true` 或 `partial: true` 时，结论必须声明「结果不完整」，不能当全量数据。

### 5. 排障速查

| 现象 | 处置 |
|---|---|
| 发问后模型没调用技能 | 确认是在工程根启动的**新会话**；可 `/skill:zq-jira-query` 手动唤起 |
| `CONFIG_ERROR` | 依次检查：工程根 `jira_config.json` 是否存在、JSON 是否合法、`default_source` 与某个 `sources[].name` 是否逐字符一致；还有一条最容易漏——`--source` 传的源名与 `sources[].name` 不逐字一致（**大小写敏感、两端空格不会被自动去掉**） |
| `NETWORK_ERROR` / HTTP 000 | 内网/VPN 未连；先 `curl -sS -o /dev/null -w "%{http_code}" http://10.18.20.137:8082/rest/api/2/serverInfo` 自检 |
| 命令 file not found | 仓库被移动过。按 `SKILL.md` 顶部「维护说明」用 `sed` 整体替换绝对路径前缀 |

更完整的命令细节（全量子命令参数、error_code 全表、审计与 state 目录说明）见技能定义 `.claude/skills/zq-jira-query/SKILL.md` 及其 `references/` 下的速查文档。
