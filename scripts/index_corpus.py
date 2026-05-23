"""Batch-index all .txt files in a sandbox subdirectory.

Reuses the same chunking and embedding pipeline as ``index_document`` but
bypasses the MCP tool layer so that 44+ files don't each require an LLM
decision call.

Requires the LLM Gateway V7 to be running (for embeddings).

Usage::

    uv run python scripts/index_corpus.py                     # default: court_opinions
    uv run python scripts/index_corpus.py --subdir papers      # another subdir
    uv run python scripts/index_corpus.py --chunk-size 300 --overlap 60
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure the project root is importable.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import memory as _memory  # noqa: E402
from gateway import ensure_gateway  # noqa: E402

SANDBOX = PROJECT_ROOT / "sandbox"


def _chunk_text(text: str, size: int = 400, overlap: int = 80) -> list[str]:
    """Sliding-window chunking by word count.

    Duplicated from mcp_server._chunk_text so this script does not import the
    MCP server (which registers tools on import and starts an event loop).
    """
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    stride = max(1, size - overlap)
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + size]))
        if i + size >= len(words):
            break
        i += stride
    return chunks


def index_file(
    path: Path,
    *,
    run_id: str,
    chunk_size: int,
    overlap: int,
) -> int:
    """Read, chunk, and index a single file. Returns number of chunks stored."""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return 0

    # Source label matches what index_document would produce.
    rel = path.relative_to(SANDBOX)
    source = f"sandbox:{rel}"

    chunks = _chunk_text(text, size=chunk_size, overlap=overlap)
    for i, chunk in enumerate(chunks):
        preview = chunk[:120].replace("\n", " ")
        descriptor = f"[{source} chunk {i + 1}/{len(chunks)}] {preview}"
        _memory.add_fact(
            descriptor=descriptor,
            value={
                "chunk": chunk,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source": source,
            },
            source=source,
            run_id=run_id,
        )
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-index sandbox text files.")
    parser.add_argument(
        "--subdir",
        default="court_opinions",
        help="Subdirectory under sandbox/ to index (default: court_opinions)",
    )
    parser.add_argument("--chunk-size", type=int, default=400)
    parser.add_argument("--overlap", type=int, default=80)
    args = parser.parse_args()

    target = SANDBOX / args.subdir
    if not target.is_dir():
        print(f"Error: {target} is not a directory", file=sys.stderr)
        sys.exit(1)

    files = sorted(target.glob("*.txt"))
    if not files:
        print(f"No .txt files found in {target}", file=sys.stderr)
        sys.exit(1)

    ensure_gateway()

    run_id = f"batch-index-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    total_chunks = 0
    t0 = time.time()

    print(f"Indexing {len(files)} files from {target.relative_to(PROJECT_ROOT)}/")
    print(f"Chunk size: {args.chunk_size}, overlap: {args.overlap}")
    print(f"Run ID: {run_id}\n")

    for path in files:
        n = index_file(
            path,
            run_id=run_id,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
        total_chunks += n
        print(f"  {path.name}: {n} chunks")

    elapsed = time.time() - t0
    print(f"\nDone. {total_chunks} chunks from {len(files)} files in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
