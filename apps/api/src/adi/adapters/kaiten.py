from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from adi.adapters.base import DeliverySourceError, SourceErrorCode
from adi.domain.models import (
    CapabilityLevel,
    ContextRef,
    DeliveryContext,
    DeliverySnapshot,
    DeliveryStage,
    EvidenceRef,
    RelationType,
    SourceCapabilities,
    SourceType,
    WorkItem,
    WorkRelation,
)


@dataclass(frozen=True)
class KaitenMapping:
    stages: dict[int, DeliveryStage] = field(default_factory=dict)


class KaitenAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        mapping: KaitenMapping,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.mapping = mapping
        self.client = client or httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        self._contexts: dict[str, DeliveryContext] = {}

    async def list_contexts(self) -> tuple[DeliveryContext, ...]:
        spaces = self._json(await self._get("/api/latest/spaces"))
        contexts: list[DeliveryContext] = []
        for space in spaces:
            boards = self._json(await self._get(f"/api/latest/spaces/{space['id']}/boards"))
            for board in boards:
                context = DeliveryContext(
                    source=SourceType.KAITEN,
                    external_id=str(board["id"]),
                    name=f"{space['title']} / {board['title']}",
                    source_url=f"{self.base_url}/space/{space['id']}/boards/{board['id']}",
                    wip_limit=_board_wip_limit(board),
                    capabilities=self.capabilities(
                        ContextRef(source=SourceType.KAITEN, external_id=str(board["id"]))
                    ),
                )
                self._contexts[context.external_id] = context
                contexts.append(context)
        return tuple(contexts)

    async def collect(self, context: ContextRef, observed_at: datetime) -> DeliverySnapshot:
        cards = await self._cards(context.external_id)
        items = tuple(normalize_card(card, self.mapping, self.base_url) for card in cards)
        known = {item.item_id for item in items}
        relations: list[WorkRelation] = []
        for card in cards:
            if card.get("blocked") is not True:
                continue
            blockers = self._json(await self._get(f"/api/latest/cards/{card['id']}/blockers"))
            for blocker in blockers:
                target = f"kaiten:{blocker.get('blocker_card_id')}"
                source = f"kaiten:{card['id']}"
                if blocker.get("released") is None and source in known and target in known:
                    relations.append(
                        WorkRelation(
                            source_item_id=source,
                            target_item_id=target,
                            relation_type=RelationType.BLOCKED_BY,
                            evidence_id=f"relation:kaiten:{blocker['id']}",
                            observed_at=_optional_datetime(blocker.get("created")) or observed_at,
                            metadata={"provider": "kaiten"},
                        )
                    )
        delivery_context = self._contexts.get(
            context.external_id,
            DeliveryContext(
                source=SourceType.KAITEN,
                external_id=context.external_id,
                name=f"Kaiten board {context.external_id}",
                source_url=f"{self.base_url}/boards/{context.external_id}",
                capabilities=self.capabilities(context),
            ),
        )
        return DeliverySnapshot(
            context=delivery_context,
            observed_at=observed_at,
            items=items,
            relations=tuple(relations),
            evidence=(
                EvidenceRef(
                    evidence_id=f"snapshot:kaiten:{context.external_id}",
                    kind="snapshot",
                    observed_at=observed_at,
                    attributes={"item_count": len(items)},
                ),
                *tuple(_evidence(item, observed_at) for item in items),
                *tuple(_relation_evidence(relation) for relation in relations),
            ),
            configuration_fingerprint=self.configuration_fingerprint(),
        )

    def capabilities(self, context: ContextRef) -> SourceCapabilities:
        del context
        return SourceCapabilities(
            work_items=CapabilityLevel.SUPPORTED,
            stages=CapabilityLevel.SUPPORTED,
            due_dates=CapabilityLevel.SUPPORTED,
            assignees=CapabilityLevel.SUPPORTED,
            blockers=CapabilityLevel.SUPPORTED,
            dependencies=CapabilityLevel.UNAVAILABLE,
            stage_history=CapabilityLevel.UNAVAILABLE,
            priorities=CapabilityLevel.SUPPORTED,
            labels=CapabilityLevel.SUPPORTED,
            source_urls=CapabilityLevel.SUPPORTED,
        )

    def configuration_fingerprint(self) -> str:
        value = repr(sorted((key, stage.value) for key, stage in self.mapping.stages.items()))
        return "kaiten-" + hashlib.sha256(value.encode()).hexdigest()[:12]

    async def _cards(self, board_id: str) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await self._get(
                "/api/latest/cards",
                params={"board_id": board_id, "limit": 100, "offset": offset},
            )
            page = self._json(page)
            values = page if isinstance(page, list) else page.get("cards", [])
            cards.extend(values)
            if len(values) < 100:
                return cards
            offset += len(values)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        try:
            response = await self.client.get(self.base_url + path, params=params)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            code = {
                401: SourceErrorCode.AUTHENTICATION_FAILED,
                403: SourceErrorCode.PERMISSION_DENIED,
                429: SourceErrorCode.RATE_LIMITED,
            }.get(status, SourceErrorCode.PROVIDER_ERROR)
            raise DeliverySourceError(
                code=code,
                message=f"Kaiten request failed with HTTP {status}",
                occurred_at=datetime.now(UTC),
            ) from error
        except httpx.RequestError as error:
            raise DeliverySourceError(
                code=SourceErrorCode.PROVIDER_ERROR,
                message="Kaiten request could not reach the provider",
                occurred_at=datetime.now(UTC),
            ) from error

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as error:
            raise DeliverySourceError(
                code=SourceErrorCode.INVALID_RESPONSE,
                message="Kaiten returned malformed JSON",
                occurred_at=datetime.now(UTC),
            ) from error


def normalize_card(card: dict[str, Any], mapping: KaitenMapping, base_url: str) -> WorkItem:
    owner = card.get("owner") or card.get("assignee")
    assignee = owner.get("full_name") if isinstance(owner, dict) else owner
    tags = tuple(tag.get("name", "") for tag in card.get("tags", []) if tag.get("name"))
    created = _datetime(card.get("created"))
    updated = _datetime(card.get("updated"))
    return WorkItem(
        source=SourceType.KAITEN,
        external_id=str(card["id"]),
        title=card["title"],
        stage=mapping.stages.get(int(card["column_id"]), DeliveryStage.UNKNOWN),
        assignee=assignee,
        priority=_name(card.get("priority")),
        created_at=created,
        updated_at=updated,
        due_at=_optional_datetime(card.get("due_date")),
        entered_stage_at=None,
        completed_at=_optional_datetime(card.get("completed")),
        blocked_since=_optional_datetime(card.get("blocked_since")),
        blocker_eta=_optional_datetime(card.get("blocker_eta")),
        labels=tags,
        source_url=f"{base_url.rstrip('/')}/card/{card['id']}",
        metadata={"column_id": card["column_id"]},
    )


def _board_wip_limit(board: dict[str, Any]) -> int | None:
    limits = [column.get("wip_limit") for column in board.get("columns", [])]
    values = [value for value in limits if isinstance(value, int) and value > 0]
    return sum(values) if values else None


def _name(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("name")
    return str(value) if value is not None else None


def _datetime(value: Any) -> datetime:
    return _optional_datetime(value) or datetime(1970, 1, 1, tzinfo=UTC)


def _optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _evidence(item: WorkItem, observed_at: datetime) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"item:kaiten:{item.external_id}",
        kind="work_item",
        item_id=item.item_id,
        source_url=item.source_url,
        observed_at=observed_at,
        attributes={"stage": item.stage.value, "assignee": item.assignee},
    )


def _relation_evidence(relation: WorkRelation) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=relation.evidence_id,
        kind="relation",
        item_id=relation.source_item_id,
        observed_at=relation.observed_at,
        attributes={
            "target_item_id": relation.target_item_id,
            "relation_type": relation.relation_type.value,
        },
    )
