from pathlib import Path

from autodev.qa.discovery import CheckDiscovery


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discovers_configured_python_and_javascript_checks(tmp_path: Path) -> None:
    write_text(
        tmp_path / "pyproject.toml",
        "[dependency-groups]\ndev = ['pytest', 'ruff', 'mypy']\n[tool.mypy]\nstrict = true\n",
    )
    write_text(tmp_path / "uv.lock", "version = 1\n")
    write_text(tmp_path / "tests" / "test_ok.py", "def test_ok(): assert True\n")
    write_text(
        tmp_path / "package.json",
        '{"scripts":{"lint":"eslint .","test":"vitest","build":"vite build"}}',
    )

    plan = CheckDiscovery(tmp_path).discover()

    assert plan.commands == [
        ["uv", "run", "pytest", "-q"],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "mypy", "."],
        ["uv", "lock", "--check"],
        ["npm", "run", "lint"],
        ["npm", "run", "test"],
        ["npm", "run", "build"],
    ]
