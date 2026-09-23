"""Publish read-only status to Telegram.

ADR 0006 stage 1: publish liveness, connection details and the last backup
result to where the group already talks, granting **no authority to anyone**.

**This bot never reads its own inbox.** It calls `sendMessage` and
`editMessageText` and nothing else: no `getUpdates`, no webhook registration,
no command handlers. ADR 0008 records that as a decision rather than an
omission, because it is what makes stage 1 safe by construction instead of by
discipline. A bot that cannot be instructed has no command surface to get
authorization wrong on, nothing to rate limit, and a leaked token buys an
attacker the ability to edit a status message.

Stage 2 will have to add receiving, and at that moment it will also have to add
identity, authorization and an audit trail, which is exactly the coupling ADR
0006 wanted rather than an accident of sequencing.

One message is kept and edited rather than a new one sent each cycle. A status
that scrolls away is a status nobody reads, and a channel full of "still up"
teaches people to mute it, which defeats the point.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hostlab.errors import HostlabError

API = "https://api.telegram.org"
TIMEOUT = 15.0


class PublishFailed(HostlabError):
    """The status could not be published. Never swallowed silently."""


@dataclass(frozen=True)
class Channel:
    """Where to publish, and the note of what was published last."""

    token: str
    chat_id: str
    # Holds only a message id. Gitignored via *.local.json, though nothing
    # secret goes in it: losing it costs one duplicate message, not a secret.
    state_file: Path = Path("telegram.local.json")

    def endpoint(self, method: str) -> str:
        return f"{API}/bot{self.token}/{method}"

    def remembered_message(self) -> int | None:
        if not self.state_file.exists():
            return None
        try:
            stored = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        message_id = stored.get(self.chat_id)
        return int(message_id) if isinstance(message_id, int) else None

    def remember_message(self, message_id: int) -> None:
        stored: dict[str, Any] = {}
        if self.state_file.exists():
            try:
                stored = json.loads(self.state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                stored = {}
        stored[self.chat_id] = message_id
        self.state_file.write_text(json.dumps(stored, indent=2), encoding="utf-8")


def _call(channel: Channel, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310
        channel.endpoint(method),
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            answer: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        message = f"Telegram {method} returned {error.code}: {detail}"
        raise PublishFailed(message) from error
    except urllib.error.URLError as error:
        message = f"Telegram {method} could not be reached: {error.reason}"
        raise PublishFailed(message) from error

    if not answer.get("ok", False):
        message = f"Telegram {method} refused: {answer.get('description', answer)}"
        raise PublishFailed(message)

    return answer


def publish(channel: Channel, text: str) -> int:
    """Edit the standing status message, or start one if there is none.

    Falls back to sending when the edit fails, because the reasons an edit
    fails are all recoverable this way: the message was deleted, the channel
    was cleared, or the note of its id was lost. A status that stops updating
    because of any of those is a status that silently lies.
    """
    message_id = channel.remembered_message()

    if message_id is not None:
        try:
            _call(
                channel,
                "editMessageText",
                {"chat_id": channel.chat_id, "message_id": message_id, "text": text},
            )
        except PublishFailed:
            message_id = None
        else:
            return message_id

    answer = _call(channel, "sendMessage", {"chat_id": channel.chat_id, "text": text})
    new_id = int(answer["result"]["message_id"])
    channel.remember_message(new_id)
    return new_id
