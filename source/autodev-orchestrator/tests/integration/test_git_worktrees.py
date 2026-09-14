from __future__ import annotations

from pathlib import Path

import pytest

from autodev.git.repository import GitConflictError, GitError, GitRepository


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


async def test_managed_worktree_merge_tag_revert_and_clone(tmp_path: Path) -> None:
    repository_path = tmp_path / "source"
    repository_path.mkdir()
    repository = GitRepository(repository_path)
    await repository.initialize()
    write_text(repository_path / "service.txt", "base\n")
    initial = await repository.commit_task(
        task_key="BOOTSTRAP",
        title="initialize",
        changed_files=["service.txt"],
        checks=[],
    )

    worktree = await repository.create_worktree("task-42", branch="autodev/task-42")
    task_repository = GitRepository(worktree.path)
    write_text(worktree.path / "service.txt", "base\nfeature\n")
    feature = await task_repository.commit_task(
        task_key="TASK-42",
        title="add feature",
        changed_files=["service.txt"],
        checks=["pytest"],
    )
    await repository.remove_worktree("task-42")
    merged_sha = await repository.merge("autodev/task-42", fast_forward_only=True)
    await repository.tag("v0.1.0")

    assert merged_sha == feature.sha
    assert (repository_path / "service.txt").read_text(encoding="utf-8") == "base\nfeature\n"
    assert await repository.tags() == ["v0.1.0"]
    assert (await repository.status()).clean

    revert_sha = await repository.revert_commit(feature.sha)
    assert revert_sha not in {initial.sha, feature.sha}
    assert (repository_path / "service.txt").read_text(encoding="utf-8") == "base\n"

    clone = await GitRepository.clone(str(repository_path), tmp_path / "clone")
    assert await clone.is_repository()
    assert (await clone.status()).clean


async def test_task_commit_refuses_pre_staged_changes(tmp_path: Path) -> None:
    repository_path = tmp_path / "repo"
    repository_path.mkdir()
    repository = GitRepository(repository_path)
    await repository.initialize()
    write_text(repository_path / "first.txt", "one\n")
    await repository.commit_task(
        task_key="BOOTSTRAP", title="initialize", changed_files=["first.txt"], checks=[]
    )
    write_text(repository_path / "first.txt", "changed\n")
    await repository._run("add", "--", "first.txt")
    write_text(repository_path / "second.txt", "new\n")

    with pytest.raises(GitError, match="unrelated staged changes"):
        await repository.commit_task(
            task_key="TASK-2", title="second", changed_files=["second.txt"], checks=[]
        )


async def test_worktree_name_cannot_escape_managed_root(tmp_path: Path) -> None:
    repository_path = tmp_path / "repo"
    repository_path.mkdir()
    repository = GitRepository(repository_path)
    await repository.initialize()

    with pytest.raises(GitError, match="invalid worktree name"):
        await repository.create_worktree("../escape", branch="autodev/escape")


async def test_conflicting_merge_is_aborted_and_reported(tmp_path: Path) -> None:
    repository_path = tmp_path / "repo"
    repository_path.mkdir()
    repository = GitRepository(repository_path)
    await repository.initialize()
    write_text(repository_path / "shared.txt", "base\n")
    await repository.commit_task(
        task_key="BOOTSTRAP", title="initialize", changed_files=["shared.txt"], checks=[]
    )
    worktree = await repository.create_worktree("conflict", branch="autodev/conflict")
    write_text(repository_path / "shared.txt", "main\n")
    await repository.commit_task(
        task_key="MAIN", title="change main", changed_files=["shared.txt"], checks=[]
    )
    worktree_repository = GitRepository(worktree.path)
    write_text(worktree.path / "shared.txt", "feature\n")
    await worktree_repository.commit_task(
        task_key="FEATURE", title="change feature", changed_files=["shared.txt"], checks=[]
    )
    await repository.remove_worktree("conflict")

    with pytest.raises(GitConflictError) as error:
        await repository.merge("autodev/conflict")

    assert error.value.conflicted_files == ["shared.txt"]
    assert (await repository.status()).clean
    assert (repository_path / "shared.txt").read_text(encoding="utf-8") == "main\n"


async def test_task_commit_blocks_secret_and_restores_clean_index(tmp_path: Path) -> None:
    repository_path = tmp_path / "repo"
    repository_path.mkdir()
    repository = GitRepository(repository_path)
    await repository.initialize()
    write_text(repository_path / "safe.txt", "safe\n")
    await repository.commit_task(
        task_key="BOOTSTRAP", title="initialize", changed_files=["safe.txt"], checks=[]
    )
    write_text(repository_path / ".env", "API_KEY=abcdefghijklmnopqrstuvwx\n")

    with pytest.raises(GitError, match="secret scan blocked"):
        await repository.commit_task(
            task_key="SECRET", title="bad secret", changed_files=[".env"], checks=[]
        )

    _, staged, _ = await repository._run("diff", "--cached", "--name-only")
    assert staged == ""
    assert await repository.changed_files() == [".env"]


async def test_push_to_configured_remote(tmp_path: Path) -> None:
    remote_path = tmp_path / "remote"
    remote_path.mkdir()
    remote = GitRepository(remote_path)
    await remote.initialize()
    await remote._run("config", "receive.denyCurrentBranch", "updateInstead")

    source_path = tmp_path / "source"
    source_path.mkdir()
    source = GitRepository(source_path)
    await source.initialize()
    write_text(source_path / "release.txt", "ready\n")
    commit = await source.commit_task(
        task_key="PUSH",
        title="publish release",
        changed_files=["release.txt"],
        checks=["pytest"],
    )
    await source._run("remote", "add", "origin", str(remote_path))

    await source.push(remote="origin", refspec="HEAD")

    _, remote_sha, _ = await remote._run("rev-parse", "HEAD")
    assert remote_sha.strip() == commit.sha
    assert (remote_path / "release.txt").read_text(encoding="utf-8") == "ready\n"
