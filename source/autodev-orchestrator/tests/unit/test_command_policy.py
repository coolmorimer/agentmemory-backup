import pytest

from autodev.security.command_policy import CommandCategory, CommandPolicy


@pytest.mark.parametrize(
    ("command", "category"),
    [
        (["rg", "TODO"], CommandCategory.READ_ONLY),
        (["python", "-m", "pytest", "-q"], CommandCategory.TEST),
        (["uv", "run", "ruff", "check", "."], CommandCategory.TEST),
        (["git", "status"], CommandCategory.GIT_SAFE),
        (["git", "commit", "-m", "x"], CommandCategory.GIT_WRITE),
        (["rm", "-rf", "data"], CommandCategory.DESTRUCTIVE),
        (["unknown-tool"], CommandCategory.UNKNOWN),
    ],
)
def test_command_classification(command: list[str], category: CommandCategory) -> None:
    assert CommandPolicy().classify(command) is category


def test_check_policy_rejects_git_write_and_destructive_commands() -> None:
    policy = CommandPolicy()

    assert policy.permits_check(["python", "-m", "pytest"]) is True
    assert policy.permits_check(["git", "commit"]) is False
    assert policy.permits_check(["rm", "-rf", "data"]) is False
