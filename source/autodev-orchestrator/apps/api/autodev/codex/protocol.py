from __future__ import annotations

from typing import Any, Protocol

JsonObject = dict[str, Any]


class AppServerError(RuntimeError):
    """Base error for the Codex App Server transport."""


class AppServerProcessError(AppServerError):
    """The child process exited or its transport closed unexpectedly."""


class AppServerTimeout(AppServerError):
    """A request or turn exceeded its configured deadline."""


class JsonRpcError(AppServerError):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"Codex App Server error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class ServerRequestHandler(Protocol):
    async def handle(self, method: str, params: JsonObject) -> JsonObject: ...
