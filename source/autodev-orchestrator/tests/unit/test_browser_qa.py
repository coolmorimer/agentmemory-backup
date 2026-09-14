from __future__ import annotations

from pathlib import Path

import pytest

from autodev.qa.browser import (
    BrowserAction,
    BrowserFlow,
    CliResult,
    PlaywrightCliRunner,
)


class FakeCliExecutor:
    def __init__(self, *, console: str = "No console messages", requests: str = "GET / 200"):
        self.console = console
        self.requests = requests
        self.commands: list[list[str]] = []

    async def run(self, command: list[str], *, cwd: Path) -> CliResult:
        self.commands.append(command)
        if "console" in command:
            return CliResult(exit_code=0, output=self.console)
        if "requests" in command:
            return CliResult(exit_code=0, output=self.requests)
        return CliResult(exit_code=0, output="ok")


async def test_browser_runner_snapshots_before_ref_actions_and_collects_diagnostics(
    tmp_path: Path,
) -> None:
    executor = FakeCliExecutor()
    result = await PlaywrightCliRunner(
        tmp_path,
        command_prefix=["playwright-cli"],
        executor=executor,
    ).run(
        BrowserFlow(
            url="http://127.0.0.1:8000/docs",
            ready_text="AutoDev",
            actions=[BrowserAction(command="click", target="e1")],
        ),
        run_id="smoke",
    )

    assert result.passed
    assert result.commands_run == [
        "open http://127.0.0.1:8000/docs",
        "tracing-start",
        "snapshot",
        "find AutoDev",
        "click e1",
        "snapshot",
        "console error",
        "requests",
        "screenshot",
        "tracing-stop",
        "close",
    ]


async def test_browser_runner_fails_on_console_and_http_errors(tmp_path: Path) -> None:
    executor = FakeCliExecutor(console="error: boom", requests="GET /api 500")

    result = await PlaywrightCliRunner(
        tmp_path, command_prefix=["playwright-cli"], executor=executor
    ).run(BrowserFlow(url="https://example.test"), run_id="failure")

    assert result.passed is False
    assert result.console_errors == ["error: boom"]
    assert result.failed_requests == ["GET /api 500"]


async def test_browser_runner_rejects_artifact_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid browser QA run id"):
        await PlaywrightCliRunner(
            tmp_path, command_prefix=["playwright-cli"], executor=FakeCliExecutor()
        ).run(BrowserFlow(url="https://example.test"), run_id="../escape")
