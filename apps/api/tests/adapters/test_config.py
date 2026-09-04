from pathlib import Path

from adi.adapters.config import load_source_mappings
from adi.domain.models import DeliveryStage, RelationType

ROOT = Path(__file__).parents[4]


def test_example_config_builds_source_specific_mappings() -> None:
    jira, kaiten = load_source_mappings(ROOT / "config/sources.example.yaml")

    assert jira.stages["Development"] is DeliveryStage.IN_PROGRESS
    assert jira.relations["depends on"] is RelationType.DEPENDS_ON
    assert kaiten.stages == {}
