from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_local_file_broker_resolves_one_exact_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "synthetic-day5.txt"
    target.write_text("synthetic evidence", encoding="utf-8")
    monkeypatch.setenv("AI_BROWSER_ASSIST_DOWNLOADS_DIR", str(tmp_path))

    response = TestClient(app).post(
        "/local-files/resolve-download",
        headers={"X-AI-Browser-Assist-Extension": "service-worker"},
        json={"filename": "synthetic-day5.txt"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "absolute_path": str(target.resolve()),
        "filename": "synthetic-day5.txt",
        "mime_type": "text/plain",
        "size_bytes": len("synthetic evidence"),
        "source": "local_downloads_broker_exact_match",
    }


@pytest.mark.parametrize("filename", ("../secret.txt", "folder/secret.txt", "folder\\secret.txt"))
def test_local_file_broker_rejects_path_substitution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    filename: str,
) -> None:
    monkeypatch.setenv("AI_BROWSER_ASSIST_DOWNLOADS_DIR", str(tmp_path))
    response = TestClient(app).post(
        "/local-files/resolve-download",
        headers={"X-AI-Browser-Assist-Extension": "service-worker"},
        json={"filename": filename},
    )
    assert response.status_code == 400


def test_local_file_broker_rejects_non_executor_caller(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_BROWSER_ASSIST_DOWNLOADS_DIR", str(tmp_path))
    response = TestClient(app).post(
        "/local-files/resolve-download",
        json={"filename": "synthetic-day5.txt"},
    )
    assert response.status_code == 403
