from __future__ import annotations

import json
import sys
from typing import Any


def send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> None:
    thread_id = "thread-test"
    turn_id = "turn-test"
    waiting_for_approval = False
    for line in sys.stdin:
        message = json.loads(line)
        method = message.get("method")
        if method == "initialize":
            if "--die" in sys.argv:
                return
            send(
                {
                    "id": message["id"],
                    "result": {
                        "userAgent": "fake-codex",
                        "platformFamily": "windows",
                        "platformOs": "windows",
                        "codexHome": "C:/fake",
                    },
                }
            )
        elif method == "thread/start" or method == "thread/resume":
            send({"id": message["id"], "result": {"thread": {"id": thread_id}}})
        elif method == "turn/start":
            send(
                {
                    "id": message["id"],
                    "result": {"turn": {"id": turn_id, "status": "inProgress", "items": []}},
                }
            )
            waiting_for_approval = True
            send(
                {
                    "id": "approval-1",
                    "method": "item/commandExecution/requestApproval",
                    "params": {"command": ["python", "-m", "pytest"]},
                }
            )
        elif waiting_for_approval and message.get("id") == "approval-1":
            waiting_for_approval = False
            accepted = message.get("result", {}).get("decision") == "accept"
            if accepted:
                send(
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": thread_id,
                            "turnId": turn_id,
                            "completedAtMs": 1,
                            "item": {
                                "id": "file-1",
                                "type": "fileChange",
                                "status": "completed",
                                "changes": [{"path": "todo.py", "kind": "update", "diff": "+tags"}],
                            },
                        },
                    }
                )
                send(
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": thread_id,
                            "turnId": turn_id,
                            "completedAtMs": 2,
                            "item": {
                                "id": "message-1",
                                "type": "agentMessage",
                                "text": "Implemented tags.",
                            },
                        },
                    }
                )
            send(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": thread_id,
                        "turn": {
                            "id": turn_id,
                            "status": "completed" if accepted else "failed",
                            "items": [],
                            "error": None if accepted else {"message": "approval declined"},
                        },
                    },
                }
            )


if __name__ == "__main__":
    main()
