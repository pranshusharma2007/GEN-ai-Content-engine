"""
History persistence — Supabase (Postgres) with a local-JSON fallback.

Table `transformations` (see supabase_schema.sql):
    run_id      text  primary key
    user_id     text
    created_at  timestamptz
    payload     jsonb        -- the full run document

If SUPABASE_URL / SUPABASE_SERVICE_KEY are not set, runs are stored in
`backend/.local_history.json` so History still works with zero setup.
No MongoDB, no hand-rolled SQLite.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Optional

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_KEY = (
    os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    or os.environ.get("SUPABASE_KEY", "").strip()
)
_TABLE = os.environ.get("SUPABASE_TABLE", "transformations")

_LOCAL_PATH = Path(__file__).parent / ".local_history.json"
_lock = threading.Lock()
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        print("[storage] Supabase not configured — using local JSON history file.")
        return None
    try:
        from supabase import create_client

        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("[storage] Supabase client ready.")
        return _client
    except Exception as exc:  # noqa: BLE001
        print(f"[storage] Supabase init failed ({exc}) — falling back to local JSON.")
        return None


# ── Local JSON fallback ──────────────────────────────────────────────────────

def _local_read() -> list[dict]:
    if not _LOCAL_PATH.exists():
        return []
    try:
        return json.loads(_LOCAL_PATH.read_text("utf-8")) or []
    except Exception:  # noqa: BLE001
        return []


def _local_write(rows: list[dict]) -> None:
    tmp = _LOCAL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(_LOCAL_PATH)


# ── Public API (mirrors the old Mongo helpers) ───────────────────────────────

def save_run(document: dict) -> None:
    """Persist one transformation run. `document` must contain run_id / user_id / created_at."""
    client = _get_client()
    row = {
        "run_id": document["run_id"],
        "user_id": document.get("user_id") or "anonymous",
        "created_at": document.get("created_at"),
        "payload": document,
    }
    if client is not None:
        try:
            client.table(_TABLE).upsert(row, on_conflict="run_id").execute()
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[storage] Supabase save failed ({exc}) — writing local fallback.")

    with _lock:
        rows = _local_read()
        rows = [r for r in rows if r.get("run_id") != row["run_id"]]
        rows.append(row)
        _local_write(rows)


def fetch_history(user_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Return recent run summaries (newest first), scoped to `user_id` when given."""
    client = _get_client()
    if client is not None:
        try:
            q = client.table(_TABLE).select("payload")
            if user_id:
                q = q.eq("user_id", user_id)
            res = q.order("created_at", desc=True).limit(limit).execute()
            docs = [r["payload"] for r in (res.data or [])]
            return [_summarise(d) for d in docs]
        except Exception as exc:  # noqa: BLE001
            print(f"[storage] Supabase history fetch failed ({exc}) — using local fallback.")

    rows = _local_read()
    if user_id:
        rows = [r for r in rows if r.get("user_id") == user_id]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return [_summarise(r["payload"]) for r in rows[:limit]]


def fetch_run(run_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    """Return the full run document, or None. Enforces `user_id` ownership when given."""
    client = _get_client()
    if client is not None:
        try:
            q = client.table(_TABLE).select("payload, user_id").eq("run_id", run_id)
            res = q.limit(1).execute()
            if res.data:
                row = res.data[0]
                if user_id and row.get("user_id") not in (user_id, "anonymous"):
                    return None
                return row["payload"]
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"[storage] Supabase run fetch failed ({exc}) — using local fallback.")

    for r in _local_read():
        if r.get("run_id") == run_id:
            if user_id and r.get("user_id") not in (user_id, "anonymous"):
                return None
            return r["payload"]
    return None


def _summarise(doc: dict) -> dict:
    """Trim a full run document down to the fields the history list needs."""
    return {
        "run_id": doc.get("run_id"),
        "source": {
            "type": (doc.get("source") or {}).get("type"),
            "preview": (doc.get("source") or {}).get("preview"),
        },
        "parameters": doc.get("parameters"),
        "created_at": doc.get("created_at"),
        "consistency": {
            "consistency_score": (doc.get("consistency") or {}).get("consistency_score"),
        },
    }


def backend_label() -> str:
    return "supabase" if (SUPABASE_URL and SUPABASE_SERVICE_KEY) else "local-json"
