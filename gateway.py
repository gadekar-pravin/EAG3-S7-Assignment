"""Bridge to llm_gatewayV7.

V7 is V3 plus a single new endpoint, `POST /v1/embed`. The session-version
mapping (V7 for Session 7) lets us evolve the gateway forward without
touching prior versions. V3 remains available for Session 6 agents.

Checks that the gateway is reachable, then re-exports the V7 `LLM` client
and a module-level `embed()` helper. Every layer in this agent imports from
here so the health-check logic lives in one place.

The gateway is a separate long-lived service. Start it manually before
running the agent::

    cd /path/to/llm_gatewayV7 && uv run main.py

Set ``LLM_GATEWAY_V7_URL`` to override the default ``http://localhost:8107``.
"""

from __future__ import annotations

import os

import httpx

from llm_client import LLM  # vendored copy of llm_gatewayV7/client.py

GATEWAY_URL = os.getenv("LLM_GATEWAY_V7_URL", "http://localhost:8107")


def _is_up() -> bool:
    try:
        httpx.get(f"{GATEWAY_URL}/v1/routers", timeout=2.0)
        return True
    except Exception:
        return False


def ensure_gateway() -> None:
    """Verify the gateway is reachable; raise with instructions if not."""
    if _is_up():
        return
    raise RuntimeError(
        f"LLM Gateway V7 is not running at {GATEWAY_URL}.\n"
        "Start it manually:\n"
        "    cd /path/to/llm_gatewayV7 && uv run main.py\n"
        "Or set LLM_GATEWAY_V7_URL to point to an already-running instance."
    )


def embed(text: str, task_type: str = "retrieval_document") -> dict:
    """Compute an embedding for `text` via the gateway's V7 embed endpoint.

    Returns the full response dict: `{embedding, dim, model, provider,
    latency_ms, ...}`. The chosen embedding model is fixed at the gateway
    level. Changing it invalidates every FAISS index built against the old
    vectors, so callers should treat the model as a project-level constant.
    """
    ensure_gateway()
    return LLM(base_url=GATEWAY_URL).embed(text, task_type=task_type)


__all__ = ["ensure_gateway", "LLM", "GATEWAY_URL", "embed"]
