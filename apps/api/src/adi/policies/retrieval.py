from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

TOKEN = re.compile(r"[a-z0-9_]+")
DIRECTIVE = re.compile(r"<!--\s*adi:\s*([a-z_]+)=(\d+)\s*-->")
DEFAULT_RULES = {
    "aging_days": 4,
    "verify_aging_days": 3,
    "blocker_sla_days": 2,
    "dependency_threat_days": 5,
}


@dataclass(frozen=True)
class DeliveryPolicyRules:
    aging_days: int = 4
    verify_aging_days: int = 3
    blocker_sla_days: int = 2
    dependency_threat_days: int = 5


@dataclass(frozen=True)
class PolicyChunk:
    source_id: str
    document: str
    heading: str
    content: str
    trust: str = "trusted_policy"


@dataclass(frozen=True)
class PolicyResult(PolicyChunk):
    score: float = 0.0


class PolicyIndex:
    """Small inspectable BM25 index over second-level Markdown sections."""

    def __init__(
        self,
        chunks: tuple[PolicyChunk, ...],
        rules: DeliveryPolicyRules | None = None,
        conflicts: tuple[str, ...] = (),
    ) -> None:
        self.chunks = chunks
        self.rules = rules or DeliveryPolicyRules()
        self.conflicts = conflicts
        self._documents = tuple(_tokens(chunk.heading + " " + chunk.content) for chunk in chunks)
        self._average_length = sum(map(len, self._documents)) / max(len(self._documents), 1)
        self._document_frequency = Counter(
            token for document in self._documents for token in set(document)
        )

    @classmethod
    def from_directory(cls, directory: Path) -> PolicyIndex:
        chunks: list[PolicyChunk] = []
        values: dict[str, set[int]] = {key: set() for key in DEFAULT_RULES}
        for path in sorted(directory.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            for name, raw in DIRECTIVE.findall(content):
                if name in values:
                    values[name].add(int(raw))
            chunks.extend(_chunk_document(path))
        conflicts = tuple(sorted(name for name, found in values.items() if len(found) > 1))
        resolved = {
            name: next(iter(found)) if len(found) == 1 else default
            for name, default in DEFAULT_RULES.items()
            for found in (values[name],)
        }
        return cls(tuple(chunks), DeliveryPolicyRules(**resolved), conflicts)

    def search(self, query: str, top_k: int = 4) -> tuple[PolicyResult, ...]:
        query_tokens = _tokens(query)
        scores = [self._score(query_tokens, index) for index in range(len(self.chunks))]
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        return tuple(
            PolicyResult(**chunk.__dict__, score=score)
            for index, score in ranked[:top_k]
            if score > 0.15
            for chunk in (self.chunks[index],)
        )

    def get(self, source_id: str) -> PolicyChunk | None:
        return next((chunk for chunk in self.chunks if chunk.source_id == source_id), None)

    def _score(self, query: tuple[str, ...], index: int) -> float:
        document = self._documents[index]
        frequencies = Counter(document)
        score = 0.0
        for term in set(query):
            frequency = frequencies[term]
            if not frequency:
                continue
            document_frequency = self._document_frequency[term]
            inverse = math.log(
                1 + (len(self.chunks) - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            normalization = frequency + 1.2 * (
                0.25 + 0.75 * len(document) / max(self._average_length, 1)
            )
            score += inverse * frequency * 2.2 / normalization
        return score


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(TOKEN.findall(value.lower()))


def _chunk_document(path: Path) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    heading: str | None = None
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if heading and lines:
                chunks.append(_chunk(path.name, heading, lines))
            heading = line[3:].strip()
            lines = []
        elif heading and line.strip():
            lines.append(line.strip())
    if heading and lines:
        chunks.append(_chunk(path.name, heading, lines))
    return chunks


def _chunk(document: str, heading: str, lines: list[str]) -> PolicyChunk:
    slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
    return PolicyChunk(
        source_id=f"{document}#{slug}",
        document=document,
        heading=heading,
        content="\n".join(lines),
    )
