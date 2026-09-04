from datetime import UTC, datetime

from adi.adapters.jira import JiraMapping, normalize_issue
from adi.adapters.kaiten import KaitenMapping, normalize_card
from adi.domain.models import DeliveryStage, RelationType, SourceType, WorkItem

NOW = datetime(2026, 9, 7, 9, tzinfo=UTC)


def test_equivalent_tracker_shapes_produce_equivalent_delivery_facts() -> None:
    kaiten = normalize_card(
        {
            "id": 17,
            "title": "Restore tenant access",
            "column_id": 3,
            "owner": None,
            "created": "2026-08-20T09:00:00Z",
            "updated": "2026-09-04T09:00:00Z",
            "due_date": "2026-09-08T17:00:00Z",
            "blocked_since": "2026-09-02T09:00:00Z",
            "priority": "critical",
            "tags": [{"name": "identity"}],
        },
        KaitenMapping(stages={3: DeliveryStage.IN_PROGRESS}),
        "https://northstar.kaiten.ru",
    )
    jira = normalize_issue(
        {
            "key": "NS-17",
            "fields": {
                "summary": "Restore tenant access",
                "status": {"name": "Development"},
                "assignee": None,
                "created": "2026-08-20T09:00:00Z",
                "updated": "2026-09-04T09:00:00Z",
                "duedate": "2026-09-08T17:00:00Z",
                "priority": {"name": "critical"},
                "labels": ["identity"],
                "customfield_blocked_since": "2026-09-02T09:00:00Z",
            },
        },
        JiraMapping(
            stages={"Development": DeliveryStage.IN_PROGRESS},
            blocked_since_field="customfield_blocked_since",
        ),
        "https://northstar.atlassian.net",
    )

    assert _facts(kaiten) == _facts(jira)


def test_jira_link_mapping_is_configurable() -> None:
    mapping = JiraMapping(
        stages={"Done": DeliveryStage.DONE},
        relations={"depends on": RelationType.DEPENDS_ON},
    )
    issue = {
        "key": "NS-19",
        "fields": {
            "summary": "Connect billing events",
            "status": {"name": "Done"},
            "assignee": {"displayName": "Liam"},
            "created": "2026-08-20T09:00:00Z",
            "updated": "2026-09-04T09:00:00Z",
            "issuelinks": [],
        },
    }

    normalized = normalize_issue(issue, mapping, "https://northstar.atlassian.net")
    assert normalized.stage is DeliveryStage.DONE


def _facts(work_item: WorkItem) -> tuple[object, ...]:
    return (
        work_item.title,
        work_item.stage,
        work_item.assignee,
        work_item.priority,
        work_item.due_at,
        work_item.blocked_since,
        work_item.labels,
    )


def test_sources_remain_distinct_identity_namespaces() -> None:
    assert SourceType.KAITEN.value != SourceType.JIRA.value
