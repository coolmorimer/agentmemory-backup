from __future__ import annotations

from typing import Any

import httpx
from typer.testing import CliRunner

from autodev.cli import app


class FakeResponse:
    def __init__(self, body: object) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._body


def test_project_create_can_goal_plan_and_start(monkeypatch: Any) -> None:
    requests: list[tuple[str, str, object]] = []

    def request(method: str, url: str, **kwargs: object) -> FakeResponse:
        requests.append((method, url, kwargs.get("json")))
        if url.endswith("/api/projects"):
            return FakeResponse({"id": "project-1", "status": "CREATED"})
        if url.endswith("/start"):
            return FakeResponse({"id": "project-1", "status": "IMPLEMENTING"})
        return FakeResponse({})

    monkeypatch.setattr(httpx, "request", request)
    result = CliRunner().invoke(
        app,
        [
            "project",
            "create",
            "--name",
            "fixture",
            "--repository-path",
            "C:/fixture",
            "--goal",
            "Ship it",
            "--start",
        ],
    )

    assert result.exit_code == 0
    assert '"status": "IMPLEMENTING"' in result.stdout
    assert [item[0] for item in requests] == ["POST", "POST", "POST", "POST"]


def test_models_command_prints_json(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        httpx,
        "request",
        lambda *args, **kwargs: FakeResponse([{"id": "codex/app-server"}]),
    )

    result = CliRunner().invoke(app, ["models"])

    assert result.exit_code == 0
    assert "codex/app-server" in result.stdout


def test_doctor_recognizes_live_ollama_api_without_path_entry(monkeypatch: Any) -> None:
    monkeypatch.setattr("autodev.cli.shutil.which", lambda name: None if name == "ollama" else name)
    monkeypatch.setattr("autodev.cli._ollama_api_available", lambda _base_url: True)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "ollama: ok (API)" in result.stdout
