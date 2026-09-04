from datetime import UTC, datetime

import httpx
import pytest

from adi.adapters.base import DeliverySourceError, SourceErrorCode
from adi.adapters.jira import JiraAdapter, JiraMapping
from adi.adapters.kaiten import KaitenAdapter, KaitenMapping
from adi.domain.models import ContextRef, DeliveryStage, RelationType, SourceType

NOW = datetime(2026, 9, 7, 9, tzinfo=UTC)


@pytest.mark.asyncio
async def test_kaiten_reads_board_cards_and_blockers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/spaces":
            return httpx.Response(200, json=[{"id": 1, "title": "Northstar"}])
        if request.url.path == "/api/latest/spaces/1/boards":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 9,
                        "title": "Delivery",
                        "columns": [{"id": 3, "title": "Doing", "type": 2}],
                    }
                ],
            )
        if request.url.path == "/api/latest/cards":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 17,
                        "title": "Restore tenant access",
                        "column_id": 3,
                        "blocked": True,
                        "created": "2026-08-20T09:00:00Z",
                        "updated": "2026-09-04T09:00:00Z",
                    }
                ],
            )
        if request.url.path == "/api/latest/cards/17/blockers":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 44,
                        "blocker_card_id": 29,
                        "created": "2026-09-02T09:00:00Z",
                        "released": None,
                    }
                ],
            )
        raise AssertionError(request.url)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = KaitenAdapter(
        base_url="https://northstar.kaiten.ru",
        token="secret",
        mapping=KaitenMapping(stages={3: DeliveryStage.IN_PROGRESS}),
        client=client,
    )

    contexts = await adapter.list_contexts()
    snapshot = await adapter.collect(
        ContextRef(source=SourceType.KAITEN, external_id="9", parent_external_id="1"), NOW
    )

    assert contexts[0].name == "Northstar / Delivery"
    assert snapshot.items[0].stage is DeliveryStage.IN_PROGRESS
    assert snapshot.relations == ()  # Unknown blocker target is never invented.
    await client.aclose()


@pytest.mark.asyncio
async def test_kaiten_skips_blocker_requests_for_unblocked_cards() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/cards":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 18,
                        "title": "Healthy work",
                        "column_id": 3,
                        "blocked": False,
                        "created": "2026-08-20T09:00:00Z",
                        "updated": "2026-09-04T09:00:00Z",
                    }
                ],
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = KaitenAdapter(
        base_url="https://northstar.kaiten.ru",
        token="secret",
        mapping=KaitenMapping(stages={3: DeliveryStage.IN_PROGRESS}),
        client=client,
    )
    snapshot = await adapter.collect(ContextRef(source=SourceType.KAITEN, external_id="9"), NOW)
    assert snapshot.relations == ()
    await client.aclose()


@pytest.mark.asyncio
async def test_jira_reads_board_issues_and_links() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rest/agile/1.0/board":
            return httpx.Response(
                200,
                json={"values": [{"id": 5, "name": "Northstar", "location": {"projectKey": "NS"}}]},
            )
        if request.url.path == "/rest/software/1.0/board/5/issue":
            return httpx.Response(
                200,
                json={
                    "issues": [
                        {
                            "key": "NS-19",
                            "fields": {
                                "summary": "Connect billing events",
                                "status": {"name": "Analysis"},
                                "assignee": {"displayName": "Liam"},
                                "created": "2026-08-20T09:00:00Z",
                                "updated": "2026-09-04T09:00:00Z",
                                "issuelinks": [
                                    {
                                        "type": {
                                            "outward": "depends on",
                                            "inward": "is depended on by",
                                        },
                                        "outwardIssue": {"key": "NS-29"},
                                    }
                                ],
                            },
                        },
                        {
                            "key": "NS-29",
                            "fields": {
                                "summary": "Upgrade identity gateway",
                                "status": {"name": "Backlog"},
                                "assignee": {"displayName": "Maya"},
                                "created": "2026-08-20T09:00:00Z",
                                "updated": "2026-09-04T09:00:00Z",
                                "issuelinks": [],
                            },
                        },
                    ],
                    "isLast": True,
                },
            )
        raise AssertionError(request.url)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    mapping = JiraMapping(
        stages={"Analysis": DeliveryStage.ANALYSIS, "Backlog": DeliveryStage.BACKLOG},
        relations={"depends on": RelationType.DEPENDS_ON},
    )
    adapter = JiraAdapter(
        base_url="https://northstar.atlassian.net",
        email="manager@example.com",
        token="secret",
        mapping=mapping,
        client=client,
    )

    contexts = await adapter.list_contexts()
    snapshot = await adapter.collect(ContextRef(source=SourceType.JIRA, external_id="5"), NOW)

    assert contexts[0].external_id == "5"
    assert snapshot.relations[0].relation_type is RelationType.DEPENDS_ON
    assert snapshot.relations[0].source_item_id == "jira:NS-19"
    await client.aclose()


@pytest.mark.asyncio
async def test_jira_translates_auth_failure_without_provider_body() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401, request=request, text="Authorization: Bearer secret-token"
            )
        )
    )
    adapter = JiraAdapter(
        base_url="https://northstar.atlassian.net",
        email="manager@example.com",
        token="secret-token",
        mapping=JiraMapping(),
        client=client,
    )
    with pytest.raises(DeliverySourceError) as caught:
        await adapter.list_contexts()
    assert caught.value.code is SourceErrorCode.AUTHENTICATION_FAILED
    assert "secret-token" not in caught.value.message
    await client.aclose()
