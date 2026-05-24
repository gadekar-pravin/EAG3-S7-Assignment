#!/usr/bin/env bash
set -uo pipefail

# ── Prerequisites ──────────────────────────────────────────────────────
GATEWAY_URL="http://localhost:8107/v1/status"
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

# ── Report setup ──────────────────────────────────────────────────────
LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/logs"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
REPORT="$LOG_DIR/test_report_${TIMESTAMP}.html"
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
START_TIME=$(date +%s)

# ── Test runner ────────────────────────────────────────────────────────
PASS=0
FAIL=0
TOTAL=0
FAILED_TESTS=""

run_test() {
    local label="$1"
    shift
    TOTAL=$((TOTAL + 1))

    # Extract query (last argument)
    local query=""
    for arg in "$@"; do query="$arg"; done

    echo ""
    echo "══════════════════════════════════════════════════════════════"
    echo "[$TOTAL/10] $label"
    echo "      \"$query\""
    echo "══════════════════════════════════════════════════════════════"

    local t_start
    t_start=$(date +%s)

    "$@" 2>&1 | tee "$WORK_DIR/${TOTAL}_output.txt"
    local rc=$?

    local t_end
    t_end=$(date +%s)
    local duration=$((t_end - t_start))
    local status="PASS"
    [ $rc -ne 0 ] && status="FAIL"

    if [ "$status" = "PASS" ]; then
        PASS=$((PASS + 1))
        echo "  ✓ PASS (${duration}s)"
    else
        FAIL=$((FAIL + 1))
        FAILED_TESTS="$FAILED_TESTS\n  - $label"
        echo "  ✗ FAIL (${duration}s)"
    fi

    # Extract FINAL answer
    grep '^FINAL: ' "$WORK_DIR/${TOTAL}_output.txt" | sed 's/^FINAL: //' | head -1 \
        > "$WORK_DIR/${TOTAL}_final.txt"

    # Save metadata
    echo "$label"    > "$WORK_DIR/${TOTAL}_label.txt"
    echo "$query"    > "$WORK_DIR/${TOTAL}_query.txt"
    echo "$status"   > "$WORK_DIR/${TOTAL}_status.txt"
    echo "$duration" > "$WORK_DIR/${TOTAL}_duration.txt"

    # HTML-escape output (& first, then < and >)
    LC_ALL=C sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g' \
        "$WORK_DIR/${TOTAL}_output.txt" > "$WORK_DIR/${TOTAL}_escaped.txt"
}

# ── HTML report generator ─────────────────────────────────────────────
generate_report() {
    local end_time
    end_time=$(date +%s)
    local total_duration=$((end_time - START_TIME))
    local total_min=$((total_duration / 60))
    local total_sec=$((total_duration % 60))
    local gen_date
    gen_date=$(date '+%Y-%m-%d %H:%M:%S')
    local host
    host=$(hostname -s 2>/dev/null || echo "unknown")

    cat > "$REPORT" <<'HEADER_EOF'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EAG3-S7 Agent Test Report</title>
<style>
  :root { --pass: #22863a; --fail: #cb2431; --bg: #fafbfc; --border: #e1e4e8; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
         margin: 0; padding: 20px; background: var(--bg); color: #24292e; line-height: 1.5; }
  h1 { margin: 0 0 4px; font-size: 1.6em; }
  .meta { color: #586069; font-size: 0.9em; margin-bottom: 16px; }
  .summary { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
  .summary .card { background: #fff; border: 1px solid var(--border); border-radius: 6px;
                   padding: 12px 20px; font-size: 1.1em; }
  .card.pass-card { border-left: 4px solid var(--pass); }
  .card.fail-card { border-left: 4px solid var(--fail); }
  .card .num { font-size: 1.8em; font-weight: 700; }
  .card .num.pass { color: var(--pass); }
  .card .num.fail { color: var(--fail); }
  table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid var(--border);
          border-radius: 6px; overflow: hidden; margin-bottom: 24px; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }
  th { background: #f6f8fa; font-weight: 600; font-size: 0.85em; text-transform: uppercase; }
  td { font-size: 0.95em; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.8em;
           font-weight: 600; color: #fff; }
  .badge.pass { background: var(--pass); }
  .badge.fail { background: var(--fail); }
  details { background: #fff; border: 1px solid var(--border); border-radius: 6px;
            margin-bottom: 12px; overflow: hidden; }
  summary { padding: 12px 16px; cursor: pointer; font-weight: 600; font-size: 1.05em;
            user-select: none; }
  summary:hover { background: #f6f8fa; }
  .detail-body { padding: 0 16px 16px; }
  .detail-body .query { background: #f6f8fa; padding: 8px 12px; border-radius: 4px;
                        font-family: monospace; margin-bottom: 12px; white-space: pre-wrap;
                        word-break: break-word; }
  .detail-body .final-answer { background: #dafbe1; padding: 8px 12px; border-radius: 4px;
                                margin-bottom: 12px; }
  .detail-body .final-answer.fail { background: #ffeef0; }
  pre.output { background: #1b1f23; color: #e1e4e8; padding: 16px; border-radius: 6px;
               overflow-x: auto; font-size: 0.85em; line-height: 1.4; white-space: pre-wrap;
               word-break: break-word; max-height: 600px; overflow-y: auto; }
  .footer { color: #586069; font-size: 0.8em; margin-top: 20px; text-align: center; }
</style>
</head>
<body>
HEADER_EOF

    # Title and meta
    cat >> "$REPORT" <<META_EOF
<h1>EAG3-S7 Agent Test Report</h1>
<div class="meta">Generated: ${gen_date} &nbsp;|&nbsp; Host: ${host} &nbsp;|&nbsp; Duration: ${total_min}m ${total_sec}s</div>
META_EOF

    # Summary cards
    cat >> "$REPORT" <<SUMMARY_EOF
<div class="summary">
  <div class="card pass-card"><div class="num pass">${PASS}</div>Passed</div>
  <div class="card fail-card"><div class="num fail">${FAIL}</div>Failed</div>
  <div class="card"><div class="num">${TOTAL}</div>Total</div>
  <div class="card"><div class="num">${total_min}m ${total_sec}s</div>Duration</div>
</div>
SUMMARY_EOF

    # Summary table
    cat >> "$REPORT" <<'TABLE_HEADER'
<table>
<thead><tr><th>#</th><th>Test</th><th>Query</th><th>Status</th><th>Time</th><th>Final Answer</th></tr></thead>
<tbody>
TABLE_HEADER

    local i=1
    while [ $i -le "$TOTAL" ]; do
        local t_label t_status t_duration t_final t_query badge_class
        t_label=$(cat "$WORK_DIR/${i}_label.txt")
        t_status=$(cat "$WORK_DIR/${i}_status.txt")
        t_duration=$(cat "$WORK_DIR/${i}_duration.txt")
        t_final=$(cat "$WORK_DIR/${i}_final.txt" 2>/dev/null || echo "")
        t_query=$(cat "$WORK_DIR/${i}_query.txt")

        if [ "$t_status" = "PASS" ]; then
            badge_class="pass"
        else
            badge_class="fail"
        fi

        # Truncate final answer for summary table (first 150 chars)
        local t_final_short
        t_final_short=$(printf '%.150s' "$t_final")
        if [ ${#t_final} -gt 150 ]; then
            t_final_short="${t_final_short}..."
        fi

        # HTML-escape the truncated final answer and query for the table
        t_final_short=$(echo "$t_final_short" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')
        local t_query_escaped
        t_query_escaped=$(echo "$t_query" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')

        cat >> "$REPORT" <<ROW_EOF
<tr>
  <td>${i}</td>
  <td>${t_label}</td>
  <td style="font-size:0.85em; max-width:300px">${t_query_escaped}</td>
  <td><span class="badge ${badge_class}">${t_status}</span></td>
  <td>${t_duration}s</td>
  <td>${t_final_short}</td>
</tr>
ROW_EOF
        i=$((i + 1))
    done

    echo "</tbody></table>" >> "$REPORT"

    # Detail sections (failed tests first, expanded)
    echo '<h2>Test Details</h2>' >> "$REPORT"

    # Failed tests first (open by default)
    local i=1
    while [ $i -le "$TOTAL" ]; do
        local t_status
        t_status=$(cat "$WORK_DIR/${i}_status.txt")
        if [ "$t_status" = "FAIL" ]; then
            _write_detail_section "$i" "open"
        fi
        i=$((i + 1))
    done

    # Then passing tests (collapsed)
    local i=1
    while [ $i -le "$TOTAL" ]; do
        local t_status
        t_status=$(cat "$WORK_DIR/${i}_status.txt")
        if [ "$t_status" = "PASS" ]; then
            _write_detail_section "$i" ""
        fi
        i=$((i + 1))
    done

    # Footer
    cat >> "$REPORT" <<'FOOTER_EOF'
<div class="footer">Generated by scripts/run_all.sh</div>
</body>
</html>
FOOTER_EOF
}

_write_detail_section() {
    local idx="$1"
    local open_attr="$2"

    local t_label t_status t_duration t_query t_final t_escaped
    t_label=$(cat "$WORK_DIR/${idx}_label.txt")
    t_status=$(cat "$WORK_DIR/${idx}_status.txt")
    t_duration=$(cat "$WORK_DIR/${idx}_duration.txt")
    t_query=$(cat "$WORK_DIR/${idx}_query.txt")
    t_final=$(cat "$WORK_DIR/${idx}_final.txt" 2>/dev/null || echo "")
    t_escaped=$(cat "$WORK_DIR/${idx}_escaped.txt")

    local badge_class="pass"
    local answer_class=""
    [ "$t_status" = "FAIL" ] && badge_class="fail" && answer_class=" fail"

    # HTML-escape query and final answer for detail view
    t_query=$(echo "$t_query" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')
    t_final=$(echo "$t_final" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')

    cat >> "$REPORT" <<DETAIL_EOF
<details ${open_attr}>
  <summary><span class="badge ${badge_class}">${t_status}</span> &nbsp; Test ${idx}: ${t_label} &nbsp; (${t_duration}s)</summary>
  <div class="detail-body">
    <strong>Query:</strong>
    <div class="query">${t_query}</div>
    <strong>Final Answer:</strong>
    <div class="final-answer${answer_class}">${t_final:-<em>No FINAL answer captured</em>}</div>
    <strong>Full Agent Output:</strong>
    <pre class="output">${t_escaped}</pre>
  </div>
</details>
DETAIL_EOF
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

# Generate HTML report
generate_report
echo "Report: $REPORT"

if [ "$FAIL" -gt 0 ]; then
    echo -e "Failed tests:$FAILED_TESTS"
    echo "══════════════════════════════════════════════════════════════"
    command -v open > /dev/null 2>&1 && open "$REPORT"
    exit 1
else
    echo "All tests passed."
    echo "══════════════════════════════════════════════════════════════"
    command -v open > /dev/null 2>&1 && open "$REPORT"
fi
