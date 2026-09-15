# -*- coding: utf-8 -*-
"""Jira 更新能力 · 真实环境集成测试（禁止 mock，全部连真 Jira）。

测试目标
--------
用真实 Jira2 源与真实 `jira_config.json`，端到端验证 `jira_cli.py update --preview`
到 `jira_cli.py apply --plan-id` 这条链路的业务行为：日期换算与回显、混合改字段加推状态、
批量幂等三分、计划过期与一次性消费、写源准入、经办人名称解析三分支、标签整体覆盖、
标题与描述的覆盖式写入与全文留痕、已关闭单的两条路径。
每个用例都以子进程方式调用 `scripts/jira_cli.py`（跟人和模型实际用法完全一致），
只断言命令的退出码、JSON 返回体、以及回读 Jira 得到的真实结果，不打任何桩。

依赖环境
--------
1. 真实可达的 Jira2 源（`jira_config.json` 里 `default_source = Jira2`），账号具备
   XMKFB 项目的改单与流转权限。网络不可达时这些用例会直接失败，属预期。
2. 靶单：全部是标题带「联调验证-可删除」的自建单，key 经环境变量 `JIRA_IT_KEYS`
   传入（逗号分隔，按下表**按序号**取用；给少了对应用例会 skip 并说明缺第几个）：

     序号 0  长期靶单        —— 只改普通字段、不推状态（场景 1、8、9、10、11、12 复用）
     序号 1  一次性靶单      —— 场景 2 多跳推状态
     序号 2  一次性靶单      —— 场景 3 改日期 + 推状态
     序号 3  一次性靶单      —— 场景 4 批量三条之一（当前不在目标状态）
     序号 4  一次性靶单      —— 场景 4 批量三条之二（当前不在目标状态）
     序号 5  一次性靶单      —— 场景 4 批量三条之三（**必须已经处于目标状态**，用于验幂等跳过）
     序号 6  已关闭靶单      —— 场景 13（`statusCategory.key == "done"`）

3. 可选环境变量：
     `JIRA_IT_TARGET_STATUS`     推状态用的口语词，缺省 `完成`（2026-08-12 实测 Jira2 完成类状态显示名即「完成」，原样透传不映射）
     `JIRA_IT_REOPEN_STATUS`     场景 13 把已关闭单推回的目标状态名，缺省 `进行中`
     `JIRA_IT_ASSIGNEE_UNIQUE`   场景 10 唯一命中分支用的真实姓名（不给则 skip）
     `JIRA_IT_ASSIGNEE_AMBIGUOUS` 场景 10 多命中分支用的姓氏（不给则 skip）
     `JIRA_IT_SKIP_SLOW=1`       跳过需要干等 5 分钟的过期用例（会 skip 并写明原因，不静默通过）

数据准备方式
------------
靶单由测试人员在 Jira 网页上手工新建（标题统一写「联调验证-可删除」），本文件不自动建单；
每个用例内部需要的前置数据（比如场景 11 要求「已有两个标签」、场景 12 要求「描述是已知原文」）
由用例自己先用一次正常的 preview + apply 铺好，再开始正式断言，保证可重复执行。

善后策略
--------
- 只改普通字段的场景（1、8、11、12）复用长期靶单，用例结束在 finally 里把
  截止日期 / 标签 / 标题 / 描述改回跑之前读到的原值（截止日期原本为空的用 `duedate=null` 清空）。
- **会改状态的场景（2、3、4、13）每轮需要新建一次性靶单**：状态回滚在 Jira 工作流里
  常常物理不可行，靶单一旦被推到「已完成」多半推不回「待办」，复用就没有合格起点了。
  用例结束会**尽力**把状态推回原样；推不回时不静默吞掉，而是登记到 `RESTORE_LOG`，
  在 tearDownClass 里打印出来，由测试人员抄进
  `project-docs/iterations/jira技能化/2026-08-09-验收.md` 第五节登记表
  （登记内容：单号、遗留状态、推不回的原因）。
- 场景 10（经办人）与场景 11 第二段（标签整体覆盖的取消分支）**只跑预览不执行**，Jira 侧零改动。

跑法
----
    JIRA_IT=1 JIRA_IT_KEYS=XMKFB-123 python3 -m unittest discover tests/integration

不带 `JIRA_IT=1` 时本文件全部 skip，所以默认的
`python3 -m unittest discover tests` 依然只跑离线单测、且保持全绿。
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JIRA_CLI = os.path.join(ROOT, "scripts", "jira_cli.py")
PLANS_DIR = os.path.join(ROOT, "state", "plans")
AUDIT_LOG = os.path.join(ROOT, "state", "audit.log")

# 靶单 key 列表：模块导入期只读环境变量，不连网、不读 jira_config.json
TARGET_KEYS = [k.strip() for k in os.environ.get("JIRA_IT_KEYS", "").split(",") if k.strip()]
TARGET_STATUS = os.environ.get("JIRA_IT_TARGET_STATUS", "完成")
REOPEN_STATUS = os.environ.get("JIRA_IT_REOPEN_STATUS", "进行中")

# 善后登记：推不回原状态的靶单在这里留痕，tearDownClass 统一打印
RESTORE_LOG = []


@unittest.skipUnless(os.environ.get("JIRA_IT") == "1", "未开启真实 Jira 集成测试")
class JiraUpdateIntegrationTest(unittest.TestCase):
    """update 能力的真实环境集成测试。用例之间互不共享内存状态，靠靶单本身串联。"""

    # ------------------------------------------------------------ 基础设施

    @classmethod
    def tearDownClass(cls):
        if RESTORE_LOG:
            sys.stderr.write("\n===== 善后登记（请抄进验收文档第五节登记表）=====\n")
            for line in RESTORE_LOG:
                sys.stderr.write("  " + line + "\n")
            sys.stderr.write("=" * 46 + "\n")

    def _run(self, argv, timeout=180):
        """子进程调用 jira_cli.py，返回 (退出码, 解析后的 JSON 字典)。

        CLI 约定 stdout 只有一行 JSON；解析不了就直接判用例失败并把原始输出摊开，
        避免把「脚本崩了」误读成「业务断言不过」。
        """
        proc = subprocess.run([sys.executable, JIRA_CLI] + argv,
                              cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        raw = (proc.stdout or "").strip().splitlines()
        self.assertTrue(raw, "命令没有任何 stdout 输出，argv=%s，stderr=%s" % (argv, proc.stderr))
        try:
            out = json.loads(raw[-1])
        except ValueError:
            self.fail("命令 stdout 不是合法 JSON，argv=%s\nstdout=%s\nstderr=%s"
                      % (argv, proc.stdout, proc.stderr))
        return proc.returncode, out

    def _target_key(self, index, purpose):
        """按序号取靶单；没给够就 skip 并说明缺的是第几个、用途是什么。"""
        if len(TARGET_KEYS) <= index:
            self.skipTest("环境变量 JIRA_IT_KEYS 需要第 %d 个靶单（用途：%s），当前只提供了 %d 个"
                          % (index + 1, purpose, len(TARGET_KEYS)))
        return TARGET_KEYS[index]

    def _get_issue(self, key):
        """回读 Jira 上这条单的真实字段（用只读 get 子命令，走的是同一套鉴权与 base_url）。"""
        code, out = self._run(["get", "--key", key])
        self.assertEqual(0, code, "回读靶单 %s 失败：%s" % (key, out))
        self.assertTrue(out.get("ok"), "回读靶单 %s 返回 ok=false：%s" % (key, out))
        return out["issue"]["fields"]

    def _status_of(self, key):
        """返回 (状态显示名, statusCategory.key)。"""
        status = self._get_issue(key).get("status") or {}
        return status.get("name"), ((status.get("statusCategory") or {}).get("key"))

    def _preview(self, argv, timeout=180):
        """跑一次 update --preview，返回 (退出码, 返回体)。不替调用方断言成败。"""
        return self._run(["update"] + argv + ["--preview"], timeout=timeout)

    def _apply(self, plan_id, timeout=180):
        return self._run(["apply", "--plan-id", plan_id], timeout=timeout)

    def _preview_ok(self, argv, timeout=180):
        """预览必须成功的场合用它：失败直接判用例不过，并把 error_code 摊给排查用。"""
        code, out = self._preview(argv, timeout=timeout)
        self.assertEqual(0, code, "预览应当成功，实际退出码 %d，返回=%s" % (code, out))
        self.assertTrue(out.get("ok"), "预览应当 ok=true，实际返回=%s" % out)
        return out

    def _apply_ok(self, plan_id, timeout=180):
        """apply 必须整批跑完：无论逐条成败，退出码恒为 0、ok 恒为 true（契约 §10）。"""
        code, out = self._apply(plan_id, timeout=timeout)
        self.assertEqual(0, code, "apply 整批跑完退出码应为 0，实际 %d，返回=%s" % (code, out))
        self.assertTrue(out.get("ok"), "apply 整批跑完 ok 应为 true，实际返回=%s" % out)
        return out

    def _plan_files(self):
        """state/plans 下的文件名集合，用于断言「预览期问题不落盘」。"""
        if not os.path.isdir(PLANS_DIR):
            return set()
        return set(os.listdir(PLANS_DIR))

    def _do_update(self, argv, timeout=180):
        """预览 + 确认执行的完整两阶段，返回 (预览返回体, 执行返回体)。"""
        preview = self._preview_ok(argv, timeout=timeout)
        report = self._apply_ok(preview["plan_id"], timeout=timeout)
        return preview, report

    def _skip_if_status_blocked(self, code, out, scene):
        """真实工作流拓扑不支持时按设计稿要求 skip（写明原因，不静默当成通过）。"""
        if code == 1 and out.get("error_code") == "PREVIEW_HAS_BLOCKERS":
            reasons = "；".join(str(b.get("reason")) for b in out.get("blockers") or [])
            self.skipTest("%s 前置不满足：靶项目工作流不支持本次状态流转（%s）" % (scene, reasons))

    # ------------------------------------------------------------ 善后动作

    def _restore_duedate(self, key, old_duedate):
        """把截止日期改回原值；原本为空就用 duedate=null 清空。"""
        value = "duedate=%s" % (old_duedate if old_duedate else "null")
        code, preview = self._preview(["--key", key, "--set", value])
        if code != 0:
            RESTORE_LOG.append("%s 截止日期未能恢复（预览失败：%s）" % (key, preview.get("error")))
            return
        self._apply(preview["plan_id"])

    def _restore_labels(self, key, old_labels):
        code, preview = self._preview(
            ["--key", key, "--set", "labels=" + json.dumps(old_labels, ensure_ascii=False)])
        if code != 0:
            RESTORE_LOG.append("%s 标签未能恢复（预览失败：%s）" % (key, preview.get("error")))
            return
        self._apply(preview["plan_id"])

    def _restore_status(self, key, old_status_name):
        """尽力把状态推回原样；推不回就如实登记，绝不假装成功。"""
        current, _ = self._status_of(key)
        if current == old_status_name:
            return
        code, preview = self._preview(["--key", key, "--status", old_status_name,
                                       "--allow-closed-transition"])
        if code != 0:
            RESTORE_LOG.append(
                "%s 状态推不回「%s」，遗留在「%s」；原因：预览被拒 %s"
                % (key, old_status_name, current, preview.get("error_code")))
            return
        self._apply_ok(preview["plan_id"])
        final, _ = self._status_of(key)
        if final != old_status_name:
            RESTORE_LOG.append(
                "%s 状态推不回「%s」，遗留在「%s」；原因：工作流无回退路径（执行后仍未回到原状态）"
                % (key, old_status_name, final))

    # ------------------------------------------------------------ 场景 1

    def test_场景01_单条改截止时间到明天(self):
        """场景 1：给一条任务改截止时间到明天（主流程）。"""
        key = self._target_key(0, "长期靶单，只改普通字段")
        before = self._get_issue(key)
        old_duedate = before.get("duedate")
        old_status_name = (before.get("status") or {}).get("name")
        expected = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            preview = self._preview_ok(["--key", key, "--set", "duedate=明天"])
            text = preview["preview_text"]
            self.assertIn("操作源：", text, "预览首行必须回显操作源")
            self.assertIn("基准日：%s（本机当天）" % date.today().strftime("%Y-%m-%d"), text,
                          "预览必须写明基准日是本机当天")
            self.assertIn("本次将修改 1 条单", text, "预览必须写明本次条数")
            self.assertIn(key, text, "预览必须逐条列出单号")
            self.assertRegex(text, r"%s（周[一二三四五六日]" % expected,
                             "「明天」必须换算成绝对日期并带星期")
            self.assertIn("产生变更通知", text, "预览必须带固定措辞的通知提示")
            self.assertIn("本预览 5 分钟内有效", text, "单条预览的有效期应为 5 分钟")
            self.assertIn("本工具不提供撤销。", text, "预览末行必须写明不提供撤销")
            self.assertEqual(300, preview["ttl_seconds"], "单条预览 TTL 应为 300 秒")

            report = self._apply_ok(preview["plan_id"])
            self.assertEqual({"success": 1, "skipped": 0, "failed": 0}, report["counts"],
                             "本条应当执行成功：%s" % report.get("result_text"))
            self.assertFalse(report["has_failures"], "本次不应有失败条目")

            after = self._get_issue(key)
            self.assertEqual(expected, after.get("duedate"),
                             "Jira 上的截止日期应当变成明天对应的绝对日期")
            self.assertEqual(old_status_name, (after.get("status") or {}).get("name"),
                             "只改截止日期时状态不得变化")

            audit = self._read_audit_records(key)
            self.assertTrue(audit, "执行记录里应当能查到这条单的审计行")
            dumped = json.dumps(audit[-1], ensure_ascii=False)
            self.assertIn(expected, dumped, "审计里应当留有改后值")
        finally:
            self._restore_duedate(key, old_duedate)

    # ------------------------------------------------------------ 场景 2

    def test_场景02_多跳把待办单推到完成(self):
        """场景 2：一句「标记完成」推到已完成（多跳）。工作流允许直达时按设计稿 skip。"""
        key = self._target_key(1, "一次性靶单，验多跳推状态")
        old_status_name, _ = self._status_of(key)
        code, preview = self._preview(["--key", key, "--status", TARGET_STATUS])
        self._skip_if_status_blocked(code, preview, "场景 2")
        self.assertEqual(0, code, "预览应当成功，实际返回=%s" % preview)

        item = preview["preview"]["items"][0]
        status_change = item.get("status_change") or {}
        if status_change.get("reachability") != "predicted":
            self.skipTest("场景 2 前置不满足：靶项目工作流允许「%s」直达「%s」，"
                          "真实环境构造不出多跳，多跳寻路逻辑由单测承担"
                          % (old_status_name, status_change.get("to_name")))
        try:
            text = preview["preview_text"]
            self.assertIn("需多步流转", text, "多跳条目必须在预览里提示会自动寻路")
            self.assertIn("若需多跳，后续跳的必填项按同样规则自动填充，预览无法提前列出。", text,
                          "多跳时必须提示后续跳的必填项无法提前列出")
            if TARGET_STATUS != status_change.get("to_name"):
                self.assertIn("你说的「%s」已按约定映射为目标状态「%s」。"
                              % (TARGET_STATUS, status_change.get("to_name")), text,
                              "口语词被映射时必须给出映射说明")

            report = self._apply_ok(preview["plan_id"])
            self.assertEqual({"success": 1, "skipped": 0, "failed": 0}, report["counts"],
                             "多跳流转应当整条成功：%s" % report.get("result_text"))
            hops = ((report["items"][0].get("status_result") or {}).get("hops")) or []
            self.assertGreaterEqual(len(hops), 2, "预览判定为多跳时执行期应当走过至少两跳")
            for hop in hops:
                self.assertTrue(hop.get("to_id") and hop.get("to_name"),
                                "审计与报告里每一跳都要留下 to.id 与 to.name：%s" % hop)
            final_name, _ = self._status_of(key)
            self.assertEqual(status_change.get("to_name"), final_name,
                             "执行后靶单应当停在目标状态")
        finally:
            self._restore_status(key, old_status_name)

    # ------------------------------------------------------------ 场景 3

    def test_场景03_同时改日期和推状态(self):
        """场景 3：一句话同时改日期和推状态（混合，先字段后状态）。"""
        key = self._target_key(2, "一次性靶单，验改日期 + 推状态")
        before = self._get_issue(key)
        old_duedate = before.get("duedate")
        old_status_name = (before.get("status") or {}).get("name")
        # 「下周一」= 今天所在周的下一个自然周的周一（周首为周一）
        today = date.today()
        expected = (today - timedelta(days=today.weekday()) + timedelta(days=7)).strftime("%Y-%m-%d")

        code, preview = self._preview(["--key", key, "--set", "duedate=下周一",
                                       "--status", TARGET_STATUS])
        self._skip_if_status_blocked(code, preview, "场景 3")
        self.assertEqual(0, code, "预览应当成功，实际返回=%s" % preview)
        try:
            item = preview["preview"]["items"][0]
            self.assertEqual(expected, item["put_payload"]["duedate"],
                             "「下周一」必须按下一个自然周解释")
            self.assertIsNotNone(item.get("status_change"), "本次应当同时包含状态改动")
            self.assertIn("截止日期：", preview["preview_text"], "预览必须列出截止日期改动")
            self.assertIn("状态：", preview["preview_text"], "预览必须列出状态改动")

            report = self._apply_ok(preview["plan_id"])
            self.assertEqual({"success": 1, "skipped": 0, "failed": 0}, report["counts"],
                             "字段与状态都改成功时应当只算一次成功：%s" % report.get("result_text"))
            reported = report["items"][0]
            self.assertTrue(reported.get("field_changes"), "报告里应当留有日期项的改前改后值")
            self.assertTrue(reported.get("status_result"), "报告里应当留有状态项的改前改后值")

            after = self._get_issue(key)
            self.assertEqual(expected, after.get("duedate"), "截止日期应当已生效")
            self.assertEqual((item["status_change"] or {}).get("to_name"),
                             (after.get("status") or {}).get("name"),
                             "状态应当已推进到目标状态")
        finally:
            self._restore_status(key, old_status_name)
            self._restore_duedate(key, old_duedate)

    # ------------------------------------------------------------ 场景 4

    def test_场景04_批量三条改状态含一条幂等(self):
        """场景 4：三条单一起改状态，其中一条本来就是目标状态（幂等三分）。"""
        keys = [self._target_key(3, "场景 4 批量靶单之一"),
                self._target_key(4, "场景 4 批量靶单之二"),
                self._target_key(5, "场景 4 批量靶单之三（须已处于目标状态）")]
        old_status = {k: self._status_of(k)[0] for k in keys}

        argv = []
        for k in keys:
            argv += ["--key", k]
        argv += ["--status", TARGET_STATUS, "--complete-set"]
        code, preview = self._preview(argv)
        self._skip_if_status_blocked(code, preview, "场景 4")
        self.assertEqual(0, code, "批量预览应当成功，实际返回=%s" % preview)

        items = preview["preview"]["items"]
        no_change = [i["key"] for i in items if i.get("no_change")]
        if len(no_change) != 1:
            self.skipTest("场景 4 前置不满足：三条靶单里恰好一条已处于目标状态才能验幂等三分，"
                          "当前已处于目标状态的是 %s（当前状态：%s）" % (no_change, old_status))
        try:
            text = preview["preview_text"]
            self.assertIn("本次将修改 3 条单", text, "批量预览必须写明总条数")
            for k in keys:
                self.assertIn(k, text, "批量预览必须逐条列出单号 %s" % k)
            self.assertIn("本预览 15 分钟内有效", text, "批量预览的有效期应为 15 分钟")
            self.assertEqual(900, preview["ttl_seconds"], "批量预览 TTL 应为 900 秒")

            report = self._apply_ok(preview["plan_id"], timeout=300)
            self.assertEqual({"success": 2, "skipped": 1, "failed": 0}, report["counts"],
                             "应当成功两条、跳过一条、失败零条：%s" % report.get("result_text"))
            self.assertFalse(report["has_failures"], "幂等跳过不得算作失败")
            skipped = [i for i in report["items"] if i["result"] == "skipped"]
            self.assertEqual(1, len(skipped), "跳过条目应当只有一条")
            self.assertIn("值已是目标值", skipped[0]["reason"],
                          "幂等跳过的原因必须写「值已是目标值」")
            self.assertEqual(skipped[0]["key"], no_change[0], "跳过的应当是本来就在目标状态的那条")
            self.assertNotIn(skipped[0]["key"], report["resume_keys"],
                             "幂等跳过的单不进可补做清单")

            target_name = None
            for i in items:
                if i.get("status_change"):
                    target_name = i["status_change"]["to_name"]
                    break
            for k in keys:
                self.assertEqual(target_name, self._status_of(k)[0],
                                 "执行后三条单都应当处于目标状态：%s" % k)
        finally:
            for k in keys:
                self._restore_status(k, old_status[k])

    # ------------------------------------------------------------ 场景 6

    def test_场景06_字段改成功但状态卡住的半成品(self):
        """场景 6：字段改成功、状态卡在半路（半成品如实上报）。

        构造这个前置需要在预览生成之后、apply 执行之前，由测试人员在 Jira 网页上把靶单
        推到一个「后续走不到目标状态」的死路分支上，而这条分支是否存在完全取决于
        管理员配置的工作流拓扑，自动化用例既构造不出分支、也插不进这个时间窗。
        按设计稿要求这里 skip 并写清原因，不静默当成通过；半成品的逻辑由
        tests/test_update_apply.py 的执行侧单测承担。
        """
        self.skipTest("场景 6 前置不满足：半成品需要在预览之后由测试人员在 Jira 网页把靶单推到"
                      "走不到目标状态的死路分支上，靶项目工作流是否存在这种分支由管理员配置决定，"
                      "自动化用例无法构造；请按文件末尾的人工场景说明手工执行并登记验收记录")

    # ------------------------------------------------------------ 场景 8

    def test_场景08_预览过期后确认被拒(self):
        """场景 8 上半：单条预览（300 秒）晾过期后再确认，必须被拒且 Jira 零改动。"""
        if os.environ.get("JIRA_IT_SKIP_SLOW") == "1":
            self.skipTest("场景 8 过期分支需要真实干等 300 秒，已被 JIRA_IT_SKIP_SLOW=1 显式跳过；"
                          "本轮验收记录须标注该分支未跑")
        key = self._target_key(0, "长期靶单，只改普通字段")
        old_duedate = self._get_issue(key).get("duedate")

        preview = self._preview_ok(["--key", key, "--set", "duedate=明天"])
        self.assertEqual(300, preview["ttl_seconds"], "单条预览 TTL 应为 300 秒")
        expires = datetime.fromisoformat(preview["expires_at"])
        wait = (expires - datetime.now(expires.tzinfo)).total_seconds() + 5
        self.assertLess(wait, 400, "单条 TTL 不应超过 5 分钟出头，等待时间异常：%s 秒" % wait)
        if wait > 0:
            time.sleep(wait)

        code, out = self._apply(preview["plan_id"])
        self.assertEqual(1, code, "过期计划确认应当退出码 1，实际返回=%s" % out)
        self.assertEqual("PLAN_REJECTED", out.get("error_code"), "过期计划应当报 PLAN_REJECTED")
        self.assertIn("过期", out.get("error", ""), "拒绝原因应当写明计划已过期")
        self.assertEqual(old_duedate, self._get_issue(key).get("duedate"),
                         "计划过期时 Jira 上不得发生任何改动")

    def test_场景08_重复确认被一次性消费拒绝(self):
        """场景 8 下半：同一份 plan_id 确认第二次，必须被拒，不把改动做两遍。"""
        key = self._target_key(0, "长期靶单，只改普通字段")
        old_duedate = self._get_issue(key).get("duedate")
        expected = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            preview = self._preview_ok(["--key", key, "--set", "duedate=明天"])
            plan_id = preview["plan_id"]
            report = self._apply_ok(plan_id)
            self.assertEqual(1, report["counts"]["success"], "第一次确认应当执行成功")
            self.assertEqual(expected, self._get_issue(key).get("duedate"), "第一次确认应当已生效")

            code, out = self._apply(plan_id)
            self.assertEqual(1, code, "重复确认应当退出码 1，实际返回=%s" % out)
            self.assertEqual("PLAN_REJECTED", out.get("error_code"), "重复确认应当报 PLAN_REJECTED")
            self.assertIn("一次性消费", out.get("error", ""),
                          "拒绝原因应当写明计划已被使用过（一次性消费）")
            self.assertEqual(expected, self._get_issue(key).get("duedate"),
                             "重复确认不得把同一批改动再做一遍")
        finally:
            self._restore_duedate(key, old_duedate)

    # ------------------------------------------------------------ 场景 9

    def test_场景09_对非默认源发起修改被拒(self):
        """场景 9：对未开放写能力的源（Jira1）发起修改，必须在联网之前就被拒。"""
        key = self._target_key(0, "任意真实靶单，仅用于拼出一条完整命令")
        before = self._plan_files()
        started = time.time()
        code, out = self._run(["--source", "Jira1", "update", "--key", key,
                               "--set", "duedate=明天", "--preview"])
        elapsed = time.time() - started
        self.assertEqual(2, code, "写源准入失败属本地校验，退出码应为 2，实际返回=%s" % out)
        self.assertEqual("WRITE_SOURCE_NOT_ALLOWED", out.get("error_code"),
                         "指定未开放写能力的源应当报 WRITE_SOURCE_NOT_ALLOWED，"
                         "不是 NETWORK_ERROR：拒绝必须发生在联网之前")
        self.assertIn("404", out.get("hint", ""), "hint 里应当写明 Jira1 的 serverInfo 实测返回 404")
        self.assertIn("临时", out.get("hint", ""), "hint 里应当写明该限制是临时的、排查后会解除")
        self.assertLess(elapsed, 60,
                        "写源准入是纯本地校验，应当立刻返回，不该等到 Jira1 网络超时（实测 %.1f 秒）"
                        % elapsed)
        self.assertEqual(before, self._plan_files(),
                         "被写源准入拒绝的预览不得在 state/plans 下落任何文件")

    # ------------------------------------------------------------ 场景 10

    def test_场景10_经办人唯一命中显示人名加账号(self):
        """场景 10 分支一：唯一命中，预览要显示人能核对的「姓名（账号 xxx）」，只预览不执行。"""
        name = os.environ.get("JIRA_IT_ASSIGNEE_UNIQUE")
        if not name:
            self.skipTest("未提供 JIRA_IT_ASSIGNEE_UNIQUE（一个在真实 Jira 上唯一命中的姓名），"
                          "无法验证经办人唯一命中分支")
        key = self._target_key(0, "长期靶单，仅用于预览")
        before = self._get_issue(key)
        preview = self._preview_ok(["--key", key, "--set", "assignee=%s" % name])
        text = preview["preview_text"]
        self.assertIn("经办人：", text, "预览必须列出经办人改动")
        self.assertRegex(text, r"（账号 [^）]+）", "经办人新值必须显示成「姓名（账号 xxx）」便于人工核对")
        item = preview["preview"]["items"][0]
        self.assertIn("name", item["put_payload"]["assignee"],
                      "经办人载荷应当解析成 {name: 账号}")
        # 只预览不执行：这份 plan 不 apply，Jira 侧零改动
        self.assertEqual(before.get("assignee"), self._get_issue(key).get("assignee"),
                         "只跑预览时 Jira 上的经办人不得变化")

    def test_场景10_经办人查无此人(self):
        """场景 10 分支二：零命中，报 FIELD_VALUE_NO_MATCH，且不落盘。"""
        key = self._target_key(0, "长期靶单，仅用于预览")
        before = self._plan_files()
        code, out = self._preview(["--key", key, "--set", "assignee=不存在的联调验证用户zzz"])
        self.assertEqual(1, code, "名称解析失败属预览联网期业务失败，退出码应为 1，实际返回=%s" % out)
        self.assertEqual("FIELD_VALUE_NO_MATCH", out.get("error_code"),
                         "查无此人应当报 FIELD_VALUE_NO_MATCH")
        self.assertEqual("assignee", out.get("field"), "载荷里应当带上出问题的字段名")
        self.assertEqual([], out.get("candidates"), "零命中时候选清单应当为空")
        self.assertEqual(before, self._plan_files(), "预览期问题不得在 state/plans 下落任何文件")

    def test_场景10_经办人多命中列出候选(self):
        """场景 10 分支三：多命中，摆出候选清单让人挑（不超过 10 条并标注是否还有更多），且不落盘。"""
        keyword = os.environ.get("JIRA_IT_ASSIGNEE_AMBIGUOUS")
        if not keyword:
            self.skipTest("未提供 JIRA_IT_ASSIGNEE_AMBIGUOUS（一个在真实 Jira 上会多命中的姓氏），"
                          "无法验证经办人多命中分支")
        key = self._target_key(0, "长期靶单，仅用于预览")
        before = self._plan_files()
        code, out = self._preview(["--key", key, "--set", "assignee=%s" % keyword])
        if code == 1 and out.get("error_code") == "FIELD_VALUE_NO_MATCH":
            self.skipTest("场景 10 多命中分支前置不满足：关键词「%s」在真实 Jira 上零命中，"
                          "请换一个确实有多个同姓用户的姓氏" % keyword)
        self.assertEqual(1, code, "多命中属预览联网期业务失败，退出码应为 1，实际返回=%s" % out)
        self.assertEqual("FIELD_VALUE_AMBIGUOUS", out.get("error_code"),
                         "多命中应当报 FIELD_VALUE_AMBIGUOUS")
        self.assertEqual("assignee", out.get("field"), "载荷里应当带上出问题的字段名")
        candidates = out.get("candidates") or []
        self.assertGreater(len(candidates), 1, "多命中时应当摆出多个候选")
        self.assertLessEqual(len(candidates), 10, "候选清单最多 10 条")
        for c in candidates:
            self.assertTrue(c.get("display") and c.get("id"),
                            "每个候选都要有可核对的显示名与账号：%s" % c)
        self.assertIn("has_more", out, "候选清单必须标注是否还有更多")
        self.assertEqual(before, self._plan_files(), "预览期问题不得在 state/plans 下落任何文件")

    # ------------------------------------------------------------ 场景 11

    def test_场景11_标签整体覆盖并列出将被移除项(self):
        """场景 11：标签是整体覆盖，预览要把将被顶掉的项列出来。"""
        key = self._target_key(0, "长期靶单，只改普通字段")
        old_labels = list(self._get_issue(key).get("labels") or [])
        base = ["线上问题", "二期"]
        try:
            # 数据准备：先把标签铺成已知的两个，保证用例可重复跑
            self._do_update(["--key", key,
                             "--set", "labels=" + json.dumps(base, ensure_ascii=False)])
            self.assertEqual(set(base), set(self._get_issue(key).get("labels") or []),
                             "数据准备失败：标签未铺成 [线上问题, 二期]")

            # 第一段：再加一个标签，预览必须写出全量旧值 → 全量新值
            merged = base + ["需回归"]
            preview = self._preview_ok(
                ["--key", key, "--set", "labels=" + json.dumps(merged, ensure_ascii=False)])
            self.assertIn("标签：[线上问题, 二期] → [线上问题, 二期, 需回归]", preview["preview_text"],
                          "预览必须完整写出标签的全量旧值与全量新值")
            self.assertNotIn("将被移除", preview["preview_text"],
                             "本次只是追加，不应出现将被移除提示")
            report = self._apply_ok(preview["plan_id"])
            self.assertEqual(1, report["counts"]["success"], "追加标签应当执行成功")
            self.assertEqual(set(merged), set(self._get_issue(key).get("labels") or []),
                             "确认后三个标签都应当在，原有两个不得丢失")

            # 第二段：改成只留一个，预览要列出将被移除项；看完回「取消」——不 apply
            preview2 = self._preview_ok(
                ["--key", key, "--set", 'labels=["需回归"]'])
            text2 = preview2["preview_text"]
            self.assertIn("标签：[线上问题, 二期, 需回归] → [需回归]", text2,
                          "覆盖式修改必须写出全量对照")
            self.assertIn("将被移除：", text2, "被顶掉的标签必须单起一行列出")
            self.assertIn("线上问题", text2.split("将被移除：")[1].splitlines()[0],
                          "将被移除的项里应当包含「线上问题」")
            self.assertIn("二期", text2.split("将被移除：")[1].splitlines()[0],
                          "将被移除的项里应当包含「二期」")
            self.assertEqual(set(merged), set(self._get_issue(key).get("labels") or []),
                             "回「取消」不执行时 Jira 上标签一个都不许变")
        finally:
            self._restore_labels(key, old_labels)

    # ------------------------------------------------------------ 场景 12

    def test_场景12_单条改标题与描述并可从留痕回捞旧文(self):
        """场景 12：单条改标题与描述（覆盖式写入），旧值必须全文留痕、可据此手工恢复。"""
        key = self._target_key(0, "长期靶单，只改普通字段")
        before = self._get_issue(key)
        old_summary = before.get("summary")
        old_description = before.get("description")
        stamp = datetime.now().strftime("%H%M%S")
        原文 = "联调验证-可删除 原始描述 %s\n\n- 列表项一\n- 列表项二\n\n**加粗片段**\n" % stamp
        新描述 = "联调验证-可删除 新描述 %s\n\n- 新列表项\n\n**新的加粗片段**\n" % stamp
        新标题 = "联调验证-可删除 新标题 %s" % stamp
        tmpdir = tempfile.mkdtemp(prefix="jira_it_")
        原文文件 = os.path.join(tmpdir, "old_desc.md")
        新文件 = os.path.join(tmpdir, "new_desc.md")
        with open(原文文件, "w", encoding="utf-8") as f:
            f.write(原文)
        with open(新文件, "w", encoding="utf-8") as f:
            f.write(新描述)
        try:
            # 数据准备：先把描述铺成已知原文（转换后的 wiki 正文即为「旧描述原文」的比对基准）
            prep_preview, _ = self._do_update(["--key", key, "--description-file", 原文文件])
            原文_wiki = prep_preview["preview"]["items"][0]["put_payload"]["description"]
            self.assertEqual(原文_wiki, self._get_issue(key).get("description"),
                             "数据准备失败：描述未铺成已知原文")

            # 第一步：单条改标题
            preview = self._preview_ok(["--key", key, "--set", "summary=%s" % 新标题])
            self.assertIn("标题：%s → %s" % (old_summary, 新标题),
                          preview["preview_text"], "预览必须写出旧标题 → 新标题")
            self._apply_ok(preview["plan_id"])
            self.assertEqual(新标题, self._get_issue(key).get("summary"), "标题应当已改成新值")

            # 第二步：单条改描述（正文走 --description-file，Markdown 转 wiki）
            preview2 = self._preview_ok(["--key", key, "--description-file", 新文件])
            新_wiki = preview2["preview"]["items"][0]["put_payload"]["description"]
            self.assertIn("描述：", preview2["preview_text"], "预览必须列出描述改动")
            self.assertNotIn("**", 新_wiki, "Markdown 加粗必须被转换成 wiki 标记，不能原样写进 Jira")
            self._apply_ok(preview2["plan_id"])
            self.assertEqual(新_wiki, self._get_issue(key).get("description"),
                             "Jira 上的描述应当是转换后的 wiki 正文")

            # 第三步：从执行记录里回捞完整旧标题与旧描述原文（不许被截断）
            records = self._read_audit_records(key)
            self.assertTrue(records, "执行记录里应当能查到这条单的审计行")
            dumped = json.dumps(records, ensure_ascii=False)
            self.assertIn(原文_wiki, dumped, "审计里必须留有完整的旧描述原文，不得截断")
            self.assertIn(old_summary, dumped, "审计里必须留有完整的旧标题，据此可手工恢复")
        finally:
            if old_summary:
                code, p = self._preview(["--key", key, "--set", "summary=%s" % old_summary])
                if code == 0:
                    self._apply(p["plan_id"])
                else:
                    RESTORE_LOG.append("%s 标题未能恢复（%s）" % (key, p.get("error")))
            if old_description:
                恢复文件 = os.path.join(tmpdir, "restore_desc.txt")
                with open(恢复文件, "w", encoding="utf-8") as f:
                    f.write(old_description)
                code, p = self._preview(["--key", key, "--description-file", 恢复文件,
                                         "--description-format", "wiki"])
                if code == 0:
                    self._apply(p["plan_id"])
                else:
                    RESTORE_LOG.append("%s 描述未能恢复（%s）" % (key, p.get("error")))
            else:
                RESTORE_LOG.append("%s 描述原本为空，工具不支持清空描述，遗留为测试正文；"
                                   "如需清空请在 Jira 网页操作" % key)

    # ------------------------------------------------------------ 场景 13

    def test_场景13_已关闭单改普通字段无需开关(self):
        """场景 13 路径一：已关闭单只改普通字段，不需要任何开关，正常预览确认即可。"""
        key = self._target_key(6, "已关闭靶单（statusCategory.key == done）")
        name, category = self._status_of(key)
        if category != "done":
            self.skipTest("场景 13 前置不满足：靶单 %s 当前状态「%s」的 statusCategory.key 是 %s，"
                          "不是完成类（done），请换一条已关闭的靶单" % (key, name, category))
        old_duedate = self._get_issue(key).get("duedate")
        expected = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            preview = self._preview_ok(["--key", key, "--set", "duedate=明天"])
            self.assertNotIn("你已显式授权", preview["preview_text"],
                             "只改普通字段时不应出现已关闭授权提示")
            report = self._apply_ok(preview["plan_id"])
            self.assertEqual(1, report["counts"]["success"],
                             "已关闭单只改普通字段应当成功：%s" % report.get("result_text"))
            self.assertEqual(expected, self._get_issue(key).get("duedate"),
                             "已关闭单的截止日期应当已改成功")
            self.assertEqual(name, self._status_of(key)[0], "只改普通字段时状态不得变化")
        finally:
            self._restore_duedate(key, old_duedate)

    def test_场景13_已关闭单推状态需显式授权(self):
        """场景 13 路径二：已关闭单推状态，未显式授权时整份预览被拒且不落盘，授权后才放行。"""
        key = self._target_key(6, "已关闭靶单（statusCategory.key == done）")
        name, category = self._status_of(key)
        if category != "done":
            self.skipTest("场景 13 前置不满足：靶单 %s 当前状态「%s」的 statusCategory.key 是 %s，"
                          "不是完成类（done），请换一条已关闭的靶单" % (key, name, category))

        # 未授权：整份预览被拒，state/plans 下不产生文件
        before = self._plan_files()
        code, out = self._preview(["--key", key, "--status", REOPEN_STATUS])
        self.assertEqual(1, code, "未授权推已关闭单应当退出码 1，实际返回=%s" % out)
        self.assertEqual("PREVIEW_HAS_BLOCKERS", out.get("error_code"),
                         "未授权推已关闭单应当整份预览被拒")
        self.assertEqual(before, self._plan_files(), "被拒的预览不得在 state/plans 下落文件")

        # 授权后：放行（工作流没有直达一跳时按设计稿 skip）
        code, preview = self._preview(["--key", key, "--status", REOPEN_STATUS,
                                       "--allow-closed-transition"])
        if code == 1 and preview.get("error_code") == "PREVIEW_HAS_BLOCKERS":
            self.skipTest("场景 13 授权分支前置不满足：靶单当前状态「%s」没有直达「%s」的流转，"
                          "完成类单只判直达一跳" % (name, REOPEN_STATUS))
        self.assertEqual(0, code, "显式授权后预览应当放行，实际返回=%s" % preview)
        try:
            self.assertIn("你已显式授权", preview["preview_text"],
                          "带 --allow-closed-transition 时预览必须提示已显式授权且多半推不回来")
            report = self._apply_ok(preview["plan_id"])
            self.assertEqual(1, report["counts"]["success"],
                             "显式授权后应当执行成功：%s" % report.get("result_text"))
            self.assertEqual(REOPEN_STATUS, self._status_of(key)[0],
                             "执行后靶单应当被推回「%s」" % REOPEN_STATUS)
        finally:
            self._restore_status(key, name)

    # ------------------------------------------------------------ 审计读取

    def _read_audit_records(self, key, tail=200):
        """读 state/audit.log 末尾若干行，挑出这条单的 update 审计记录（按时间顺序）。"""
        if not os.path.isfile(AUDIT_LOG):
            return []
        with open(AUDIT_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()[-tail:]
        records = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("key") == key and record.get("action") == "update":
                records.append(record)
        return records


# ====================================================================
# 人工场景（无法自动化，需人介入，按下面步骤手工跑并登记进
# project-docs/iterations/jira技能化/2026-08-09-验收.md 第五节）
# ====================================================================
#
# 【人工场景 5】预览之后有人抢先改了同一个字段（异常，防覆盖）
#   为什么不能自动化：需要在「预览已生成、尚未确认」这个时间窗内，由**另一个人**在 Jira
#   网页上改同一个字段；用本工具自己去改等于自己跟自己抢，构造不出真实的第三方改动语义。
#   操作步骤：
#     1. 取两条靶单（走批量拿到 900 秒 TTL，避免切到网页改完回来预览已过期），
#        先记下两条单当前的截止日期。
#     2. 跑：
#          python3 scripts/jira_cli.py update --key K1 --key K2 \
#              --set duedate=明天 --complete-set --preview
#        记下 plan_id，先别 apply。
#     3. 切到 Jira 网页，把 K1 的截止日期手工改成另一个日期（比如后天），保存。
#     4. 回到命令行跑：python3 scripts/jira_cli.py apply --plan-id <plan_id>
#   预期结果（逐条核对后登记）：
#     - 报告里 K1 记为 skipped，原因写「他人已改动：截止日期 由 A 变成 B」；
#     - Jira 网页上 K1 的那次手工改动被完整保留，没有被工具覆盖；
#     - K2 正常成功；整次调用退出码 0；K1 出现在 resume_keys（可补做的单号）里。
#   善后：把 K1、K2 的截止日期改回步骤 1 记下的原值。
#
# 【人工场景 14】批量执行中途被 Ctrl-C 打断，审计能还原做了哪几条（异常，留痕有效性）
#   为什么不能自动化：需要在执行进行到一半时发送中断信号，命中时机依赖真实网络耗时，
#   自动化里既不稳定、又会在靶单上留下不确定的中间态。
#   操作步骤：
#     1. 取三条靶单，记下各自当前的截止日期与状态。
#     2. 跑一份三条单的批量预览并 apply：
#          python3 scripts/jira_cli.py update --key K1 --key K2 --key K3 \
#              --set duedate=明天 --complete-set --preview
#          python3 scripts/jira_cli.py apply --plan-id <plan_id>
#     3. 中断时机不能靠看 apply 的终端输出 —— stdout 是整批跑完才吐的单个 JSON，
#        执行途中终端一片空白，凭感觉按 Ctrl-C 很可能在第一条 PUT 发出之前就中断，
#        那样就测不出「逐条即时落审计」这个点。正确做法是另开一个终端窗口盯审计：
#          tail -f state/audit.log
#        看到第一条 update 记录出现后，回到 apply 那个窗口立刻按 Ctrl-C。
#   预期结果（逐条核对后登记）：
#     - state/audit.log 里能逐条查到已处理的是哪几条、各自的改前改后值（逐条即时落盘，
#       不是批末统一写）；
#     - 未处理的那几条在 Jira 上完全没有变化；
#     - 该 plan_id 已被一次性消费，再 apply 一次会报 PLAN_REJECTED（不能复用）；
#     - 拿未处理的单号重新走一次 preview + apply 即可续做。
#   善后：把三条单的截止日期改回步骤 1 记下的原值。
