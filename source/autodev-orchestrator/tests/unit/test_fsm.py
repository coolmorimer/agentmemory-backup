import pytest

from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.domain.fsm import InvalidTransition, ProjectStateMachine, TaskStateMachine


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProjectStatus.CREATED, ProjectStatus.RESEARCHING),
        (ProjectStatus.PLANNING, ProjectStatus.READY),
        (ProjectStatus.READY, ProjectStatus.IMPLEMENTING),
        (ProjectStatus.TESTING, ProjectStatus.REVIEWING),
        (ProjectStatus.REVIEWING, ProjectStatus.COMPLETED),
        (ProjectStatus.VERIFYING_PRODUCTION, ProjectStatus.COMPLETED),
        (ProjectStatus.PAUSED, ProjectStatus.IMPLEMENTING),
    ],
)
def test_valid_project_transitions(current: ProjectStatus, target: ProjectStatus) -> None:
    assert ProjectStateMachine().transition(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProjectStatus.CREATED, ProjectStatus.COMPLETED),
        (ProjectStatus.READY, ProjectStatus.DEPLOYING),
        (ProjectStatus.COMPLETED, ProjectStatus.IMPLEMENTING),
        (ProjectStatus.FAILED, ProjectStatus.READY),
    ],
)
def test_invalid_project_transitions(current: ProjectStatus, target: ProjectStatus) -> None:
    with pytest.raises(InvalidTransition, match="invalid project transition"):
        ProjectStateMachine().transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TaskStatus.DRAFT, TaskStatus.READY),
        (TaskStatus.READY, TaskStatus.RUNNING),
        (TaskStatus.RUNNING, TaskStatus.WAITING_PROVIDER),
        (TaskStatus.WAITING_PROVIDER, TaskStatus.READY),
        (TaskStatus.RUNNING, TaskStatus.TESTING),
        (TaskStatus.TESTING, TaskStatus.REVIEWING),
        (TaskStatus.REVIEWING, TaskStatus.APPROVED),
        (TaskStatus.APPROVED, TaskStatus.COMPLETED),
        (TaskStatus.FIX_REQUIRED, TaskStatus.READY),
        (TaskStatus.READY, TaskStatus.PAUSED),
        (TaskStatus.RUNNING, TaskStatus.PAUSED),
        (TaskStatus.PAUSED, TaskStatus.READY),
    ],
)
def test_valid_task_transitions(current: TaskStatus, target: TaskStatus) -> None:
    assert TaskStateMachine().transition(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TaskStatus.DRAFT, TaskStatus.COMPLETED),
        (TaskStatus.READY, TaskStatus.APPROVED),
        (TaskStatus.TESTING, TaskStatus.COMPLETED),
        (TaskStatus.COMPLETED, TaskStatus.READY),
        (TaskStatus.CANCELLED, TaskStatus.RUNNING),
    ],
)
def test_invalid_task_transitions(current: TaskStatus, target: TaskStatus) -> None:
    with pytest.raises(InvalidTransition, match="invalid task transition"):
        TaskStateMachine().transition(current, target)
