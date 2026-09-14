from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path


class CommandCategory(StrEnum):
    READ_ONLY = "READ_ONLY"
    BUILD = "BUILD"
    TEST = "TEST"
    PACKAGE_INSTALL = "PACKAGE_INSTALL"
    GIT_SAFE = "GIT_SAFE"
    GIT_WRITE = "GIT_WRITE"
    NETWORK = "NETWORK"
    DEPLOY = "DEPLOY"
    DESTRUCTIVE = "DESTRUCTIVE"
    UNKNOWN = "UNKNOWN"


class CommandPolicy:
    _read_only = frozenset({"rg", "grep", "find", "where", "where.exe", "ls", "dir", "pwd"})
    _test_tools = frozenset({"pytest", "ruff", "mypy", "pyright"})
    _build_tools = frozenset({"cargo", "make", "cmake", "gradle", "gradlew", "gradlew.bat"})
    _network_tools = frozenset({"curl", "curl.exe", "wget", "ssh", "scp"})
    _destructive = frozenset({"rm", "rmdir", "del", "format", "diskpart", "remove-item"})
    _git_safe = frozenset({"status", "diff", "log", "show", "branch", "rev-parse", "ls-files"})
    _git_write = frozenset({"add", "commit", "merge", "rebase", "push", "tag", "worktree"})

    def classify(self, command: Sequence[str]) -> CommandCategory:
        if not command:
            return CommandCategory.UNKNOWN
        executable = Path(command[0]).name.casefold()
        arguments = [part.casefold() for part in command[1:]]

        if executable in self._destructive:
            return CommandCategory.DESTRUCTIVE
        if executable == "git" and arguments:
            if arguments[0] in self._git_safe:
                return CommandCategory.GIT_SAFE
            if arguments[0] in self._git_write:
                return CommandCategory.GIT_WRITE
        if executable in self._test_tools:
            return CommandCategory.TEST
        if executable in {"python", "python.exe", "python3", "python3.exe"}:
            if len(arguments) >= 2 and arguments[:2] == ["-m", "pytest"]:
                return CommandCategory.TEST
            return CommandCategory.BUILD
        if executable == "uv":
            if "pytest" in arguments or "ruff" in arguments or "mypy" in arguments:
                return CommandCategory.TEST
            if arguments and arguments[0] in {"sync", "add", "remove"}:
                return CommandCategory.PACKAGE_INSTALL
            return CommandCategory.BUILD
        if executable in {"npm", "npm.cmd", "pnpm", "pnpm.cmd"}:
            if "test" in arguments:
                return CommandCategory.TEST
            if "install" in arguments or "add" in arguments:
                return CommandCategory.PACKAGE_INSTALL
            return CommandCategory.BUILD
        if executable in self._read_only:
            return CommandCategory.READ_ONLY
        if executable in self._build_tools:
            return CommandCategory.BUILD
        if executable in self._network_tools:
            return CommandCategory.NETWORK
        if executable in {"docker", "docker.exe"}:
            if arguments and arguments[0] in {"build", "compose"}:
                return CommandCategory.BUILD
            return CommandCategory.DEPLOY
        return CommandCategory.UNKNOWN

    def permits_check(self, command: Sequence[str]) -> bool:
        return self.classify(command) in {
            CommandCategory.READ_ONLY,
            CommandCategory.BUILD,
            CommandCategory.TEST,
            CommandCategory.GIT_SAFE,
        }
