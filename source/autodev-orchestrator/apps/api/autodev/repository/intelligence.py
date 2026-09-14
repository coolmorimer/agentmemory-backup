from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field


class TodoFinding(BaseModel):
    path: str
    line: int
    marker: str
    text: str


class RepositoryMap(BaseModel):
    root: str
    languages: dict[str, int] = Field(default_factory=dict)
    frameworks: list[str] = Field(default_factory=list)
    manifests: list[str] = Field(default_factory=list)
    test_configs: list[str] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    migration_paths: list[str] = Field(default_factory=list)
    docker_files: list[str] = Field(default_factory=list)
    ci_files: list[str] = Field(default_factory=list)
    instruction_files: list[str] = Field(default_factory=list)
    generated_directories: list[str] = Field(default_factory=list)
    todos: list[TodoFinding] = Field(default_factory=list)
    scanned_files: int = 0
    truncated: bool = False


class RepoIntelligence:
    _generated_names: ClassVar[set[str]] = {
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "vendor",
    }
    _always_ignore: ClassVar[set[str]] = {".git", ".hg", ".svn"}
    _extensions: ClassVar[dict[str, str]] = {
        ".c": "C",
        ".cpp": "C++",
        ".cs": "C#",
        ".css": "CSS",
        ".go": "Go",
        ".html": "HTML",
        ".java": "Java",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".kt": "Kotlin",
        ".php": "PHP",
        ".py": "Python",
        ".rb": "Ruby",
        ".rs": "Rust",
        ".swift": "Swift",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".vue": "Vue",
    }
    _manifest_names: ClassVar[set[str]] = {
        "Cargo.toml",
        "Gemfile",
        "go.mod",
        "package.json",
        "pom.xml",
        "pyproject.toml",
        "requirements.txt",
    }
    _test_config_names: ClassVar[set[str]] = {
        "jest.config.js",
        "jest.config.ts",
        "playwright.config.js",
        "playwright.config.ts",
        "pytest.ini",
        "tox.ini",
        "vitest.config.js",
        "vitest.config.ts",
    }
    _instruction_names: ClassVar[set[str]] = {
        "AGENTS.md",
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "README.md",
    }
    _entrypoint_names: ClassVar[set[str]] = {
        "app.py",
        "main.go",
        "main.py",
        "manage.py",
        "server.js",
        "server.ts",
        "wsgi.py",
    }
    _todo_pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(TODO|FIXME|HACK|XXX)\b[:\s-]*(.*)", re.IGNORECASE
    )

    def __init__(self, root: Path, *, max_files: int = 20_000, max_text_bytes: int = 256_000):
        self.root = root.resolve()
        self.max_files = max_files
        self.max_text_bytes = max_text_bytes
        if not self.root.is_dir():
            raise ValueError(f"repository root does not exist: {self.root}")

    def scan(self) -> RepositoryMap:
        languages: Counter[str] = Counter()
        result = RepositoryMap(root=str(self.root))
        paths: list[Path] = []
        for current, directory_names, file_names in os.walk(self.root, followlinks=False):
            current_path = Path(current)
            kept_directories: list[str] = []
            for directory in sorted(directory_names):
                relative = (current_path / directory).relative_to(self.root).as_posix()
                if directory in self._generated_names:
                    result.generated_directories.append(relative)
                elif directory not in self._always_ignore:
                    kept_directories.append(directory)
            directory_names[:] = kept_directories
            for name in sorted(file_names):
                path = current_path / name
                if path.is_symlink():
                    continue
                paths.append(path)
                if len(paths) >= self.max_files:
                    result.truncated = True
                    break
            if result.truncated:
                break
        for path in paths:
            relative = path.relative_to(self.root).as_posix()
            result.scanned_files += 1
            language = self._extensions.get(path.suffix.casefold())
            if language:
                languages[language] += 1
            self._classify_path(result, path, relative)
            self._scan_text(result, path, relative)
        result.languages = dict(sorted(languages.items(), key=lambda item: (-item[1], item[0])))
        result.frameworks = sorted(set(result.frameworks))
        for field in (
            "manifests",
            "test_configs",
            "entrypoints",
            "migration_paths",
            "docker_files",
            "ci_files",
            "instruction_files",
            "generated_directories",
        ):
            setattr(result, field, sorted(set(getattr(result, field))))
        return result

    def _classify_path(self, result: RepositoryMap, path: Path, relative: str) -> None:
        name = path.name
        parts = {part.casefold() for part in path.parts}
        if name in self._manifest_names:
            result.manifests.append(relative)
        if name in self._test_config_names or (name.startswith("pytest") and name.endswith(".ini")):
            result.test_configs.append(relative)
        if name in self._entrypoint_names or relative in {"src/index.ts", "src/index.js"}:
            result.entrypoints.append(relative)
        if "migrations" in parts or "alembic" in parts:
            result.migration_paths.append(relative)
        if name == "Dockerfile" or name.startswith("Dockerfile.") or "compose" in name.casefold():
            result.docker_files.append(relative)
        if (".github" in parts and "workflows" in parts) or name == ".gitlab-ci.yml":
            result.ci_files.append(relative)
        if name in self._instruction_names:
            result.instruction_files.append(relative)

    def _scan_text(self, result: RepositoryMap, path: Path, relative: str) -> None:
        try:
            if path.stat().st_size > self.max_text_bytes:
                return
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        if path.name == "package.json":
            self._package_frameworks(result, content)
        elif path.name in {"pyproject.toml", "requirements.txt"}:
            lowered = content.casefold()
            for dependency, framework in {
                "django": "Django",
                "fastapi": "FastAPI",
                "flask": "Flask",
                "litestar": "Litestar",
            }.items():
                if dependency in lowered:
                    result.frameworks.append(framework)
        for line_number, line in enumerate(content.splitlines(), start=1):
            match = self._todo_pattern.search(line)
            if match and len(result.todos) < 500:
                result.todos.append(
                    TodoFinding(
                        path=relative,
                        line=line_number,
                        marker=match.group(1).upper(),
                        text=match.group(2).strip()[:300],
                    )
                )

    @staticmethod
    def _package_frameworks(result: RepositoryMap, content: str) -> None:
        try:
            package = json.loads(content)
        except json.JSONDecodeError:
            return
        dependencies = {
            **(package.get("dependencies") or {}),
            **(package.get("devDependencies") or {}),
        }
        for dependency, framework in {
            "@angular/core": "Angular",
            "next": "Next.js",
            "react": "React",
            "svelte": "Svelte",
            "vue": "Vue",
        }.items():
            if dependency in dependencies:
                result.frameworks.append(framework)
