y# EAGV3 Session 7 Agent

Session 7 agent for the EAG3 course: the Session 6 cognitive architecture plus FAISS-backed vector memory and document indexing tools.

## Architecture

The agent runs a four-layer loop with typed Pydantic contracts (`schemas.py`) between every layer:

```
Memory.read --> Perception.observe --> Decision.next_step --> Action.execute --> Memory.record_outcome
```

| Layer | Module | Role |
|---|---|---|
| **Perception** | `perception.py` | Decomposes the user query into goals, tracks which are done, decides when to attach artifact bytes |
| **Decision** | `decision.py` | Given the current goal plus memory hits, either answers in plain text or calls exactly one MCP tool |
| **Action** | `action.py` | Pure MCP dispatch -- no LLM. Large results (>4 KB) go to the artifact store; only a short descriptor enters memory |
| **Memory** | `memory.py` | Vector search (FAISS) first, keyword overlap as fallback. Writes embed descriptors at insert time |

The loop runs up to 20 iterations (`MAX_ITERATIONS` in `agent7.py`). Each goal is processed one at a time in order; the loop exits when all goals are marked done.

## Project Structure

| File | Description |
|---|---|
| `agent7.py` | Entry point and orchestrator loop |
| `perception.py` | Goal decomposition and artifact-attachment logic |
| `decision.py` | Tool selection or direct-answer LLM call |
| `action.py` | MCP tool dispatch and artifact threshold (4 KB) |
| `memory.py` | Vector + keyword retrieval, LLM-classified writes, FAISS integration |
| `schemas.py` | Pydantic models: `MemoryItem`, `Goal`, `Observation`, `DecisionOutput`, `ToolCall`, `Artifact` |
| `gateway.py` | Bridge to LLM Gateway V7 -- health check, `embed()` helper |
| `llm_client.py` | Vendored HTTP client for the gateway (`chat`, `stream`, `embed`) |
| `vector_index.py` | FAISS `IndexFlatIP` wrapper with disk persistence (`state/index.faiss`) |
| `artifacts.py` | Content-addressable (SHA-256) byte store under `state/artifacts/` |
| `mcp_server.py` | FastMCP server exposing 11 tools over stdio |
| `test_mcp_server.py` | pytest suite for the MCP tools |

## MCP Tools

| Tool | Description |
|---|---|
| `web_search` | Tavily primary, DuckDuckGo fallback. Hard-capped at 5 results |
| `fetch_url` | Headless Chromium via crawl4ai, returns clean markdown |
| `get_time` | Current time in any IANA timezone |
| `currency_convert` | ISO-3 currency conversion via frankfurter.dev |
| `read_file` | Read a UTF-8 file from the `sandbox/` directory |
| `list_dir` | List a directory inside `sandbox/` |
| `create_file` | Create a new file in `sandbox/` (errors if it exists) |
| `update_file` | Overwrite an existing `sandbox/` file |
| `edit_file` | Find-and-replace inside a `sandbox/` file |
| `index_document` | Chunk a sandbox file or artifact and write each chunk as a searchable `fact` in Memory |
| `search_knowledge` | Vector search over indexed `fact` chunks |

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- **LLM Gateway V7** running separately (default `http://localhost:8107`, override with `LLM_GATEWAY_V7_URL`)
- Tavily API key (optional -- web search falls back to DuckDuckGo without it)

## Setup and Run

```bash
# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env and set TAVILY_API_KEY (optional)

# Start the LLM Gateway V7 in a separate terminal
cd ../llm_gatewayV7 && uv run main.py

# Run the agent
uv run agent7.py "What is the current time in Asia/Tokyo and Asia/Kolkata?"
```

If no query is provided, the agent uses a default query about time differences between Tokyo and Kolkata.

## Testing

```bash
# Run all tests (some require network / gateway)
uv run pytest -v test_mcp_server.py

# Skip tests that need internet access
uv run pytest -v test_mcp_server.py -m "not network"

# Skip tests that need the embedding endpoint
uv run pytest -v test_mcp_server.py -m "not embed"
```

## LLM Routing

The agent delegates all LLM calls to **LLM Gateway V7** (`../llm_gatewayV7`), which provides multi-provider routing with automatic failover. The gateway runs two independent pools:

| Pool | Purpose | Providers | Models |
|---|---|---|---|
| **Router pool** | Classifies each request as TINY / LARGE / HUGE | cerebras, groq, nvidia, github | Small/fast (llama3.1-8b, Phi-4-mini, etc.) |
| **Worker pool** | Executes the actual LLM call | gemini, nvidia, groq, cerebras, openrouter, github, ollama | Large (gemini-2.5-flash, deepseek-v3.2, etc.) |

### How routing works

1. The agent tags each call with `auto_route` (e.g. `"perception"`, `"decision"`, `"memory"`)
2. The gateway sends a bounded sample (token count + 800-char head/tail) to a router-pool LLM
3. The router classifies the request as **TINY**, **LARGE**, or **HUGE** (single word)
4. The gateway picks a worker from the tier-specific failover order:
   - **TINY**: github → openrouter → groq → nvidia → cerebras → gemini → ollama
   - **LARGE**: gemini → groq → nvidia → cerebras → github → openrouter → ollama
   - **HUGE**: rejected with 503 -- caller must chunk the input
5. If `provider` is set explicitly (e.g. `provider="g"`), routing is bypassed entirely

### Per-layer settings

| Layer | `auto_route` | `provider` | `temperature` | Notes |
|---|---|---|---|---|
| Perception | `"perception"` | `"g"` (Gemini) | 1.0 | JSON-schema structured output for goal decomposition |
| Decision | `"decision"` | gateway default | 0 | Tool-use mode (`tool_choice="auto"`), system prompt caching enabled |
| Memory classifier | `"memory"` | `"g"` (Gemini) | 1.0 | JSON-schema structured output for classifying free-form content |
| Embedding | -- | gateway default | -- | Separate `POST /v1/embed` endpoint; Ollama (nomic-embed-text) with Gemini fallback, both 768-dim |

Perception and Memory pin `provider="g"` for cost-efficient structured outputs, bypassing the router. Decision omits the provider, so the gateway's router classifies it and picks the best available worker. The pools have independent rate state -- router calls never starve worker calls even when they share the same upstream API key.

## Key Design Decisions

- **Vector-only retrieval with keyword fallback.** Memory tries FAISS cosine similarity first; if the vector path returns nothing (no embeddings yet, gateway down), it falls back to the Session 6 keyword-overlap scorer. Hybrid retrieval with RRF is planned for a future session.
- **Sliding-window chunking.** `index_document` splits text into 400-word windows with 80-word overlap. Semantic chunking arrives in Session 8.
- **Fixed embedding model.** The embedding model is set at the gateway level. Changing it invalidates every FAISS index already built -- treat it as a project-level constant.
- **Artifact threshold at 4 KB.** Tool outputs larger than 4 KB are written to the content-addressable artifact store. Decision only sees full bytes when Perception explicitly attaches them to a goal.
- **Stateless layers.** Perception, Decision, and Action are pure functions of their inputs. All durable state lives in Memory (`state/memory.json`) and the artifact store (`state/artifacts/`).
- **Sandbox isolation.** File tools (`read_file`, `create_file`, etc.) are restricted to the `sandbox/` directory via path validation.
