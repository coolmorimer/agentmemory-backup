from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from autodev.domain.enums import ProjectStatus, TaskStatus


@dataclass(slots=True)
class InvalidTransition(ValueError):
    entity: str
    current: str
    target: str

    def __str__(self) -> str:
        return f"invalid {self.entity} transition: {self.current} -> {self.target}"


class StateMachine[StateT: (ProjectStatus, TaskStatus)]:
    entity: ClassVar[str]
    transitions: ClassVar[Mapping[Any, frozenset[Any]]]

    def validate(self, current: StateT, target: StateT) -> None:
        if target not in self.transitions.get(current, frozenset()):
            raise InvalidTransition(self.entity, current.value, target.value)

    def transition(self, current: StateT, target: StateT) -> StateT:
        self.validate(current, target)
        return target


class ProjectStateMachine(StateMachine[ProjectStatus]):
    entity = "project"
    transitions: ClassVar[Mapping[ProjectStatus, frozenset[ProjectStatus]]] = {
        ProjectStatus.CREATED: frozenset(
            {
                ProjectStatus.RESEARCHING,
                ProjectStatus.PLANNING,
                ProjectStatus.PAUSED,
                ProjectStatus.FAILED,
            }
        ),
        ProjectStatus.RESEARCHING: frozenset(
            {
                ProjectStatus.PLANNING,
                ProjectStatus.BLOCKED,
                ProjectStatus.FAILED,
                ProjectStatus.PAUSED,
            }
        ),
        ProjectStatus.PLANNING: frozenset(
            {ProjectStatus.READY, ProjectStatus.BLOCKED, ProjectStatus.FAILED, ProjectStatus.PAUSED}
        ),
        ProjectStatus.READY: frozenset(
            {ProjectStatus.IMPLEMENTING, ProjectStatus.PAUSED, ProjectStatus.FAILED}
        ),
        ProjectStatus.IMPLEMENTING: frozenset(
            {
                ProjectStatus.TESTING,
                ProjectStatus.BLOCKED,
                ProjectStatus.FAILED,
                ProjectStatus.PAUSED,
            }
        ),
        ProjectStatus.TESTING: frozenset(
            {
                ProjectStatus.IMPLEMENTING,
                ProjectStatus.REVIEWING,
                ProjectStatus.BLOCKED,
                ProjectStatus.FAILED,
                ProjectStatus.PAUSED,
            }
        ),
        ProjectStatus.REVIEWING: frozenset(
            {
                ProjectStatus.IMPLEMENTING,
                ProjectStatus.STAGING,
                ProjectStatus.COMPLETED,
                ProjectStatus.BLOCKED,
                ProjectStatus.FAILED,
                ProjectStatus.PAUSED,
            }
        ),
        ProjectStatus.STAGING: frozenset(
            {
                ProjectStatus.VERIFYING_STAGING,
                ProjectStatus.BLOCKED,
                ProjectStatus.FAILED,
                ProjectStatus.PAUSED,
            }
        ),
        ProjectStatus.VERIFYING_STAGING: frozenset(
            {
                ProjectStatus.DEPLOYING,
                ProjectStatus.COMPLETED,
                ProjectStatus.IMPLEMENTING,
                ProjectStatus.BLOCKED,
                ProjectStatus.FAILED,
                ProjectStatus.PAUSED,
            }
        ),
        ProjectStatus.DEPLOYING: frozenset(
            {
                ProjectStatus.VERIFYING_PRODUCTION,
                ProjectStatus.BLOCKED,
                ProjectStatus.FAILED,
                ProjectStatus.PAUSED,
            }
        ),
        ProjectStatus.VERIFYING_PRODUCTION: frozenset(
            {
                ProjectStatus.COMPLETED,
                ProjectStatus.IMPLEMENTING,
                ProjectStatus.BLOCKED,
                ProjectStatus.FAILED,
                ProjectStatus.PAUSED,
            }
        ),
        ProjectStatus.BLOCKED: frozenset(
            {
                ProjectStatus.READY,
                ProjectStatus.IMPLEMENTING,
                ProjectStatus.FAILED,
                ProjectStatus.PAUSED,
            }
        ),
        ProjectStatus.PAUSED: frozenset(
            {
                ProjectStatus.CREATED,
                ProjectStatus.RESEARCHING,
                ProjectStatus.PLANNING,
                ProjectStatus.READY,
                ProjectStatus.IMPLEMENTING,
                ProjectStatus.TESTING,
                ProjectStatus.REVIEWING,
                ProjectStatus.STAGING,
                ProjectStatus.VERIFYING_STAGING,
                ProjectStatus.DEPLOYING,
                ProjectStatus.VERIFYING_PRODUCTION,
                ProjectStatus.BLOCKED,
            }
        ),
        ProjectStatus.COMPLETED: frozenset(),
        ProjectStatus.FAILED: frozenset(),
    }


class TaskStateMachine(StateMachine[TaskStatus]):
    entity = "task"
    transitions: ClassVar[Mapping[TaskStatus, frozenset[TaskStatus]]] = {
        TaskStatus.DRAFT: frozenset(
            {
                TaskStatus.READY,
                TaskStatus.WAITING_DEPENDENCY,
                TaskStatus.PAUSED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.READY: frozenset(
            {
                TaskStatus.RUNNING,
                TaskStatus.WAITING_DEPENDENCY,
                TaskStatus.BLOCKED,
                TaskStatus.PAUSED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.WAITING_DEPENDENCY: frozenset(
            {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.PAUSED, TaskStatus.CANCELLED}
        ),
        TaskStatus.WAITING_PROVIDER: frozenset(
            {
                TaskStatus.READY,
                TaskStatus.RUNNING,
                TaskStatus.BLOCKED,
                TaskStatus.FAILED,
                TaskStatus.PAUSED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.RUNNING: frozenset(
            {
                TaskStatus.READY,
                TaskStatus.WAITING_PROVIDER,
                TaskStatus.TESTING,
                TaskStatus.FIX_REQUIRED,
                TaskStatus.BLOCKED,
                TaskStatus.FAILED,
                TaskStatus.PAUSED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.TESTING: frozenset(
            {
                TaskStatus.REVIEWING,
                TaskStatus.FIX_REQUIRED,
                TaskStatus.BLOCKED,
                TaskStatus.FAILED,
                TaskStatus.PAUSED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.REVIEWING: frozenset(
            {
                TaskStatus.APPROVED,
                TaskStatus.FIX_REQUIRED,
                TaskStatus.BLOCKED,
                TaskStatus.FAILED,
                TaskStatus.PAUSED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.FIX_REQUIRED: frozenset(
            {
                TaskStatus.READY,
                TaskStatus.RUNNING,
                TaskStatus.BLOCKED,
                TaskStatus.FAILED,
                TaskStatus.PAUSED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.APPROVED: frozenset(
            {TaskStatus.COMPLETED, TaskStatus.FIX_REQUIRED, TaskStatus.BLOCKED}
        ),
        TaskStatus.BLOCKED: frozenset(
            {TaskStatus.READY, TaskStatus.FAILED, TaskStatus.PAUSED, TaskStatus.CANCELLED}
        ),
        TaskStatus.FAILED: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
        TaskStatus.PAUSED: frozenset(
            {
                TaskStatus.DRAFT,
                TaskStatus.READY,
                TaskStatus.WAITING_DEPENDENCY,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.COMPLETED: frozenset(),
        TaskStatus.CANCELLED: frozenset(),
    }
