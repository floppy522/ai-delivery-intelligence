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
class JiraMapping:
    stages: dict[str, DeliveryStage] = field(default_factory=dict)
    relations: dict[str, RelationType] = field(default_factory=dict)
    blocked_since_field: str | None = None
    entered_stage_field: str | None = None
    blocker_eta_field: str | None = None


class JiraAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        email: str,
        token: str,
        mapping: JiraMapping,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.mapping = mapping
        self.client = client or httpx.AsyncClient(
            base_url=self.base_url,
            auth=httpx.BasicAuth(email, token),
            headers={"Accept": "application/json"},
            timeout=20,
        )
        self._contexts: dict[str, DeliveryContext] = {}

    async def list_contexts(self) -> tuple[DeliveryContext, ...]:
        response = await self._get("/rest/agile/1.0/board", params={"maxResults": 100})
        payload = self._json(response)
        contexts = tuple(
            DeliveryContext(
                source=SourceType.JIRA,
                external_id=str(board["id"]),
                name=board["name"],
                source_url=f"{self.base_url}/secure/RapidBoard.jspa?rapidView={board['id']}",
                capabilities=self.capabilities(
                    ContextRef(source=SourceType.JIRA, external_id=str(board["id"]))
                ),
            )
            for board in payload.get("values", [])
        )
        self._contexts.update({context.external_id: context for context in contexts})
        return contexts

    async def collect(self, context: ContextRef, observed_at: datetime) -> DeliverySnapshot:
        issues = await self._issues(context.external_id)
        items = tuple(normalize_issue(issue, self.mapping, self.base_url) for issue in issues)
        known = {item.item_id for item in items}
        relations = tuple(
            relation
            for issue in issues
            for relation in _relations(issue, self.mapping, observed_at)
            if relation.source_item_id in known and relation.target_item_id in known
        )
        delivery_context = self._contexts.get(
            context.external_id,
            DeliveryContext(
                source=SourceType.JIRA,
                external_id=context.external_id,
                name=f"Jira board {context.external_id}",
                source_url=f"{self.base_url}/secure/RapidBoard.jspa?rapidView={context.external_id}",
                capabilities=self.capabilities(context),
            ),
        )
        return DeliverySnapshot(
            context=delivery_context,
            observed_at=observed_at,
            items=items,
            relations=relations,
            evidence=(
                EvidenceRef(
                    evidence_id=f"snapshot:jira:{context.external_id}",
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
        custom_history = (
            CapabilityLevel.PARTIAL
            if self.mapping.entered_stage_field
            else CapabilityLevel.UNAVAILABLE
        )
        return SourceCapabilities(
            work_items=CapabilityLevel.SUPPORTED,
            stages=CapabilityLevel.SUPPORTED,
            due_dates=CapabilityLevel.SUPPORTED,
            assignees=CapabilityLevel.SUPPORTED,
            blockers=CapabilityLevel.PARTIAL,
            dependencies=CapabilityLevel.SUPPORTED,
            stage_history=custom_history,
            priorities=CapabilityLevel.SUPPORTED,
            labels=CapabilityLevel.SUPPORTED,
            source_urls=CapabilityLevel.SUPPORTED,
        )

    def configuration_fingerprint(self) -> str:
        values = (
            sorted((name, stage.value) for name, stage in self.mapping.stages.items()),
            sorted((name, relation.value) for name, relation in self.mapping.relations.items()),
            self.mapping.blocked_since_field,
            self.mapping.entered_stage_field,
            self.mapping.blocker_eta_field,
        )
        return "jira-" + hashlib.sha256(repr(values).encode()).hexdigest()[:12]

    async def _issues(self, board_id: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            params: dict[str, Any] = {"maxResults": 100}
            if token:
                params["nextPageToken"] = token
            response = await self._get(f"/rest/software/1.0/board/{board_id}/issue", params=params)
            payload = self._json(response)
            issues.extend(payload.get("issues", []))
            token = payload.get("nextPageToken")
            if payload.get("isLast", token is None):
                return issues

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
                message=f"Jira request failed with HTTP {status}",
                occurred_at=datetime.now(UTC),
            ) from error
        except httpx.RequestError as error:
            raise DeliverySourceError(
                code=SourceErrorCode.PROVIDER_ERROR,
                message="Jira request could not reach the provider",
                occurred_at=datetime.now(UTC),
            ) from error

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as error:
            raise DeliverySourceError(
                code=SourceErrorCode.INVALID_RESPONSE,
                message="Jira returned malformed JSON",
                occurred_at=datetime.now(UTC),
            ) from error


def normalize_issue(issue: dict[str, Any], mapping: JiraMapping, base_url: str) -> WorkItem:
    fields = issue["fields"]
    assignee = fields.get("assignee")
    labels = tuple(fields.get("labels") or ())
    components = tuple(component["name"] for component in fields.get("components") or ())
    return WorkItem(
        source=SourceType.JIRA,
        external_id=issue["key"],
        title=fields["summary"],
        stage=mapping.stages.get(fields["status"]["name"], DeliveryStage.UNKNOWN),
        assignee=assignee.get("displayName") if assignee else None,
        priority=(fields.get("priority") or {}).get("name"),
        created_at=_datetime(fields.get("created")),
        updated_at=_datetime(fields.get("updated")),
        due_at=_optional_datetime(fields.get("duedate")),
        entered_stage_at=_custom_datetime(fields, mapping.entered_stage_field),
        completed_at=_optional_datetime(fields.get("resolutiondate")),
        blocked_since=_custom_datetime(fields, mapping.blocked_since_field),
        blocker_eta=_custom_datetime(fields, mapping.blocker_eta_field),
        labels=labels + components,
        source_url=f"{base_url.rstrip('/')}/browse/{issue['key']}",
        metadata={"status_name": fields["status"]["name"]},
    )


def _relations(
    issue: dict[str, Any], mapping: JiraMapping, observed_at: datetime
) -> tuple[WorkRelation, ...]:
    relations: list[WorkRelation] = []
    source = f"jira:{issue['key']}"
    for index, link in enumerate(issue["fields"].get("issuelinks") or ()):
        direction = "outward" if "outwardIssue" in link else "inward"
        label = link["type"].get(direction)
        target_issue = link.get(f"{direction}Issue")
        relation_type = mapping.relations.get(label)
        if relation_type and target_issue:
            relations.append(
                WorkRelation(
                    source_item_id=source,
                    target_item_id=f"jira:{target_issue['key']}",
                    relation_type=relation_type,
                    evidence_id=f"relation:jira:{issue['key']}:{index}",
                    observed_at=observed_at,
                    metadata={"provider_label": label},
                )
            )
    return tuple(relations)


def _custom_datetime(fields: dict[str, Any], field_name: str | None) -> datetime | None:
    return _optional_datetime(fields.get(field_name)) if field_name else None


def _datetime(value: Any) -> datetime:
    return _optional_datetime(value) or datetime(1970, 1, 1, tzinfo=UTC)


def _optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value)
    if len(raw) == 10:
        raw += "T00:00:00+00:00"
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _evidence(item: WorkItem, observed_at: datetime) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"item:jira:{item.external_id}",
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
