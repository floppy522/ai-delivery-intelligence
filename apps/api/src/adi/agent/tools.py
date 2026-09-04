from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from adi.domain.models import DeliverySnapshot, DeliveryStage, RelationType
from adi.engine.diff import ChangeSet
from adi.engine.signals import DeliveryAnalysis
from adi.policies.retrieval import PolicyIndex


class ToolPermissionError(ValueError):
    pass


class DeliveryToolExecutor:
    """Allowlisted projections over immutable run data; no side-effect tools exist."""

    def __init__(
        self,
        snapshot: DeliverySnapshot,
        changes: ChangeSet,
        analysis: DeliveryAnalysis,
        policies: PolicyIndex,
    ) -> None:
        self.snapshot = snapshot
        self.changes = changes
        self.analysis = analysis
        self.policies = policies
        self.retrieved_policy_ids: set[str] = set()
        self._tools: dict[str, Callable[[dict[str, Any]], object]] = {
            "get_delivery_snapshot": self._snapshot,
            "get_delivery_changes": self._changes,
            "get_flow_metrics": self._metrics,
            "get_aging_work": self._aging,
            "get_blockers": self._blockers,
            "get_dependencies": self._dependencies,
            "get_due_items": self._due,
            "search_delivery_policies": self._search,
            "get_work_item_evidence": self._item_evidence,
        }

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolPermissionError(f"Tool is not allowlisted: {name}")
        payload = tool(arguments)
        trust = "trusted_policy" if name == "search_delivery_policies" else "untrusted_tracker_data"
        return json.dumps({"trust": trust, "data": payload}, default=str)

    def _snapshot(self, arguments: dict[str, Any]) -> object:
        del arguments
        return [item.model_dump(mode="json") for item in self.snapshot.items]

    def _changes(self, arguments: dict[str, Any]) -> object:
        del arguments
        return self.changes.model_dump(mode="json")

    def _metrics(self, arguments: dict[str, Any]) -> object:
        del arguments
        return self.analysis.metrics.model_dump(mode="json")

    def _aging(self, arguments: dict[str, Any]) -> object:
        del arguments
        return [
            item.model_dump(mode="json")
            for item in self.snapshot.items
            if item.entered_stage_at
            and item.stage
            in {DeliveryStage.ANALYSIS, DeliveryStage.IN_PROGRESS, DeliveryStage.VERIFY}
            and (self.snapshot.observed_at - item.entered_stage_at).days
            >= (
                self.policies.rules.verify_aging_days
                if item.stage is DeliveryStage.VERIFY
                else self.policies.rules.aging_days
            )
        ]

    def _blockers(self, arguments: dict[str, Any]) -> object:
        del arguments
        return [
            relation.model_dump(mode="json")
            for relation in self.snapshot.relations
            if relation.relation_type in {RelationType.BLOCKS, RelationType.BLOCKED_BY}
        ]

    def _dependencies(self, arguments: dict[str, Any]) -> object:
        del arguments
        return [
            relation.model_dump(mode="json")
            for relation in self.snapshot.relations
            if relation.relation_type in {RelationType.DEPENDS_ON, RelationType.DEPENDED_ON_BY}
        ]

    def _due(self, arguments: dict[str, Any]) -> object:
        del arguments
        return [
            item.model_dump(mode="json") for item in self.snapshot.items if item.due_at is not None
        ]

    def _search(self, arguments: dict[str, Any]) -> object:
        query = str(arguments.get("query", ""))[:500]
        matches = self.policies.search(query, top_k=4)
        self.retrieved_policy_ids.update(match.source_id for match in matches)
        return [match.__dict__ for match in matches]

    def _item_evidence(self, arguments: dict[str, Any]) -> object:
        item_id = str(arguments.get("item_id", ""))
        item = next((item for item in self.snapshot.items if item.item_id == item_id), None)
        return item.model_dump(mode="json") if item else {"error": "unknown_item"}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": parameters,
    }
    for name, description, parameters in (
        (
            "get_delivery_snapshot",
            "Read normalized work items.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        (
            "get_delivery_changes",
            "Read deterministic changes.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        (
            "get_flow_metrics",
            "Read deterministic flow metrics.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        (
            "get_aging_work",
            "Read aging active work.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        (
            "get_blockers",
            "Read normalized blockers.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        (
            "get_dependencies",
            "Read normalized dependencies.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        (
            "get_due_items",
            "Read due-date facts.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        (
            "search_delivery_policies",
            "Search trusted policy sections.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        (
            "get_work_item_evidence",
            "Read one item by canonical item_id.",
            {
                "type": "object",
                "properties": {"item_id": {"type": "string"}},
                "required": ["item_id"],
                "additionalProperties": False,
            },
        ),
    )
]
