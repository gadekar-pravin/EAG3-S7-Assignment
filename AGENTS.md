# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Python AI agent with a four-layer cognitive architecture (Memory → Perception → Decision → Action) for EAG3 Session 7. Each layer has typed Pydantic contracts in `schemas.py`.

## Commands

```bash
uv sync                                        # install deps
uv run agent7.py "query"                       # run agent (gateway must be running)
uv run pytest -v test_mcp_server.py            # all tests
uv run pytest -v test_mcp_server.py -m "not network"  # skip internet tests
uv run pytest -v test_mcp_server.py -m "not embed"    # skip embedding tests
uv run ruff check .                                    # lint
uv run ruff format .                                   # format
```

## Prerequisites

- LLM Gateway V7 must be running at `localhost:8107` before starting the agent (lives in `../llm_gatewayV7`)
- Optional: set `TAVILY_API_KEY` in `.env` for premium web search (falls back to DuckDuckGo)

## Architecture Rules

- Layers are pure functions with typed I/O — only Memory holds durable state
- Perception never drops prior goals; only appends or marks done
- Decision picks a tool or produces a direct answer — no other logic
- Action is stateless: dispatches MCP tools, stores large results (>4KB) as artifacts
- Tool outcomes bypass the LLM classifier; they go directly to `record_outcome()`
- Artifacts are immutable (SHA-256 content-addressed)

## Code Conventions

- Use `uv` exclusively (never `pip`)
- Full type hints throughout; Pydantic BaseModel for all inter-layer contracts
- `from __future__ import annotations` at top of every module
- File tools are sandboxed to `./sandbox/` — `_safe()` validates paths
- Perception uses `provider="g"` (Gemini); Decision uses default gateway router with `cache_system=True`
- Test markers: `@pytest.mark.network` and `@pytest.mark.embed` for conditional skipping
