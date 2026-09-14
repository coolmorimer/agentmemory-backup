from __future__ import annotations

import json
import shutil
from typing import Annotated

import httpx
import typer

from autodev.config import get_settings

app = typer.Typer(help="AutoDev Orchestrator command line interface")
project_app = typer.Typer(help="Create and control projects")
app.add_typer(project_app, name="project")


def _request(method: str, path: str, *, payload: dict[str, object] | None = None) -> object:
    settings = get_settings()
    try:
        response = httpx.request(
            method,
            f"{settings.api_base_url.rstrip('/')}{path}",
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        typer.echo(f"API request failed: {error}", err=True)
        raise typer.Exit(code=1) from error


def _print(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _ollama_api_available(base_url: str) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/version", timeout=2)
        response.raise_for_status()
    except httpx.HTTPError:
        return False
    return True


@project_app.command("create")
def create_project(
    name: Annotated[str, typer.Option(prompt=True)],
    repository_path: Annotated[str, typer.Option(prompt=True)],
    goal: Annotated[str | None, typer.Option(help="Optional goal to plan immediately")] = None,
    privacy: Annotated[str, typer.Option(help="PUBLIC, PRIVATE, or LOCAL_ONLY")] = "PRIVATE",
    start: Annotated[bool, typer.Option(help="Plan and start when a goal is supplied")] = False,
) -> None:
    project = _request(
        "POST",
        "/api/projects",
        payload={
            "name": name,
            "repository_path": repository_path,
            "privacy_level": privacy.upper(),
        },
    )
    if not isinstance(project, dict) or not isinstance(project.get("id"), str):
        typer.echo("API returned an invalid project", err=True)
        raise typer.Exit(code=1)
    project_id = project["id"]
    if goal:
        _request("POST", f"/api/projects/{project_id}/goals", payload={"prompt": goal})
        _request("POST", f"/api/projects/{project_id}/plan")
        if start:
            project = _request("POST", f"/api/projects/{project_id}/start")
    _print(project)


def _project_action(project_id: str, action: str) -> None:
    _print(_request("POST", f"/api/projects/{project_id}/{action}"))


@project_app.command("start")
def start_project(project_id: str) -> None:
    _project_action(project_id, "start")


@project_app.command("pause")
def pause_project(project_id: str) -> None:
    _project_action(project_id, "pause")


@project_app.command("resume")
def resume_project(project_id: str) -> None:
    _project_action(project_id, "resume")


@app.command()
def status(project_id: str) -> None:
    _print(_request("GET", f"/api/dashboard/projects/{project_id}"))


@app.command()
def tasks(project_id: str) -> None:
    _print(_request("GET", f"/api/projects/{project_id}/tasks"))


@app.command()
def models() -> None:
    _print(_request("GET", "/api/models"))


@app.command()
def providers() -> None:
    _print(_request("GET", "/api/providers"))


@app.command("memory-search")
def memory_search(
    query: str,
    project: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=50)] = 5,
) -> None:
    parameters = httpx.QueryParams(
        {"query": query, "limit": str(limit), **({"project": project} if project else {})}
    )
    _print(_request("GET", f"/api/memory/search?{parameters}"))


@app.command()
def doctor(
    verbose: Annotated[bool, typer.Option(help="Show configured service endpoints")] = False,
) -> None:
    """Check local executable prerequisites without exposing credential values."""
    settings = get_settings()
    required = ("git", "docker", settings.codex_executable)
    failed = False
    for executable in required:
        found = shutil.which(executable)
        typer.echo(f"{executable}: {'ok' if found else 'missing'}")
        failed = failed or found is None
    ollama_executable = shutil.which("ollama")
    ollama_api = _ollama_api_available(settings.ollama_base_url)
    ollama_state = "ok (API)" if ollama_api else (
        "ok (executable)" if ollama_executable else "optional/missing"
    )
    typer.echo(f"ollama: {ollama_state}")
    typer.echo(f"node: {'ok' if shutil.which('node') else 'optional/missing'}")
    if verbose:
        typer.echo(f"PostgreSQL: {settings.database_url.split('@')[-1]}")
        typer.echo(f"Redis: {settings.redis_url}")
        typer.echo(f"Ollama: {settings.ollama_base_url}")
        typer.echo(f"LiteLLM: {settings.litellm_base_url}")
        typer.echo(f"AgentMemory: {settings.agentmemory_base_url}")
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
