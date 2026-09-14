from __future__ import annotations

import asyncio
import re
from pathlib import Path

from pydantic import BaseModel

from autodev.security.secrets import SecretScanner


class GitError(RuntimeError):
    pass


class GitConflictError(GitError):
    def __init__(self, operation: str, conflicted_files: list[str]) -> None:
        super().__init__(f"git {operation} conflicted: {', '.join(conflicted_files)}")
        self.operation = operation
        self.conflicted_files = conflicted_files


class GitCommitResult(BaseModel):
    sha: str
    message: str
    changed_files: list[str]


class GitStatus(BaseModel):
    branch: str
    head_sha: str | None
    changed_files: list[str]
    clean: bool


class GitWorktree(BaseModel):
    name: str
    path: Path
    branch: str


class GitRepository:
    _ref_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

    def __init__(self, path: Path, *, worktree_root: Path | None = None) -> None:
        self.path = path.resolve()
        if not self.path.is_dir():
            raise GitError(f"repository does not exist: {self.path}")
        self.worktree_root = (
            worktree_root.resolve()
            if worktree_root
            else self.path.parent.joinpath(f".{self.path.name}-worktrees").resolve()
        )

    @classmethod
    async def clone(cls, source: str, destination: Path) -> GitRepository:
        target = cls._prepare_clone_destination(destination)
        process = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--",
            source,
            str(target),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            error_tail = stderr.decode(errors="replace")[-2000:]
            raise GitError(f"git clone failed ({process.returncode}): {error_tail}")
        return cls(target)

    @staticmethod
    def _prepare_clone_destination(destination: Path) -> Path:
        target = destination.resolve()
        if target.exists() and any(target.iterdir()):
            raise GitError(f"clone destination is not empty: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    async def initialize(self, *, branch: str = "main") -> None:
        await self._run("init", "-b", branch)

    async def is_repository(self) -> bool:
        result = await self._run("rev-parse", "--is-inside-work-tree", check=False)
        return result[0] == 0 and result[1].strip() == "true"

    async def changed_files(self) -> list[str]:
        _, output, _ = await self._run("status", "--porcelain=v1", "-z", "--untracked-files=all")
        files: list[str] = []
        entries = output.split("\0")
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if len(entry) < 4:
                continue
            files.append(entry[3:])
            if entry[0] in {"R", "C"} or entry[1] in {"R", "C"}:
                index += 1
        return sorted(set(files))

    async def status(self) -> GitStatus:
        _, branch, _ = await self._run("branch", "--show-current")
        head_code, head, _ = await self._run("rev-parse", "HEAD", check=False)
        changed_files = await self.changed_files()
        return GitStatus(
            branch=branch.strip(),
            head_sha=head.strip() if head_code == 0 else None,
            changed_files=changed_files,
            clean=not changed_files,
        )

    async def diff(self) -> str:
        _, unstaged, _ = await self._run("diff", "--no-ext-diff", "--binary")
        _, staged, _ = await self._run("diff", "--cached", "--no-ext-diff", "--binary")
        return unstaged + staged

    async def create_branch(self, name: str, *, start_point: str = "HEAD") -> None:
        await self._run("branch", self._validate_ref(name), self._validate_ref(start_point))

    async def branch_exists(self, name: str) -> bool:
        code, _, _ = await self._run(
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{self._validate_ref(name)}",
            check=False,
        )
        return code == 0

    async def create_worktree(
        self,
        name: str,
        *,
        branch: str,
        start_point: str = "HEAD",
        create_branch: bool = True,
    ) -> GitWorktree:
        safe_name = self._validate_worktree_name(name)
        safe_branch = self._validate_ref(branch)
        destination = (self.worktree_root / safe_name).resolve()
        self._assert_worktree_path(destination)
        if destination.exists():
            raise GitError(f"worktree destination already exists: {destination}")
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        if create_branch:
            await self._run(
                "worktree",
                "add",
                "-b",
                safe_branch,
                str(destination),
                self._validate_ref(start_point),
            )
        else:
            await self._run("worktree", "add", str(destination), safe_branch)
        return GitWorktree(name=safe_name, path=destination, branch=safe_branch)

    async def remove_worktree(self, name: str, *, force: bool = False) -> None:
        destination = (self.worktree_root / self._validate_worktree_name(name)).resolve()
        self._assert_worktree_path(destination)
        arguments = ["worktree", "remove"]
        if force:
            arguments.append("--force")
        arguments.append(str(destination))
        await self._run(*arguments)
        await self._run("worktree", "prune")

    async def merge(self, branch: str, *, fast_forward_only: bool = False) -> str:
        arguments = ["merge", "--no-edit"]
        if fast_forward_only:
            arguments.append("--ff-only")
        arguments.append(self._validate_ref(branch))
        code, _, error = await self._run(*arguments, check=False)
        if code != 0:
            conflicts = await self._conflicted_files()
            await self._run("merge", "--abort", check=False)
            if conflicts:
                raise GitConflictError("merge", conflicts)
            raise GitError(f"git merge failed ({code}): {error[-2000:]}")
        _, sha, _ = await self._run("rev-parse", "HEAD")
        return sha.strip()

    async def rebase(self, onto: str) -> str:
        code, _, error = await self._run("rebase", self._validate_ref(onto), check=False)
        if code != 0:
            conflicts = await self._conflicted_files()
            await self._run("rebase", "--abort", check=False)
            if conflicts:
                raise GitConflictError("rebase", conflicts)
            raise GitError(f"git rebase failed ({code}): {error[-2000:]}")
        _, sha, _ = await self._run("rev-parse", "HEAD")
        return sha.strip()

    async def tag(self, name: str, *, message: str | None = None) -> None:
        safe_name = self._validate_ref(name)
        if message:
            await self._run("tag", "-a", safe_name, "-m", message)
        else:
            await self._run("tag", safe_name)

    async def tags(self) -> list[str]:
        _, output, _ = await self._run("tag", "--list")
        return sorted(filter(None, output.splitlines()))

    async def push(self, *, remote: str = "origin", refspec: str = "HEAD") -> None:
        await self._run("push", self._validate_ref(remote), self._validate_ref(refspec))

    async def revert_commit(self, sha: str) -> str:
        await self._run("revert", "--no-edit", self._validate_sha(sha))
        _, result, _ = await self._run("rev-parse", "HEAD")
        return result.strip()

    async def commit_task(
        self,
        *,
        task_key: str,
        title: str,
        changed_files: list[str],
        checks: list[str],
    ) -> GitCommitResult:
        if not changed_files:
            raise GitError("refusing to create an empty task commit")
        _, already_staged, _ = await self._run("diff", "--cached", "--name-only", "-z")
        if already_staged:
            raise GitError("refusing task commit while unrelated staged changes exist")
        safe_files = [self._validate_relative_path(path) for path in changed_files]
        await self._run("add", "--", *safe_files)
        _, staged, _ = await self._run("diff", "--cached", "--name-only", "-z")
        staged_files = [path for path in staged.split("\0") if path]
        if not staged_files:
            raise GitError("no staged changes remain after scope validation")
        _, staged_diff, _ = await self._run(
            "diff", "--cached", "--no-ext-diff", "--unified=0", "--", *safe_files
        )
        secret_findings = SecretScanner().scan_diff(staged_diff)
        if secret_findings:
            await self._run("reset", "--", *safe_files)
            summary = ", ".join(
                f"{finding.path}:{finding.line or '?'} ({finding.kind})"
                for finding in secret_findings
            )
            raise GitError(f"secret scan blocked task commit: {summary}")
        message = (
            f"feat(task): {title}\n\n"
            f"Task: {task_key}\n"
            f"Checks: {', '.join(checks) if checks else 'none'}\n"
            "Review: approved"
        )
        await self._run(
            "-c",
            "user.name=AutoDev Orchestrator",
            "-c",
            "user.email=autodev@localhost",
            "commit",
            "-m",
            message,
        )
        _, sha, _ = await self._run("rev-parse", "HEAD")
        return GitCommitResult(sha=sha.strip(), message=message, changed_files=sorted(staged_files))

    async def _conflicted_files(self) -> list[str]:
        _, output, _ = await self._run("diff", "--name-only", "--diff-filter=U", "-z", check=False)
        return sorted(path for path in output.split("\0") if path)

    def _validate_relative_path(self, value: str) -> str:
        candidate = Path(value)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.path / candidate).resolve()
        try:
            relative = resolved.relative_to(self.path)
        except ValueError as error:
            raise GitError(f"changed path escapes repository: {value}") from error
        return relative.as_posix()

    @classmethod
    def _validate_ref(cls, value: str) -> str:
        if (
            not cls._ref_pattern.fullmatch(value)
            or ".." in value
            or value.endswith((".", "/"))
            or value.startswith("-")
            or "@{" in value
        ):
            raise GitError(f"invalid Git ref: {value}")
        return value

    @staticmethod
    def _validate_sha(value: str) -> str:
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", value):
            raise GitError(f"invalid commit SHA: {value}")
        return value

    @staticmethod
    def _validate_worktree_name(value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) or ".." in value:
            raise GitError(f"invalid worktree name: {value}")
        return value

    def _assert_worktree_path(self, path: Path) -> None:
        try:
            path.relative_to(self.worktree_root)
        except ValueError as error:
            raise GitError(f"worktree path escapes managed root: {path}") from error

    async def _run(self, *arguments: str, check: bool = True) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(self.path),
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode(errors="replace")
        error_output = stderr.decode(errors="replace")
        if check and process.returncode != 0:
            raise GitError(
                f"git {arguments[0] if arguments else ''} failed ({process.returncode}): "
                f"{error_output[-2000:]}"
            )
        return process.returncode or 0, output, error_output
