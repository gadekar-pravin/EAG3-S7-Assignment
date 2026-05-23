"""Tests for the EAGV3 S6 MCP server. Run: pytest -v test_mcp_server.py"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).parent
SERVER = HERE / "mcp_server.py"
SANDBOX = HERE / "sandbox"
TEST_DIR_NAME = "_test_tools"
TEST_DIR = SANDBOX / TEST_DIR_NAME


def _result(res) -> Any:
    """Extract a structured payload from a CallToolResult."""
    if getattr(res, "structuredContent", None) is not None:
        sc = res.structuredContent
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    block = res.content[0]
    text = getattr(block, "text", None)
    if text is None:
        return block
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _clean_test_dir() -> None:
    SANDBOX.mkdir(exist_ok=True)
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir()


def _test_path(name: str) -> str:
    return f"{TEST_DIR_NAME}/{name}"


async def _call_tool(name: str, arguments: dict) -> Any:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            return await s.call_tool(name, arguments=arguments)


@pytest.mark.network
@pytest.mark.asyncio
async def test_web_search():
    res = await _call_tool("web_search", {"query": "python asyncio", "max_results": 3})
    data = _result(res)
    print("web_search:", data)
    assert isinstance(data, list)
    assert len(data) >= 1
    for hit in data:
        assert {"title", "url", "snippet"} <= set(hit)


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_url():
    res = await _call_tool("fetch_url", {"url": "https://example.com"})
    data = _result(res)
    print("fetch_url status/len:", data["status"], data["length_bytes"])
    assert data["status"] == 200
    assert "Example Domain" in data["text"]
    assert data["length_bytes"] > 0
    assert "text" in data["content_type"].lower() or "html" in data["content_type"].lower()


@pytest.mark.asyncio
async def test_get_time():
    res = await _call_tool("get_time", {"timezone": "Asia/Kolkata"})
    data = _result(res)
    print("get_time:", data)
    assert data["timezone"] == "Asia/Kolkata"
    assert data["offset_hours"] == 5.5
    assert "T" in data["iso"]
    assert data["human"]


@pytest.mark.network
@pytest.mark.asyncio
async def test_currency_convert():
    res = await _call_tool(
        "currency_convert", {"amount": 100, "from_currency": "usd", "to_currency": "eur"}
    )
    data = _result(res)
    print("currency_convert:", data)
    assert data["from"] == "USD"
    assert data["to"] == "EUR"
    assert data["amount"] == 100
    assert data["source"] == "frankfurter.dev"
    assert data["converted"] > 0
    assert data["rate"] > 0


@pytest.mark.asyncio
async def test_read_file():
    _clean_test_dir()
    (TEST_DIR / "hello.txt").write_text("hello world", encoding="utf-8")
    res = await _call_tool("read_file", {"path": _test_path("hello.txt")})
    data = _result(res)
    print("read_file:", data)
    assert data["content"] == "hello world"
    assert data["encoding"] == "utf-8"
    assert data["size_bytes"] == 11
    assert data["path"] == _test_path("hello.txt")


@pytest.mark.asyncio
async def test_list_dir():
    _clean_test_dir()
    (TEST_DIR / "a.txt").write_text("a", encoding="utf-8")
    (TEST_DIR / "sub").mkdir()
    res = await _call_tool("list_dir", {"path": TEST_DIR_NAME})
    data = _result(res)
    print("list_dir:", data)
    assert isinstance(data, dict)
    assert data["count"] == 2
    names = {e["name"]: e for e in data["entries"]}
    assert names["a.txt"]["type"] == "file"
    assert names["a.txt"]["size_bytes"] == 1
    assert names["sub"]["type"] == "dir"
    assert names["sub"]["size_bytes"] == 0


@pytest.mark.asyncio
async def test_create_file():
    _clean_test_dir()
    res = await _call_tool(
        "create_file",
        {"path": _test_path("new.txt"), "content": "fresh"},
    )
    data = _result(res)
    print("create_file:", data)
    assert data["ok"] is True
    assert data["size_bytes"] == 5
    assert (TEST_DIR / "new.txt").read_text(encoding="utf-8") == "fresh"

    dup = await _call_tool("create_file", {"path": _test_path("new.txt"), "content": "x"})
    assert dup.isError, "second create on same path must error"
    print("create_file dup error:", dup.content[0].text if dup.content else "")


@pytest.mark.asyncio
async def test_update_file():
    _clean_test_dir()
    (TEST_DIR / "u.txt").write_text("old", encoding="utf-8")
    res = await _call_tool(
        "update_file",
        {"path": _test_path("u.txt"), "content": "brand new body"},
    )
    data = _result(res)
    print("update_file:", data)
    assert data["ok"] is True
    assert (TEST_DIR / "u.txt").read_text(encoding="utf-8") == "brand new body"
    assert data["size_bytes"] == len("brand new body")

    missing = await _call_tool(
        "update_file",
        {"path": _test_path("nope.txt"), "content": "x"},
    )
    assert missing.isError
    print("update_file missing error:", missing.content[0].text if missing.content else "")


@pytest.mark.asyncio
async def test_edit_file():
    _clean_test_dir()
    (TEST_DIR / "e.txt").write_text("foo bar foo", encoding="utf-8")

    multi = await _call_tool(
        "edit_file", {"path": _test_path("e.txt"), "find": "foo", "replace": "FOO"}
    )
    assert multi.isError, "ambiguous find without replace_all must error"
    print("edit_file ambiguous error:", multi.content[0].text if multi.content else "")

    res_all = await _call_tool(
        "edit_file",
        {"path": _test_path("e.txt"), "find": "foo", "replace": "FOO", "replace_all": True},
    )
    data = _result(res_all)
    print("edit_file replace_all:", data)
    assert data["replacements"] == 2
    assert (TEST_DIR / "e.txt").read_text(encoding="utf-8") == "FOO bar FOO"

    res_single = await _call_tool(
        "edit_file", {"path": _test_path("e.txt"), "find": "bar", "replace": "BAZ"}
    )
    data = _result(res_single)
    print("edit_file single:", data)
    assert data["replacements"] == 1
    assert (TEST_DIR / "e.txt").read_text(encoding="utf-8") == "FOO BAZ FOO"

    missing = await _call_tool(
        "edit_file", {"path": _test_path("e.txt"), "find": "zzz", "replace": "x"}
    )
    assert missing.isError
    print("edit_file not-found error:", missing.content[0].text if missing.content else "")


@pytest.mark.asyncio
async def test_sandbox_escape():
    res = await _call_tool("read_file", {"path": "../foo"})
    assert res.isError, "sandbox escape must be rejected"
    msg = res.content[0].text if res.content else ""
    print("sandbox_escape error:", msg)
    assert "escape" in msg.lower() or "sandbox" in msg.lower()


def test_perception_system_has_no_mcp_tool_names():
    import perception

    tool_names = {
        "web_search",
        "fetch_url",
        "get_time",
        "currency_convert",
        "read_file",
        "list_dir",
        "create_file",
        "update_file",
        "edit_file",
        "index_document",
        "search_knowledge",
    }
    system = perception.SYSTEM
    leaked = sorted(name for name in tool_names if name in system)
    assert leaked == []


def test_court_rag_parses_metadata_and_chunks():
    import court_rag

    opinion = court_rag.parse_opinion(SANDBOX / "court_opinions" / "cl_10319961.txt")
    assert opinion.case == "State v. Robert X. Geter"
    assert opinion.court == "Supreme Court of South Carolina"
    assert opinion.date_filed == "2025-01-23"

    chunks = court_rag.chunk_words("one two three four five", size=3, overlap=1)
    assert chunks == ["one two three", "three four five"]


def test_court_rag_status_and_no_index_response(tmp_path):
    import court_rag

    corpus_dir = tmp_path / "corpus"
    store_dir = tmp_path / "store"
    corpus_dir.mkdir()
    (corpus_dir / "case.txt").write_text(
        "Case: Tiny Case\nCourt: Test Court\nDate Filed: 2026-01-01\n"
        "Citations: 1 Test 2\nURL: https://example.test\nSource Query: test\n\n"
        "Alpha facts about an appeal.",
        encoding="utf-8",
    )

    status = court_rag.get_status(corpus_dir=corpus_dir, store_dir=store_dir)
    assert status["indexed"] is False
    assert status["document_count"] == 1
    assert status["chunk_count"] == 0

    result = court_rag.answer_question("What happened?", use_index=False, store_dir=store_dir)
    assert result.status == "no_index_context"
    assert result.sources == []
    assert "No answer" in result.answer


def test_court_rag_retrieves_with_mock_embeddings(tmp_path):
    import court_rag

    corpus_dir = tmp_path / "corpus"
    store_dir = tmp_path / "store"
    corpus_dir.mkdir()
    (corpus_dir / "alpha.txt").write_text(
        "Case: Alpha v. State\nCourt: Test Court\nDate Filed: 2026-01-01\n"
        "Citations: 10 Test 20\nURL: https://example.test/alpha\nSource Query: test\n\n"
        "Alpha topic says transferred intent is unavailable for attempted murder.",
        encoding="utf-8",
    )
    (corpus_dir / "beta.txt").write_text(
        "Case: Beta v. State\nCourt: Test Court\nDate Filed: 2026-01-02\n"
        "Citations: 11 Test 21\nURL: https://example.test/beta\nSource Query: test\n\n"
        "Beta topic concerns workers compensation and workplace trauma.",
        encoding="utf-8",
    )

    def fake_embed(text: str, task_type: str) -> list[float]:
        del task_type
        lower = text.lower()
        return [
            1.0 if "alpha" in lower or "attempted murder" in lower else 0.0,
            1.0 if "beta" in lower or "workers compensation" in lower else 0.0,
            1.0,
        ]

    stats = court_rag.build_index(
        corpus_dir=corpus_dir,
        store_dir=store_dir,
        embedder=fake_embed,
        chunk_size=80,
        overlap=10,
    )
    assert stats.document_count == 2
    assert stats.chunk_count == 2

    result = court_rag.answer_question(
        "What does alpha say about attempted murder?",
        store_dir=store_dir,
        embedder=fake_embed,
        answer_generator=lambda query, chunks: f"{query}: {chunks[0].case}",
        top_k=1,
    )
    assert result.status == "answered"
    assert result.sources[0]["source_path"] == "alpha.txt"
    assert "Alpha v. State" in result.answer


@pytest.mark.embed
def test_court_rag_live_embedding_path(tmp_path):
    import court_rag
    from gateway import ensure_gateway

    try:
        ensure_gateway()
    except RuntimeError as exc:
        pytest.skip(str(exc))

    corpus_dir = tmp_path / "corpus"
    store_dir = tmp_path / "store"
    corpus_dir.mkdir()
    (corpus_dir / "live.txt").write_text(
        "Case: Live v. Gateway\nCourt: Test Court\nDate Filed: 2026-01-03\n"
        "Citations: 12 Test 22\nURL: https://example.test/live\nSource Query: test\n\n"
        "The live embedding path indexes this opinion for retrieval.",
        encoding="utf-8",
    )

    stats = court_rag.build_index(corpus_dir=corpus_dir, store_dir=store_dir)
    assert stats.chunk_count == 1

    result = court_rag.answer_question(
        "What does the live gateway document say?",
        store_dir=store_dir,
        answer_generator=lambda query, chunks: f"{query}: {chunks[0].case}",
        top_k=1,
    )
    assert result.status == "answered"
    assert result.sources[0]["source_path"] == "live.txt"
