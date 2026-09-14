from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from autodev.repository.intelligence import RepoIntelligence


class CheckPlan(BaseModel):
    commands: list[list[str]] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


class CheckDiscovery:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()

    def discover(self) -> CheckPlan:
        repository_map = RepoIntelligence(self.repository).scan()
        commands: list[list[str]] = []
        rationale: list[str] = []
        manifests = set(repository_map.manifests)
        if (
            "Python" in repository_map.languages
            or "pyproject.toml" in manifests
            or "requirements.txt" in manifests
        ):
            prefix = (
                ["uv", "run"] if (self.repository / "uv.lock").is_file() else [sys.executable, "-m"]
            )
            if self._has_python_tests(repository_map.test_configs):
                commands.append([*prefix, "pytest", "-q"])
                rationale.append("Python tests detected")
            pyproject = self._text("pyproject.toml").casefold()
            if "ruff" in pyproject:
                commands.extend(
                    [
                        [*prefix, "ruff", "format", "--check", "."],
                        [*prefix, "ruff", "check", "."],
                    ]
                )
                rationale.append("Ruff configuration detected")
            if "mypy" in pyproject:
                commands.append([*prefix, "mypy", "."])
                rationale.append("mypy configuration detected")
            if (self.repository / "uv.lock").is_file():
                commands.append(["uv", "lock", "--check"])
                rationale.append("uv lockfile detected")
        if "package.json" in manifests:
            scripts = self._package_scripts()
            for script in ("lint", "typecheck", "test", "build"):
                if script in scripts:
                    commands.append(["npm", "run", script])
                    rationale.append(f"package.json script detected: {script}")
        if "go.mod" in manifests:
            commands.append(["go", "test", "./..."])
            rationale.append("Go module detected")
        if "Cargo.toml" in manifests:
            commands.extend([["cargo", "fmt", "--check"], ["cargo", "test"]])
            rationale.append("Rust crate detected")
        return CheckPlan(commands=_deduplicate(commands), rationale=rationale)

    def _has_python_tests(self, test_configs: list[str]) -> bool:
        return bool(test_configs) or (self.repository / "tests").is_dir()

    def _package_scripts(self) -> dict[str, str]:
        try:
            payload = json.loads(self._text("package.json"))
        except json.JSONDecodeError:
            return {}
        scripts = payload.get("scripts") or {}
        return {str(key): str(value) for key, value in scripts.items()}

    def _text(self, relative: str) -> str:
        path = self.repository / relative
        try:
            return path.read_text(encoding="utf-8") if path.is_file() else ""
        except (OSError, UnicodeDecodeError):
            return ""


def _deduplicate(commands: list[list[str]]) -> list[list[str]]:
    seen: set[tuple[str, ...]] = set()
    result: list[list[str]] = []
    for command in commands:
        key = tuple(command)
        if key not in seen:
            seen.add(key)
            result.append(command)
    return result
