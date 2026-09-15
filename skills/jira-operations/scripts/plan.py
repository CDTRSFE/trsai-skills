# -*- coding: utf-8 -*-
"""两阶段 plan 门禁 + 审计日志（对齐设计 §7）。

状态机：
  preview → [pending] → apply 成功 → [consumed]（os.rename 至 <id>.consumed.json）
     ├── 超过 TTL（默认 5 分钟） → PLAN_REJECTED（已过期）
     └── 已 consumed 再 apply  → PLAN_REJECTED（已使用）

归属判定用 os.rename：谁 rename 成功谁执行，失败方直接拒绝，
比读-改-写更可靠（模型完全可能并行发两条 Bash）。

定位说明：这道门是防手滑的变更预览门，不是安全边界（设计 §7.2）。
"""

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

import _atomic

DEFAULT_TTL_SECONDS = 300
PLAN_ID_PATTERN = re.compile(r"^plan_[0-9a-f]{8}$")


class PlanRejected(Exception):
    """plan 校验不通过。reason 为人类可读中文原因。"""


def _now():
    return datetime.now(timezone.utc).astimezone()


def _plan_path(plans_dir, plan_id):
    if not PLAN_ID_PATTERN.match(plan_id or ""):
        raise PlanRejected("plan_id 格式非法: %s" % plan_id)
    return os.path.join(plans_dir, plan_id + ".json")


def create_plan(plans_dir, payload, ttl_seconds=DEFAULT_TTL_SECONDS):
    """生成 plan 并原子落盘，返回 plan 字典。"""
    now = _now()
    plan = {
        "plan_id": "plan_" + secrets.token_hex(4),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
    }
    plan.update(payload)
    path = _plan_path(plans_dir, plan["plan_id"])
    _atomic.atomic_write(path, json.dumps(plan, ensure_ascii=False, indent=2))
    return plan


def consume_plan(plans_dir, plan_id):
    """校验 plan 存在 / 未过期 / 未使用，并用 rename 抢占执行权。

    成功返回 plan 字典；任一校验不过抛 PlanRejected。
    """
    path = _plan_path(plans_dir, plan_id)
    if not os.path.isfile(path):
        if os.path.isfile(path[:-5] + ".consumed.json"):
            raise PlanRejected("plan 已被使用过（一次性消费）")
        raise PlanRejected("plan 不存在: %s" % plan_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except (ValueError, OSError) as e:
        raise PlanRejected("plan 文件损坏: %s" % e)
    expires_at = plan.get("expires_at", "")
    try:
        expired = _now() > datetime.fromisoformat(expires_at)
    except ValueError:
        expired = True
    if expired:
        raise PlanRejected("plan 已过期（有效期 %s）" % expires_at)
    consumed_path = path[:-5] + ".consumed.json"
    try:
        os.rename(path, consumed_path)
    except OSError:
        raise PlanRejected("plan 已被使用过（一次性消费）")
    return plan


def audit(audit_path, record):
    """追加一条审计日志（成功与被拒都记），单行 JSON。"""
    entry = {"ts": _now().isoformat()}
    entry.update(record)
    _atomic.jsonl_append(audit_path, json.dumps(entry, ensure_ascii=False))
