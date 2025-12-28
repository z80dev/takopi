from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _now_unix() -> int:
    return int(time.time())


@dataclass(frozen=True)
class Route:
    route_type: str  # "exec"
    route_id: str    # session_id
    meta: Dict[str, Any]


class RouteStore:
    """
    Stores mapping: (chat_id, bot_message_id) -> route
    so Telegram replies can be routed.
    """

    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS routes (
              chat_id INTEGER NOT NULL,
              bot_message_id INTEGER NOT NULL,
              route_type TEXT NOT NULL,
              route_id TEXT NOT NULL,
              meta_json TEXT,
              created_at INTEGER NOT NULL,
              PRIMARY KEY (chat_id, bot_message_id)
            );
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_routes_route_id ON routes(route_id);"
        )
        self._conn.commit()

    def link(
        self,
        chat_id: int,
        bot_message_id: int,
        route_type: str,
        route_id: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO routes(chat_id, bot_message_id, route_type, route_id, meta_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (chat_id, bot_message_id, route_type, route_id, meta_json, _now_unix()),
        )
        self._conn.commit()

    def resolve(self, chat_id: int, bot_message_id: int) -> Optional[Route]:
        cur = self._conn.execute(
            """
            SELECT route_type, route_id, meta_json
            FROM routes
            WHERE chat_id = ? AND bot_message_id = ?
            """,
            (chat_id, bot_message_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        route_type, route_id, meta_json = row
        try:
            meta = json.loads(meta_json) if meta_json else {}
        except json.JSONDecodeError:
            meta = {}
        return Route(route_type=route_type, route_id=route_id, meta=meta)
