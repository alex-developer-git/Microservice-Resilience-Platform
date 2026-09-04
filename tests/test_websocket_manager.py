import pytest

from app.websocket import WebSocketStatusManager


class FakeWebSocket:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.accepted = False
        self.fail_send = fail_send
        self.payloads: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, object]) -> None:
        if self.fail_send:
            raise RuntimeError("connection closed")
        self.payloads.append(payload)


@pytest.mark.asyncio
async def test_websocket_status_manager_broadcasts_and_removes_disconnected_clients() -> None:
    manager = WebSocketStatusManager()
    connected = FakeWebSocket()
    disconnected = FakeWebSocket(fail_send=True)

    await manager.connect(connected)
    await manager.connect(disconnected)
    await manager.broadcast({"event_type": "snapshot"})
    await manager.broadcast({"event_type": "update"})
    manager.disconnect(connected)

    assert connected.accepted is True
    assert disconnected.accepted is True
    assert connected.payloads == [{"event_type": "snapshot"}, {"event_type": "update"}]
