#!/usr/bin/env bash
set -uo pipefail

# ── Colors (disabled when piped or NO_COLOR is set) ──────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    CYAN='\033[0;36m'
    YELLOW='\033[0;33m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    GREEN='' RED='' CYAN='' YELLOW='' BOLD='' RESET=''
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Prerequisites ────────────────────────────────────────────────────
GATEWAY_URL="http://localhost:8107/v1/status"
if ! curl -sf "$GATEWAY_URL" > /dev/null 2>&1; then
    echo "ERROR: LLM Gateway V7 is not reachable at $GATEWAY_URL"
    echo "Start it first:  cd ../llm_gatewayV7 && uv run python gateway.py"
    exit 1
fi
echo -e "${GREEN}Gateway OK${RESET} at $GATEWAY_URL"

if ! command -v jq > /dev/null 2>&1; then
    echo "ERROR: jq is required but not found. Install it: brew install jq"
    exit 1
fi

QUERIES_FILE="$PROJECT_ROOT/rag_queries.json"
if [ ! -f "$QUERIES_FILE" ]; then
    echo "ERROR: $QUERIES_FILE not found."
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/state/index.faiss" ]; then
    echo "ERROR: state/index.faiss not found — the agent's main vector index is missing."
    echo "Build it first:  uv run python scripts/index_corpus.py"
    exit 1
fi

# ── Intro banner ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  RAG Comparison Demo — Two-Phase Answer Quality Test${RESET}"
echo -e "${BOLD}══════════════════════════════════════════════════════════════${RESET}"
echo -e "${YELLOW}  This script demonstrates the impact of vector-indexed RAG on"
echo -e "  answer quality. It runs the same court-opinion queries twice:${RESET}"
echo ""
echo -e "${YELLOW}    Phase 1 (Without RAG): The agent's vector index is removed,"
echo -e "      so it has no indexed court-opinion knowledge. Answers rely"
echo -e "      on general knowledge or web search alone.${RESET}"
echo ""
echo -e "${YELLOW}    Phase 2 (With RAG): The vector index is restored with all"
echo -e "      indexed court-opinion chunks. The agent can retrieve relevant"
echo -e "      passages via cosine similarity for precise answers.${RESET}"
echo ""
echo -e "${YELLOW}  Each answer is checked against keyword anchors that should"
echo -e "  appear in a correct, grounded response.${RESET}"
echo -e "${BOLD}══════════════════════════════════════════════════════════════${RESET}"
echo ""

# ── Setup ────────────────────────────────────────────────────────────
QUERY_COUNT=$(jq '.queries | length' "$QUERIES_FILE")
WORK_DIR=$(mktemp -d)
START_TIME=$(date +%s)

PHASE1_PASS=0
PHASE1_FAIL=0
PHASE2_PASS=0
PHASE2_FAIL=0
PHASE1_RESULTS=()
PHASE2_RESULTS=()

# Cleanup trap: MUST restore state/ from backup on any exit
cleanup() {
    if [ -d "$WORK_DIR/state_backup" ]; then
        rm -rf "$PROJECT_ROOT/state"
        mv "$WORK_DIR/state_backup" "$PROJECT_ROOT/state"
        echo -e "  ${YELLOW}[cleanup] Restored state/ from backup${RESET}"
    fi
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

# ── run_rag_test() ───────────────────────────────────────────────────
# Args: $1=json_index  $2=phase_label ("phase1"/"phase2")  $3=test_number
run_rag_test() {
    local idx="$1"
    local phase="$2"
    local test_num="$3"

    local qid query
    qid=$(jq -r ".queries[$idx].id" "$QUERIES_FILE")
    query=$(jq -r ".queries[$idx].query" "$QUERIES_FILE")

    # Read anchors into an array
    local anchors=()
    while IFS= read -r anchor; do
        anchors+=("$anchor")
    done < <(jq -r ".queries[$idx].answer_anchors[]" "$QUERIES_FILE")

    local phase_display
    if [ "$phase" = "phase1" ]; then
        phase_display="WITHOUT RAG"
    else
        phase_display="WITH RAG"
    fi

    echo ""
    echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
    echo -e "${BOLD}  [${phase_display}] Query ${test_num}/${QUERY_COUNT}: ${CYAN}${qid}${RESET}"
    echo "      \"$query\""
    echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"

    # Narration: explain what we expect
    if [ "$phase" = "phase1" ]; then
        echo -e "${YELLOW}  Expecting: agent cannot find specific case details in its"
        echo -e "  empty memory -> answer will lack key facts.${RESET}"
    else
        echo -e "${YELLOW}  Expecting: agent retrieves indexed passages via search_knowledge"
        echo -e "  -> answer should contain specific case details.${RESET}"
    fi
    echo ""

    local t_start t_end duration
    t_start=$(date +%s)

    (cd "$PROJECT_ROOT" && uv run python agent7.py "$query") 2>&1 \
        | tee "$WORK_DIR/${phase}_${test_num}_output.txt"
    local rc=${PIPESTATUS[0]}

    t_end=$(date +%s)
    duration=$((t_end - t_start))

    # Extract FINAL: line
    local final_answer=""
    final_answer=$(grep '^FINAL: ' "$WORK_DIR/${phase}_${test_num}_output.txt" \
        | sed 's/^FINAL: //' | head -1)

    # Validate anchors against the final answer
    local matched=0
    local missing=()
    for anchor in "${anchors[@]}"; do
        if echo "$final_answer" | grep -qiF "$anchor"; then
            matched=$((matched + 1))
        else
            missing+=("$anchor")
        fi
    done

    local anchor_total=${#anchors[@]}
    local status
    if [ "$rc" -ne 0 ]; then
        status="FAIL"
    elif [ "$matched" -eq "$anchor_total" ]; then
        status="PASS"
    else
        status="FAIL"
    fi

    if [ "$status" = "PASS" ]; then
        echo -e "  ${GREEN}PASS${RESET}  anchors: ${matched}/${anchor_total}  (${duration}s)"
    else
        echo -e "  ${RED}FAIL${RESET}  anchors: ${matched}/${anchor_total}  (${duration}s)"
        if [ ${#missing[@]} -gt 0 ]; then
            echo "        missing:"
            for m in "${missing[@]}"; do
                echo "          - \"$m\""
            done
        fi
        if [ "$rc" -ne 0 ]; then
            echo "        agent exit code: $rc"
        fi
    fi

    # Update counters and results for the appropriate phase
    local result_entry="${status}|${qid}|${matched}/${anchor_total}|${duration}s"
    if [ "$phase" = "phase1" ]; then
        if [ "$status" = "PASS" ]; then
            PHASE1_PASS=$((PHASE1_PASS + 1))
        else
            PHASE1_FAIL=$((PHASE1_FAIL + 1))
        fi
        PHASE1_RESULTS+=("$result_entry")
    else
        if [ "$status" = "PASS" ]; then
            PHASE2_PASS=$((PHASE2_PASS + 1))
        else
            PHASE2_FAIL=$((PHASE2_FAIL + 1))
        fi
        PHASE2_RESULTS+=("$result_entry")
    fi
}

# ── Phase 1: Without RAG ─────────────────────────────────────────────
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║           PHASE 1: WITHOUT RAG INDEX                       ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "${YELLOW}  Temporarily removing the vector index so the agent starts"
echo -e "  with empty memory. Without indexed court opinions, the agent"
echo -e "  must rely on general knowledge or web search — it has never"
echo -e "  'seen' the source documents.${RESET}"
echo ""

# Back up state/ and create an empty one
mv "$PROJECT_ROOT/state" "$WORK_DIR/state_backup"
mkdir -p "$PROJECT_ROOT/state"

echo -e "${YELLOW}  state/ backed up -> agent now has empty memory${RESET}"
echo ""

for i in $(seq 0 $((QUERY_COUNT - 1))); do
    run_rag_test "$i" "phase1" "$((i + 1))"
done

# Phase 1 sub-summary
echo ""
echo -e "${BOLD}── Phase 1 sub-summary ────────────────────────────────────────${RESET}"
echo -e "  Without RAG: ${PHASE1_PASS}/${QUERY_COUNT} passed, ${PHASE1_FAIL}/${QUERY_COUNT} failed"
echo ""

# ── Phase 2: With RAG ────────────────────────────────────────────────
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║           PHASE 2: WITH RAG INDEX                          ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""

# Restore state/
rm -rf "$PROJECT_ROOT/state"
mv "$WORK_DIR/state_backup" "$PROJECT_ROOT/state"

# Count indexed chunks
CHUNK_COUNT="unknown"
if [ -f "$PROJECT_ROOT/state/memory.json" ]; then
    CHUNK_COUNT=$(jq '[.[] | select(.kind == "fact")] | length' "$PROJECT_ROOT/state/memory.json" 2>/dev/null || echo "unknown")
fi

echo -e "${YELLOW}  Restoring the vector index with ${CHUNK_COUNT} court-opinion chunks."
echo -e "  The agent's search_knowledge tool can now retrieve relevant"
echo -e "  passages via cosine similarity.${RESET}"
echo ""

for i in $(seq 0 $((QUERY_COUNT - 1))); do
    run_rag_test "$i" "phase2" "$((i + 1))"
done

# Phase 2 sub-summary
echo ""
echo -e "${BOLD}── Phase 2 sub-summary ────────────────────────────────────────${RESET}"
echo -e "  With RAG: ${PHASE2_PASS}/${QUERY_COUNT} passed, ${PHASE2_FAIL}/${QUERY_COUNT} failed"
echo ""

# ── Comparison summary table ─────────────────────────────────────────
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))
TOTAL_MIN=$((TOTAL_DURATION / 60))
TOTAL_SEC=$((TOTAL_DURATION % 60))

echo -e "${BOLD}══════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Comparison Summary${RESET}"
echo -e "${BOLD}══════════════════════════════════════════════════════════════${RESET}"
echo -e "${YELLOW}  The table below shows how vector indexing transforms answer"
echo -e "  quality for domain-specific questions.${RESET}"
echo ""

printf "  ${BOLD}%-3s %-36s %-12s %-12s %-10s${RESET}\n" "#" "Query ID" "Without RAG" "With RAG" "Anchors"
printf "  %-3s %-36s %-12s %-12s %-10s\n" "---" "------------------------------------" "----------" "----------" "--------"

for i in $(seq 0 $((QUERY_COUNT - 1))); do
    local_idx=$((i + 1))

    IFS='|' read -r p1_st p1_qid p1_anch p1_dur <<< "${PHASE1_RESULTS[$i]}"
    IFS='|' read -r p2_st _p2_qid p2_anch p2_dur <<< "${PHASE2_RESULTS[$i]}"

    # Color the status cells
    if [ "$p1_st" = "PASS" ]; then
        p1_display="${GREEN}PASS${RESET}"
    else
        p1_display="${RED}FAIL${RESET}"
    fi
    if [ "$p2_st" = "PASS" ]; then
        p2_display="${GREEN}PASS${RESET}"
    else
        p2_display="${RED}FAIL${RESET}"
    fi

    printf "  %-3s %-36s " "$local_idx" "$p1_qid"
    printf "${p1_display} %-5s " "($p1_anch)"
    printf "${p2_display} %-5s " "($p2_anch)"
    echo ""
done

echo ""
echo -e "  ${BOLD}Without RAG: ${PHASE1_PASS}/${QUERY_COUNT}  |  With RAG: ${PHASE2_PASS}/${QUERY_COUNT}${RESET}"
echo -e "  Total wall-clock time: ${TOTAL_MIN}m ${TOTAL_SEC}s"
echo -e "${BOLD}══════════════════════════════════════════════════════════════${RESET}"

if [ "$PHASE2_FAIL" -gt 0 ]; then
    exit 1
fi
