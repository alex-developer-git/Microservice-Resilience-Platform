from types import SimpleNamespace

import pytest

from app import tracing
from app.config import Settings


def test_configure_tracing_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_tracing_configured", False)

    tracing.configure_tracing(SimpleNamespace(), Settings(otel_enabled=False))

    assert tracing._tracing_configured is False


def test_configure_tracing_marks_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Instrumentor:
        @staticmethod
        def instrument_app(app: object, *, excluded_urls: str) -> None:
            calls.append(excluded_urls)

    monkeypatch.setattr(tracing, "_tracing_configured", False)
    monkeypatch.setattr(tracing, "_configure_trace_provider", lambda settings: True)
    monkeypatch.setattr(tracing, "_instrument_common_clients", lambda: calls.append("clients"))
    monkeypatch.setattr(tracing, "_instrument_celery", lambda: calls.append("celery"))
    monkeypatch.setitem(
        __import__("sys").modules,
        "opentelemetry.instrumentation.fastapi",
        SimpleNamespace(FastAPIInstrumentor=Instrumentor),
    )

    tracing.configure_tracing(SimpleNamespace(), Settings(otel_enabled=True))

    assert tracing._tracing_configured is True
    assert calls == [r"^/health$", "clients", "celery"]


def test_configure_worker_tracing_marks_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tracing, "_worker_tracing_configured", False)
    monkeypatch.setattr(tracing, "_configure_trace_provider", lambda settings: True)
    monkeypatch.setattr(tracing, "_instrument_common_clients", lambda: calls.append("clients"))
    monkeypatch.setattr(tracing, "_instrument_celery", lambda: calls.append("celery"))

    tracing.configure_worker_tracing(Settings(otel_enabled=True))

    assert tracing._worker_tracing_configured is True
    assert calls == ["celery", "clients"]


def test_instrument_sqlalchemy_engine_uses_sync_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    class Instrumentor:
        def instrument(self, *, engine: object) -> None:
            calls.append(engine)

    engine = SimpleNamespace(sync_engine=object())
    monkeypatch.setattr(tracing, "_tracing_configured", True)
    monkeypatch.setattr(tracing, "_worker_tracing_configured", False)
    monkeypatch.setitem(
        __import__("sys").modules,
        "opentelemetry.instrumentation.sqlalchemy",
        SimpleNamespace(SQLAlchemyInstrumentor=Instrumentor),
    )

    tracing.instrument_sqlalchemy_engine(engine)

    assert calls == [engine.sync_engine]


def test_instrument_sqlalchemy_engine_skips_when_tracing_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_tracing_configured", False)
    monkeypatch.setattr(tracing, "_worker_tracing_configured", False)

    tracing.instrument_sqlalchemy_engine(SimpleNamespace(sync_engine=object()))
