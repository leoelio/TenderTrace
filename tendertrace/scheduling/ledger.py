from __future__ import annotations

import sqlite3
from typing import Iterable


def mark_sent(
    conn: sqlite3.Connection,
    *,
    subscription_id: str,
    cluster_key: str,
    run_id: str,
    docx_path: str | None,
) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO sent_history(subscription_id, cluster_key, run_id, docx_path)
        VALUES (?, ?, ?, ?)
        """,
        (subscription_id, cluster_key, run_id, docx_path),
    )
    return cursor.rowcount == 1


def unsent_cluster_keys(
    conn: sqlite3.Connection,
    *,
    subscription_id: str,
    cluster_keys: Iterable[str],
) -> list[str]:
    keys = list(dict.fromkeys(cluster_keys))
    if not keys:
        return []
    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"""
        SELECT cluster_key FROM sent_history
        WHERE subscription_id = ? AND cluster_key IN ({placeholders})
        """,
        (subscription_id, *keys),
    ).fetchall()
    sent = {row["cluster_key"] for row in rows}
    return [key for key in keys if key not in sent]

