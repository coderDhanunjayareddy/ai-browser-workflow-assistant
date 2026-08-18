from app.api.routes.health import health_check
from app.core.config import settings


class _HealthyDb:
    def execute(self, _query):
        return 1


def test_health_exposes_runtime_identity_for_extension_handshake() -> None:
    payload = health_check(_HealthyDb())

    assert payload["status"] == "ok"
    assert payload["db"] == "connected"
    assert payload["runtime"]["service"] == "ai-browser-assist-backend"
    assert payload["runtime"]["app_version"] == settings.app_version
    assert payload["runtime"]["build_commit"] == settings.build_commit
    assert payload["runtime"]["build_id"] == settings.build_id
    assert payload["runtime"]["canonical_backend_url"] == settings.canonical_backend_url.rstrip("/")
    assert payload["runtime"]["process_id"] > 0


def test_health_reports_disconnected_database_without_losing_runtime_identity() -> None:
    class _FailedDb:
        def execute(self, _query):
            raise RuntimeError("database unavailable")

    payload = health_check(_FailedDb())

    assert payload["status"] == "ok"
    assert payload["db"] == "disconnected"
    assert payload["runtime"]["build_id"] == settings.build_id
