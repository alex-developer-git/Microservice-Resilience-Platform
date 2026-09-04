from fastapi import WebSocket


class WebSocketStatusManager:
    def __init__(self) -> None:
        """Create an in-memory set of WebSocket connections."""
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active set."""
        self._connections.discard(websocket)

    async def broadcast(self, payload: dict[str, object]) -> None:
        """Send a JSON payload to every active WebSocket."""
        disconnected: list[WebSocket] = []
        for websocket in self._connections:
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)
