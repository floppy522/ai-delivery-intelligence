from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from adi.domain.models import SourceType
from adi.persistence.models import DeliveryRun
from adi.service import DeliveryService


class AnalyzeRequest(BaseModel):
    source: SourceType
    context_id: str


def create_app(
    *, service: DeliveryService, initializer: Callable[[], Awaitable[None]] | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        if initializer:
            await initializer()
        yield

    app = FastAPI(title="AI Delivery Intelligence", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8080"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/sources")
    async def sources() -> list[dict[str, object]]:
        return [
            {"id": name, "available": name in service.adapters, "label": name.title()}
            for name in ("demo", "kaiten", "jira")
        ]

    @app.get("/api/sources/{source}/contexts")
    async def contexts(source: SourceType) -> list[dict[str, object]]:
        adapter = service.adapters.get(source.value)
        if adapter is None:
            raise HTTPException(status_code=409, detail="Source credentials are not configured")
        return [context.model_dump(mode="json") for context in await adapter.list_contexts()]

    @app.post("/api/analyze", response_model=DeliveryRun)
    async def analyze(request: AnalyzeRequest) -> DeliveryRun:
        if request.source.value not in service.adapters:
            raise HTTPException(status_code=409, detail="Source credentials are not configured")
        return await service.analyze(request.source, request.context_id)

    @app.post("/api/demo/run", response_model=DeliveryRun)
    async def run_demo() -> DeliveryRun:
        return await service.run_demo_story()

    @app.post("/api/demo/reset", response_model=DeliveryRun)
    async def reset_demo() -> DeliveryRun:
        return await service.reset_demo()

    @app.post("/api/demo/advance", response_model=DeliveryRun)
    async def advance_demo() -> DeliveryRun:
        return await service.advance_demo()

    @app.get("/api/runs", response_model=list[DeliveryRun])
    async def runs(
        source: str = Query(...), context_id: str = Query(...)
    ) -> tuple[DeliveryRun, ...]:
        return await service.repository.list_runs(source, context_id)

    @app.get("/api/runs/{run_id}", response_model=DeliveryRun)
    async def run(run_id: str) -> DeliveryRun:
        found = await service.repository.get_run(run_id)
        if found is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return found

    @app.get("/api/policies/{source_id:path}")
    async def policy(source_id: str) -> dict[str, str]:
        chunk = service.policies.get(source_id)
        if chunk is None:
            raise HTTPException(status_code=404, detail="Policy source not found")
        return {"source_id": chunk.source_id, "heading": chunk.heading, "content": chunk.content}

    return app
