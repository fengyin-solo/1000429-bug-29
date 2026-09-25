"""泵站运行业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "pump"
REQUIRED_FIELDS = ["泵站编号", "泵组台数", "运行泵号"]
STATUS_ORDER = ["待启泵", "运行中", "待检修", "已停泵"]
ACTION_RULES = {"启泵运行": "运行中", "安排检修": "待检修", "停泵": "已停泵"}
STOPPED_STATUS = "已停泵"
STOP_ACTION = "停泵"

# 停泵后这些运行过程量不再有意义，需要一并清空，避免残留上一次运行的值。
RUNTIME_FIELDS = ["运行泵号", "出水流量", "液位高度", "运行电流"]


class PumpService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("泵站编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"泵站 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于泵站运行可执行范围"

        current = entry.get("status")
        target = ACTION_RULES[action]

        # 已停泵是终态：除了重复停幂等返回，其余动作一律拒绝，泵站不能被重新启泵。
        if current == STOPPED_STATUS:
            if action == STOP_ACTION:
                return entry, "泵站已处于停泵状态，无需重复停泵"
            return None, "泵站已停泵，不能再执行该动作；如需投运请重新登记泵站"

        if target == current:
            return entry, f"泵站已是「{current}」状态，无需重复操作"

        entry["status"] = target
        entry["pending"] = target != STOPPED_STATUS
        # 停泵计入异常量，使概览与列表的口径保持一致。
        entry["abnormal"] = target == STOPPED_STATUS
        if action == STOP_ACTION:
            for field in RUNTIME_FIELDS:
                entry[field] = ""
        return entry, f"泵站已{action}"
