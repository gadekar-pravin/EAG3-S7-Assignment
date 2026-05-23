"""Standalone RAG engine for the court-opinion localhost app.

The cognitive agent keeps its Memory/Perception/Decision/Action loop unchanged.
This module is a narrower, UI-facing RAG path over ``sandbox/court_opinions``:
parse the local text corpus, build a separate FAISS index, retrieve chunks, and
answer with citations.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from gateway import LLM
from gateway import embed as gateway_embed
from vector_index import VectorIndex

PROJECT_ROOT = Path(__file__).resolve().parent
CORPUS_DIR = PROJECT_ROOT / "sandbox" / "court_opinions"
STORE_DIR = PROJECT_ROOT / "state" / "court_rag"
CHUNKS_PATH = STORE_DIR / "chunks.json"
MANIFEST_PATH = STORE_DIR / "manifest.json"
QUERIES_PATH = PROJECT_ROOT / "rag_queries.json"

DEFAULT_CHUNK_WORDS = 320
DEFAULT_OVERLAP_WORDS = 60

Embedder = Callable[[str, str], list[float]]
AnswerGenerator = Callable[[str, list["RetrievedChunk"]], str]


@dataclass(frozen=True)
class CourtOpinion:
    path: str
    case: str
    court: str
    date_filed: str
    citations: str
    url: str
    source_query: str
    text: str

    def label(self) -> str:
        if self.citations:
            return f"{self.case}, {self.citations}"
        return self.case


@dataclass(frozen=True)
class IndexedChunk:
    id: str
    source_path: str
    case: str
    court: str
    date_filed: str
    citations: str
    url: str
    chunk_index: int
    total_chunks: int
    text: str

    def embedding_text(self) -> str:
        return (
            f"Case: {self.case}\n"
            f"Court: {self.court}\n"
            f"Date Filed: {self.date_filed}\n"
            f"Citations: {self.citations}\n\n"
            f"{self.text}"
        )


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    score: float
    source_path: str
    case: str
    court: str
    date_filed: str
    citations: str
    url: str
    chunk_index: int
    total_chunks: int
    text: str

    def citation_label(self) -> str:
        suffix = f", {self.citations}" if self.citations else ""
        return f"{self.case}{suffix}"


@dataclass(frozen=True)
class IndexStats:
    indexed: bool
    document_count: int
    chunk_count: int
    store_dir: str
    corpus_dir: str
    built_at: str | None = None
    chunk_words: int | None = None
    overlap_words: int | None = None


@dataclass(frozen=True)
class RagAnswer:
    status: str
    query: str
    use_index: bool
    answer: str
    sources: list[dict]
    chunks: list[dict]


def default_embedder(text: str, task_type: str) -> list[float]:
    """Embed text through LLM Gateway V7."""
    return list(gateway_embed(text, task_type=task_type)["embedding"])


def _metadata_value(text: str, key: str) -> str:
    prefix = f"{key}:"
    for line in text.splitlines()[:12]:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def parse_opinion(path: Path, *, corpus_dir: Path = CORPUS_DIR) -> CourtOpinion:
    text = path.read_text(encoding="utf-8", errors="replace")
    return CourtOpinion(
        path=str(path.relative_to(corpus_dir)),
        case=_metadata_value(text, "Case") or path.stem,
        court=_metadata_value(text, "Court"),
        date_filed=_metadata_value(text, "Date Filed"),
        citations=_metadata_value(text, "Citations"),
        url=_metadata_value(text, "URL"),
        source_query=_metadata_value(text, "Source Query"),
        text=text,
    )


def load_corpus(corpus_dir: Path = CORPUS_DIR) -> list[CourtOpinion]:
    if not corpus_dir.exists():
        return []
    return [
        parse_opinion(path, corpus_dir=corpus_dir)
        for path in sorted(corpus_dir.glob("*.txt"))
    ]


def chunk_words(
    text: str,
    *,
    size: int = DEFAULT_CHUNK_WORDS,
    overlap: int = DEFAULT_OVERLAP_WORDS,
) -> list[str]:
    words = text.split()
    if not words:
        return []
    stride = max(1, size - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
        start += stride
    return chunks


def _chunk_id(source_path: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256(f"{source_path}:{chunk_index}:{text}".encode()).hexdigest()[:16]
    return f"court:{digest}"


def make_chunks(
    documents: list[CourtOpinion],
    *,
    chunk_size: int = DEFAULT_CHUNK_WORDS,
    overlap: int = DEFAULT_OVERLAP_WORDS,
) -> list[IndexedChunk]:
    chunks: list[IndexedChunk] = []
    for doc in documents:
        doc_chunks = chunk_words(doc.text, size=chunk_size, overlap=overlap)
        total = len(doc_chunks)
        for i, text in enumerate(doc_chunks):
            chunks.append(
                IndexedChunk(
                    id=_chunk_id(doc.path, i, text),
                    source_path=doc.path,
                    case=doc.case,
                    court=doc.court,
                    date_filed=doc.date_filed,
                    citations=doc.citations,
                    url=doc.url,
                    chunk_index=i,
                    total_chunks=total,
                    text=text,
                )
            )
    return chunks


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_chunks(store_dir: Path = STORE_DIR) -> list[IndexedChunk]:
    path = store_dir / "chunks.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [IndexedChunk(**item) for item in raw]


def build_index(
    *,
    corpus_dir: Path = CORPUS_DIR,
    store_dir: Path = STORE_DIR,
    embedder: Embedder = default_embedder,
    chunk_size: int = DEFAULT_CHUNK_WORDS,
    overlap: int = DEFAULT_OVERLAP_WORDS,
) -> IndexStats:
    documents = load_corpus(corpus_dir)
    chunks = make_chunks(documents, chunk_size=chunk_size, overlap=overlap)

    store_dir.mkdir(parents=True, exist_ok=True)
    idx = VectorIndex(store_dir)
    idx.clear()

    for chunk in chunks:
        embedding = embedder(chunk.embedding_text(), "retrieval_document")
        idx.add(chunk.id, embedding)
    idx.persist()

    built_at = datetime.now(UTC).isoformat(timespec="seconds")
    _write_json(store_dir / "chunks.json", [asdict(chunk) for chunk in chunks])
    _write_json(
        store_dir / "manifest.json",
        {
            "built_at": built_at,
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "chunk_words": chunk_size,
            "overlap_words": overlap,
            "corpus_dir": str(corpus_dir),
        },
    )
    return IndexStats(
        indexed=True,
        document_count=len(documents),
        chunk_count=len(chunks),
        store_dir=str(store_dir),
        corpus_dir=str(corpus_dir),
        built_at=built_at,
        chunk_words=chunk_size,
        overlap_words=overlap,
    )


def get_status(*, corpus_dir: Path = CORPUS_DIR, store_dir: Path = STORE_DIR) -> dict:
    documents = load_corpus(corpus_dir)
    manifest_path = store_dir / "manifest.json"
    chunks_path = store_dir / "chunks.json"
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stats = IndexStats(
        indexed=manifest_path.exists() and chunks_path.exists(),
        document_count=int(manifest.get("document_count") or len(documents)),
        chunk_count=int(manifest.get("chunk_count") or 0),
        store_dir=str(store_dir),
        corpus_dir=str(corpus_dir),
        built_at=manifest.get("built_at"),
        chunk_words=manifest.get("chunk_words"),
        overlap_words=manifest.get("overlap_words"),
    )
    return {
        **asdict(stats),
        "sample_queries": load_sample_queries(),
    }


def load_sample_queries(path: Path = QUERIES_PATH) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("queries") or [])
    if isinstance(data, list):
        return data
    return []


def retrieve(
    query: str,
    *,
    store_dir: Path = STORE_DIR,
    embedder: Embedder = default_embedder,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    chunks = _load_chunks(store_dir)
    if not chunks:
        return []

    idx = VectorIndex(store_dir)
    if idx.size == 0:
        return []

    query_embedding = embedder(query, "retrieval_query")
    hits = idx.search(query_embedding, k=max(1, top_k))
    by_id = {chunk.id: chunk for chunk in chunks}
    results: list[RetrievedChunk] = []
    for item_id, score in hits:
        chunk = by_id.get(item_id)
        if chunk is None:
            continue
        results.append(RetrievedChunk(score=score, **asdict(chunk)))
    return results


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(
            f"[{i}] {chunk.citation_label()} | {chunk.court} | {chunk.date_filed} | "
            f"{chunk.source_path} chunk {chunk.chunk_index + 1}/{chunk.total_chunks}\n"
            f"{chunk.text}"
        )
    return "\n\n".join(blocks)


def default_answer_generator(query: str, chunks: list[RetrievedChunk]) -> str:
    context = _format_context(chunks)
    prompt = (
        "Answer the legal research question using only the retrieved court-opinion "
        "context. Cite sources inline with bracket numbers like [1]. If the context "
        "does not support the answer, say so.\n\n"
        f"QUESTION:\n{query}\n\n"
        f"RETRIEVED CONTEXT:\n{context}"
    )
    reply = LLM().chat(
        prompt=prompt,
        system="You are a precise legal RAG assistant. Do not use outside knowledge.",
        auto_route="decision",
        temperature=0,
        max_tokens=900,
    )
    return (reply.get("text") or "").strip()


def _fallback_answer(query: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return (
            "I could not find supporting court-opinion context for this question in the "
            "local index."
        )
    source = chunks[0]
    preview = source.text[:700].strip()
    return (
        f"The strongest retrieved source is {source.citation_label()} "
        f"({source.source_path}). The available context begins: {preview}"
    )


def answer_question(
    query: str,
    *,
    use_index: bool = True,
    store_dir: Path = STORE_DIR,
    embedder: Embedder = default_embedder,
    answer_generator: AnswerGenerator = default_answer_generator,
    top_k: int = 5,
) -> RagAnswer:
    clean_query = query.strip()
    if not clean_query:
        return RagAnswer(
            status="empty_query",
            query=query,
            use_index=use_index,
            answer="Enter a question about the court-opinion corpus.",
            sources=[],
            chunks=[],
        )

    if not use_index:
        return RagAnswer(
            status="no_index_context",
            query=clean_query,
            use_index=False,
            answer=(
                "No answer: the index was disabled, so the app has no retrieved "
                "court-opinion context to ground this question."
            ),
            sources=[],
            chunks=[],
        )

    chunks = retrieve(clean_query, store_dir=store_dir, embedder=embedder, top_k=top_k)
    if not chunks:
        return RagAnswer(
            status="no_hits",
            query=clean_query,
            use_index=True,
            answer=(
                "No indexed court-opinion chunks were available for this question. "
                "Build the index first, then try again."
            ),
            sources=[],
            chunks=[],
        )

    try:
        answer = answer_generator(clean_query, chunks)
    except Exception:
        answer = _fallback_answer(clean_query, chunks)

    sources_by_path: dict[str, dict] = {}
    for chunk in chunks:
        sources_by_path.setdefault(
            chunk.source_path,
            {
                "source_path": chunk.source_path,
                "case": chunk.case,
                "court": chunk.court,
                "date_filed": chunk.date_filed,
                "citations": chunk.citations,
                "url": chunk.url,
                "best_score": chunk.score,
            },
        )
    return RagAnswer(
        status="answered",
        query=clean_query,
        use_index=True,
        answer=answer,
        sources=list(sources_by_path.values()),
        chunks=[
            {
                "id": chunk.id,
                "score": chunk.score,
                "source_path": chunk.source_path,
                "case": chunk.case,
                "court": chunk.court,
                "date_filed": chunk.date_filed,
                "citations": chunk.citations,
                "url": chunk.url,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "preview": chunk.text[:900],
            }
            for chunk in chunks
        ],
    )
