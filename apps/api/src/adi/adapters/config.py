from pathlib import Path
from typing import Any

import yaml

from adi.adapters.jira import JiraMapping
from adi.adapters.kaiten import KaitenMapping
from adi.domain.models import DeliveryStage, RelationType


def load_source_mappings(path: Path) -> tuple[JiraMapping, KaitenMapping]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    jira_data = data.get("jira", {})
    jira_stages = {
        provider_name: DeliveryStage(canonical)
        for canonical, provider_names in jira_data.get("stages", {}).items()
        for provider_name in provider_names
    }
    jira_relations = {
        provider_name: RelationType(canonical)
        for provider_name, canonical in jira_data.get("relations", {}).items()
    }
    custom = jira_data.get("custom_fields", {})
    kaiten_data = data.get("kaiten", {})
    kaiten_stages = {
        int(column_id): DeliveryStage(canonical)
        for canonical, column_ids in kaiten_data.get("stages", {}).items()
        for column_id in column_ids
    }
    return (
        JiraMapping(
            stages=jira_stages,
            relations=jira_relations,
            blocked_since_field=custom.get("blocked_since"),
            blocker_eta_field=custom.get("blocker_eta"),
            entered_stage_field=custom.get("entered_stage"),
        ),
        KaitenMapping(stages=kaiten_stages),
    )
