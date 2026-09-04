import main


def test_entrypoint_exports_fastapi_app() -> None:
    """Verify the project entrypoint exports the FastAPI app."""
    assert main.app.title == "Microservice Resilience Platform"
