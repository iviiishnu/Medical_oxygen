"""
ws_manager.py
=============
WebSocket connection manager with role-based routing.
Each connection is tagged with (ws, user_id, role, ward_id).
broadcast() filters recipients by role + ward.
"""

import json
from typing import Optional
from fastapi import WebSocket


class Connection:
    def __init__(self, ws: WebSocket, user_id: int, role: str, ward_id: Optional[int]):
        self.ws = ws
        self.user_id = user_id
        self.role = role          # "DOCTOR" | "NURSE"
        self.ward_id = ward_id    # None for DOCTOR, int for NURSE


class ConnectionManager:
    def __init__(self):
        self._active: list[Connection] = []

    async def connect(
        self, ws: WebSocket, user_id: int, role: str, ward_id: Optional[int]
    ) -> None:
        await ws.accept()
        await self.connect_accepted(ws, user_id, role, ward_id)

    async def connect_accepted(
        self, ws: WebSocket, user_id: int, role: str, ward_id: Optional[int]
    ) -> None:
        """Register an already-accepted WebSocket connection."""
        conn = Connection(ws, user_id, role, ward_id)
        self._active.append(conn)
        print(
            f"🔌  WS connected: user_id={user_id} role={role} "
            f"ward_id={ward_id or 'ALL'}  (total: {len(self._active)})"
        )

    def disconnect(self, ws: WebSocket) -> None:
        self._active = [c for c in self._active if c.ws != ws]
        print(f"🔌  WS disconnected (total: {len(self._active)})")

    async def broadcast(self, payload: dict) -> None:
        """
        Send JSON to all connected clients.

        {"type": "reading"} and {"type": "alert"} messages go to every
        connected user; role-based filtering is no longer applied so the
        new single-role portal always receives every event.
        """
        message = json.dumps(payload, default=str)

        dead: list[WebSocket] = []
        for conn in self._active:
            try:
                await conn.ws.send_text(message)
            except Exception:
                dead.append(conn.ws)

        for ws in dead:
            self.disconnect(ws)


# Singleton
manager = ConnectionManager()
