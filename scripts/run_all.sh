#!/usr/bin/env bash
set -uo pipefail

# ── Prerequisites ──────────────────────────────────────────────────────
GATEWAY_URL="http://localhost:8107/health"
if ! curl -sf "$GATEWAY_URL" > /dev/null 2>&1; then
    echo "ERROR: LLM Gateway V7 is not reachable at $GATEWAY_URL"
    echo "Start it first:  cd ../llm_gatewayV7 && uv run python gateway.py"
    exit 1
fi
echo "Gateway OK at $GATEWAY_URL"

# Verify paper fixtures exist (needed by tests 5-6).
if [ ! -d sandbox/papers ] || [ -z "$(ls sandbox/papers/*.md 2>/dev/null)" ]; then
    echo "ERROR: sandbox/papers/*.md not found — tests 5-6 will fail."
    echo "Restore the papers directory before running."
    exit 1
fi

# ── Test runner ────────────────────────────────────────────────────────
PASS=0
FAIL=0
TOTAL=0
FAILED_TESTS=""

run_test() {
    local label="$1"
    shift
    TOTAL=$((TOTAL + 1))
    echo ""
    echo "══════════════════════════════════════════════════════════════"
    echo "TEST $TOTAL: $label"
    echo "══════════════════════════════════════════════════════════════"
    if "$@"; then
        PASS=$((PASS + 1))
        echo "  ✓ PASS: $label"
    else
        FAIL=$((FAIL + 1))
        FAILED_TESTS="$FAILED_TESTS\n  - $label"
        echo "  ✗ FAIL: $label"
    fi
}

# ── Tests ──────────────────────────────────────────────────────────────

run_test "Web fetch (Claude Shannon)" \
    uv run python agent7.py --clean "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."

run_test "Multi-tool (Tokyo weekend)" \
    uv run python agent7.py --clean "Find 3 family-friendly things to do in Tokyo this weekend. Check Saturday's weather forecast there and tell me which one is most appropriate."

run_test "Memory store (mom's birthday)" \
    uv run python agent7.py --clean "My mom's birthday is 15 May 2026. Remember that and give me a calendar reminder for two weeks before and on the day."

run_test "Memory recall (mom's birthday)" \
    uv run python agent7.py "When is mom's birthday?"

run_test "Web search (asyncio best practices)" \
    uv run python agent7.py --clean "Search for 'Python asyncio best practices', read the top 3 results, and give me a short numbered list of the advice they agree on."

run_test "Single doc index (attention.md)" \
    uv run python agent7.py "Index the file papers/attention.md and tell me what the three key contributions of the Transformer architecture are according to this paper"

run_test "Bulk index (all papers)" \
    uv run python agent7.py "Index every .md file under papers/. Confirm how many chunks were indexed in total."

run_test "Knowledge search (chain-of-thought)" \
    uv run python agent7.py "Across the papers I have indexed, what do they say about chain-of-thought reasoning?"

run_test "Semantic search (credit assignment)" \
    uv run python agent7.py "Across these papers, how do they handle the credit assignment problem?"

run_test "Cross-doc comparison (ReAct vs CoT)" \
    uv run python agent7.py "Compare how the ReAct paper and the Chain-of-Thought paper differ in their treatment of intermediate reasoning"

# ── Summary ────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════"
echo "RESULTS: $PASS passed, $FAIL failed, $TOTAL total"
if [ "$FAIL" -gt 0 ]; then
    echo -e "Failed tests:$FAILED_TESTS"
    echo "══════════════════════════════════════════════════════════════"
    exit 1
else
    echo "All tests passed."
    echo "══════════════════════════════════════════════════════════════"
fi
