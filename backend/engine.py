"""The ask path: a question becomes rules, a run and an explanation.

    question -> agent.spec (the model writes a spec; validated; two repairs; or a refusal)
             -> model.run  (the engine, on the snapshot in SNAPSHOT_DIR)
             -> agent.claims (the model explains; it cannot write a number)

The language model is reached through one function, `get_provider()`. The API key is read
from the environment here and nowhere else; it never reaches the browser, a log or a
response. With no key the path answers 503 and says why. A result is also written to
SIGNALS_PATH, so `/api/engine/signals` and the `/run` screen show the latest run.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # model/ and agent/ sit beside backend/, not inside it
    sys.path.insert(0, str(ROOT))

from agent.claims import result_to_claims  # noqa: E402
from agent.spec import question_to_spec  # noqa: E402
from model import store  # noqa: E402
from model.run import run  # noqa: E402

MAX_QUESTION = 500
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-5-5"  # a cheap default; ENGINE_MODEL overrides it, the eval measures it

Provider = Callable[[list[dict]], str]


class NotConfigured(Exception):
    """The path cannot answer yet: no key, no snapshot, or a missing library."""


class ProviderError(Exception):
    """The model service failed. The message never carries the key or the request."""


def _lock_factory() -> threading.Lock:
    return threading.Lock()


_RUN_LOCK = _lock_factory()  # one run at a time: a run holds the whole snapshot's working set
_snapshot_cache: dict[str, object] = {}


def get_snapshot():
    directory = Path(os.getenv("SNAPSHOT_DIR", ROOT / "data" / "raw" / "csi300"))
    if str(directory) not in _snapshot_cache:
        try:
            _snapshot_cache[str(directory)] = store.load(directory)
        except (OSError, ValueError, KeyError) as exc:
            raise NotConfigured(f"no usable snapshot at {directory}: {exc.__class__.__name__}") from exc
    return _snapshot_cache[str(directory)]


def get_provider() -> Provider:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise NotConfigured("ANTHROPIC_API_KEY is not set")
    model = os.getenv("ENGINE_MODEL", DEFAULT_MODEL)

    def complete(messages: list[dict]) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        chat = [m for m in messages if m["role"] != "system"]
        try:
            response = httpx.post(
                ANTHROPIC_URL,
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": 2000, "system": system, "messages": chat},
                timeout=60,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"model service unreachable: {exc.__class__.__name__}") from None
        if response.status_code != 200:
            raise ProviderError(f"model service answered {response.status_code}")
        return "".join(b.get("text", "") for b in response.json().get("content", []) if b.get("type") == "text")

    return complete


def _write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def check_question(question: str) -> str:
    """The question, trimmed; a bad request is refused before the server's own setup is looked at."""
    question = question.strip()
    if not question or len(question) > MAX_QUESTION:
        raise ValueError(f"the question must be 1 to {MAX_QUESTION} characters")
    return question


def answer(question: str, signals_path: Path) -> dict:
    """`ask` with the real provider and snapshot; everything that can block runs in one call."""
    question = check_question(question)
    return ask(question, get_provider(), get_snapshot(), signals_path)


def ask(question: str, provider: Provider, snapshot, signals_path: Path, now: datetime | None = None) -> dict:
    """One question. Returns {"refusal": rule}, {"problems": [...]} or {"result", "claims", ...}."""
    question = check_question(question)
    now = now or datetime.now(timezone.utc)
    with _RUN_LOCK:
        outcome = question_to_spec(
            question, provider, {snapshot.universe: snapshot.market}, now.date().isoformat()
        )
        if outcome.refusal:
            return {"refusal": outcome.refusal}
        if not outcome.ok:
            return {"problems": outcome.problems}
        result = run(outcome.spec, snapshot, question, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        _write_atomically(signals_path, json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        reply: dict = {"result": result, "claims": [], "dropped": 0}
        try:
            claims = result_to_claims(result, provider)
            reply["claims"], reply["dropped"] = claims.claims, len(claims.dropped)
        except ProviderError as exc:  # the run stands; only the explanation failed
            reply["claims_error"] = str(exc)
        return reply
