from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from adi.domain.models import DeliverySnapshot
from adi.persistence.models import DeliveryRun


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "delivery_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    context_id: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class DatabaseRunRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(database_url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def save(self, run: DeliveryRun) -> None:
        async with self.sessions() as session:
            session.add(
                RunRow(
                    run_id=run.run_id,
                    source=run.source,
                    context_id=run.context_id,
                    created_at=run.created_at,
                    payload=run.model_dump(mode="json"),
                )
            )
            await session.commit()

    async def previous_snapshot(self, source: str, context_id: str) -> DeliverySnapshot | None:
        run = await self._latest(source, context_id)
        return run.snapshot if run else None

    async def list_runs(self, source: str, context_id: str) -> tuple[DeliveryRun, ...]:
        async with self.sessions() as session:
            statement = (
                select(RunRow)
                .where(RunRow.source == source, RunRow.context_id == context_id)
                .order_by(RunRow.created_at.desc())
            )
            rows = (await session.scalars(statement)).all()
        return tuple(DeliveryRun.model_validate(row.payload) for row in rows)

    async def get_run(self, run_id: str) -> DeliveryRun | None:
        async with self.sessions() as session:
            row = await session.get(RunRow, run_id)
        return DeliveryRun.model_validate(row.payload) if row else None

    async def _latest(self, source: str, context_id: str) -> DeliveryRun | None:
        async with self.sessions() as session:
            statement = (
                select(RunRow)
                .where(RunRow.source == source, RunRow.context_id == context_id)
                .order_by(RunRow.created_at.desc())
                .limit(1)
            )
            row = await session.scalar(statement)
        return DeliveryRun.model_validate(row.payload) if row else None
