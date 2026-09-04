from pathlib import Path

from adi.policies.retrieval import PolicyIndex

ROOT = Path(__file__).parents[4]


def test_retrieves_blocker_sla_with_stable_source_id() -> None:
    index = PolicyIndex.from_directory(ROOT / "policies")

    results = index.search("blocked item exceeded blocker SLA", top_k=2)

    assert results[0].source_id == "blocker-policy.md#critical-blocker-sla"
    assert "2 business days" in results[0].content


def test_returns_empty_for_unrelated_query() -> None:
    index = PolicyIndex.from_directory(ROOT / "policies")

    assert index.search("quantum hardware procurement", top_k=3) == ()


def test_chunks_have_reviewable_metadata() -> None:
    index = PolicyIndex.from_directory(ROOT / "policies")

    chunk = next(item for item in index.chunks if item.source_id.endswith("#wip-limit"))
    assert chunk.document == "kanban-policy.md"
    assert chunk.heading == "WIP limit"
    assert chunk.trust == "trusted_policy"


def test_policy_directives_drive_rules_and_conflicts_are_explicit(tmp_path: Path) -> None:
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    first.write_text(
        "# One\n\n<!-- adi: blocker_sla_days=2 -->\n\n## SLA\nTwo days.\n",
        encoding="utf-8",
    )
    second.write_text(
        "# Two\n\n<!-- adi: blocker_sla_days=3 -->\n\n## SLA\nThree days.\n",
        encoding="utf-8",
    )

    index = PolicyIndex.from_directory(tmp_path)

    assert index.conflicts == ("blocker_sla_days",)
    assert index.rules.blocker_sla_days == 2
