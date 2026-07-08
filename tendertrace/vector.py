from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


class VectorUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingBuildResult:
    status: str
    model: str
    scanned: int
    embedded: int
    skipped: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_notice_embeddings(
    settings: Settings,
    *,
    limit: int | None = None,
) -> EmbeddingBuildResult:
    init_db(settings)
    if not settings.vector_enabled:
        return EmbeddingBuildResult(
            status="disabled",
            model=settings.vector_model,
            scanned=0,
            embedded=0,
            skipped=0,
        )
    try:
        embedder = _load_embedder(settings.vector_model)
    except VectorUnavailable as exc:
        return EmbeddingBuildResult(
            status="unavailable",
            model=settings.vector_model,
            scanned=0,
            embedded=0,
            skipped=0,
            error=str(exc),
        )
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT n.id, n.title, n.content_text, n.core_content, e.text_sha256, e.model
            FROM notices n
            LEFT JOIN notice_embeddings e ON e.notice_id = n.id
            ORDER BY n.created_at DESC
            """
        ).fetchall()
        pending = []
        skipped = 0
        for row in rows:
            text = notice_embedding_text(dict(row))
            digest = _sha256(text)
            if row["text_sha256"] == digest and row["model"] == settings.vector_model:
                skipped += 1
                continue
            pending.append((row["id"], text, digest))
            if limit is not None and len(pending) >= limit:
                break
        vectors = _embed_texts(embedder, [item[1] for item in pending])
        for (notice_id, _text, digest), vector in zip(pending, vectors, strict=True):
            conn.execute(
                """
                INSERT INTO notice_embeddings(
                    notice_id, model, dim, text_sha256, vector_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(notice_id) DO UPDATE SET
                    model = excluded.model,
                    dim = excluded.dim,
                    text_sha256 = excluded.text_sha256,
                    vector_json = excluded.vector_json,
                    updated_at = datetime('now')
                """,
                (
                    notice_id,
                    settings.vector_model,
                    len(vector),
                    digest,
                    json.dumps(vector, separators=(",", ":")),
                ),
            )
    return EmbeddingBuildResult(
        status="finished",
        model=settings.vector_model,
        scanned=len(rows),
        embedded=len(pending),
        skipped=skipped,
    )


def embed_query(settings: Settings, text: str) -> list[float]:
    if not settings.vector_enabled:
        return []
    embedder = _load_embedder(settings.vector_model)
    vectors = _embed_texts(embedder, [text])
    return vectors[0] if vectors else []


def notice_embedding_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "").strip()
        for key in ("title", "content_text", "core_content")
        if str(row.get(key) or "").strip()
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def vector_coverage(settings: Settings) -> dict[str, int | str | bool]:
    if not settings.db_path.exists():
        return {
            "enabled": settings.vector_enabled,
            "model": settings.vector_model,
            "embedded_notices": 0,
            "indexed_notices": 0,
        }
    with connection(settings) as conn:
        notice_count = conn.execute("SELECT COUNT(*) AS count FROM notices").fetchone()["count"]
        embedded_count = conn.execute(
            "SELECT COUNT(*) AS count FROM notice_embeddings WHERE model = ?",
            (settings.vector_model,),
        ).fetchone()["count"]
    return {
        "enabled": settings.vector_enabled,
        "model": settings.vector_model,
        "embedded_notices": int(embedded_count or 0),
        "indexed_notices": int(notice_count or 0),
    }


def _load_embedder(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise VectorUnavailable(
            "sentence-transformers is not installed; run: python -m pip install -e .[vector]"
        ) from exc
    return SentenceTransformer(model_name)


def _embed_texts(embedder, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = embedder.encode(texts, normalize_embeddings=True)
    return [[float(value) for value in vector] for vector in vectors]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
