from __future__ import annotations

import sys
import uuid
from pathlib import Path

from autodev.codex.app_server import CodexAppServerAdapter
from autodev.codex.base import CodingTask


async def test_adapter_runs_current_lifecycle_and_handles_safe_approval(tmp_path: Path) -> None:
    fake_server = Path(__file__).parents[1] / "fixtures" / "fake_codex_app_server.py"
    adapter = CodexAppServerAdapter(
        command=[sys.executable, str(fake_server)], turn_timeout_seconds=5
    )
    result = await adapter.run_task(
        CodingTask(
            task_id=uuid.uuid4(),
            key="TASK-1",
            title="Add tags",
            description="Add tags to todo items.",
            repository_path=tmp_path,
            required_checks=[[sys.executable, "-m", "pytest"]],
        )
    )

    assert result.status == "completed"
    assert result.thread_id == "thread-test"
    assert result.turn_id == "turn-test"
    assert result.changed_files == ["todo.py"]
    assert result.summary == "Implemented tags."


async def test_adapter_reports_process_failure_without_hanging(tmp_path: Path) -> None:
    fake_server = Path(__file__).parents[1] / "fixtures" / "fake_codex_app_server.py"
    adapter = CodexAppServerAdapter(
        command=[sys.executable, str(fake_server), "--die"], turn_timeout_seconds=2
    )
    result = await adapter.run_task(
        CodingTask(
            task_id=uuid.uuid4(),
            key="TASK-1",
            title="Add tags",
            description="Add tags to todo items.",
            repository_path=tmp_path,
        )
    )

    assert result.status == "failed"
    assert "transport closed" in (result.error or "")
