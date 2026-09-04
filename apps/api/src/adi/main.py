from fastapi import FastAPI

from adi.adapters.base import DeliverySourceAdapter
from adi.adapters.config import load_source_mappings
from adi.adapters.demo import DemoAdapter, DemoPhaseStore
from adi.adapters.jira import JiraAdapter
from adi.adapters.kaiten import KaitenAdapter
from adi.agent.openai_agent import OpenAIDeliveryAgent
from adi.api import create_app
from adi.persistence.database import DatabaseRunRepository
from adi.policies.retrieval import PolicyIndex
from adi.service import DeliveryService
from adi.settings import Settings


def build_app() -> FastAPI:
    settings = Settings()
    config_path = settings.source_config_path or settings.root / "config/sources.example.yaml"
    jira_mapping, kaiten_mapping = load_source_mappings(config_path)
    phase = DemoPhaseStore()
    adapters: dict[str, DeliverySourceAdapter] = {
        "demo": DemoAdapter(settings.root / "demo", phase)
    }
    if settings.jira_base_url and settings.jira_email and settings.jira_token:
        adapters["jira"] = JiraAdapter(
            base_url=settings.jira_base_url,
            email=settings.jira_email,
            token=settings.jira_token,
            mapping=jira_mapping,
        )
    if settings.kaiten_base_url and settings.kaiten_token:
        adapters["kaiten"] = KaitenAdapter(
            base_url=settings.kaiten_base_url,
            token=settings.kaiten_token,
            mapping=kaiten_mapping,
        )
    repository = DatabaseRunRepository(settings.database_url)
    service = DeliveryService(
        adapters=adapters,
        policies=PolicyIndex.from_directory(settings.root / "policies"),
        repository=repository,
        demo_phase=phase,
        agent=(
            OpenAIDeliveryAgent(settings.openai_api_key, settings.openai_model)
            if settings.openai_api_key
            else None
        ),
    )
    return create_app(service=service, initializer=repository.initialize)


app = build_app()
