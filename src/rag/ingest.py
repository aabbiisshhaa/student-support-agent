"""
src/rag/ingest.py - Knowledge Corpus Ingestion & Chunking Pipeline.

BSE4104 Agentic AI Capstone - University Student-Support Case Agent.
Week 1/3, Task 1: "Knowledge Corpus Register & Chunking".

What this file does
--------------------
Turns the raw, scraped Makerere University pages under `knowledge/raw/` into
the chunk records `src/rag/retriever.py` indexes, following the per-document
chunking strategy declared in the Week 1 register
(`docs/corpus_source_register.json`, itself canonicalised from
`docs/mak_knowledge_corpus_register.csv`).

    docs/corpus_source_register.json   (authoritative register, per doc:
                                         doc_id, source_url, chunking_strategy)
          |
          v
    knowledge/raw/<doc>.md             (scraped/cleaned page content)
          |
          v
    per-document chunker, selected by the register's declared strategy:
        - section_semantic     : split by heading, ~300-500 tokens/chunk
        - table_qa_hybrid       : tables kept atomic; Q&A kept one pair/chunk
        - section_ordered_steps : numbered procedures kept atomic
        - step_preserving       : one chunk per numbered instruction step
        - record_level          : one chunk per directory entry
        - hierarchical          : one chunk per category, parent/child tagged
          |
          v
    data/chunks.jsonl                  (one JSON object per chunk)
    data/chunk_manifest.json           (register version, per-doc counts,
                                         chunking strategy actually applied)

Every chunk record carries exactly the fields retriever.py's
`METADATA_FIELDS` and `RetrievedPassage` expect, so a rebuild here flows
straight through to the vector store with no schema translation step:

    chunk_id, text, doc_id, doc_title, category, source_url,
    retrieval_priority_tier, section_title, chunk_index, chunk_kind,
    token_count, content_hash, citation, overlap_with_previous, tags

Deliberately out of scope
-------------------------
* MAK-KB-001 (Timetable) is excluded on purpose - see the register's
  "excluded" section. It is live and form-driven; there is no stable page
  to chunk, and it is resolved by a dedicated lookup tool instead.
* MAK-KB-010's linked catalogue (courses.mak.ac.ug, 140+ programmes) is a
  separate, larger sub-corpus per the register's own notes; this file only
  ingests the Courses & Programs *listing* page itself.

Usage
-----
    python src/rag/ingest.py                 # build data/chunks.jsonl
    python src/rag/ingest.py --stats         # build, then print a summary
    python src/rag/ingest.py --doc MAK-KB-003  # rebuild a single document
    python src/rag/ingest.py --root /path/to/project

Then, from the same project root:
    python src/rag/retriever.py --build      # embed and index the chunks
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

# ==========================================================================
# 1. Project paths
# ==========================================================================


def find_project_root(start: Path | None = None) -> Path:
    """Locate the project root: the directory holding docs/ and knowledge/.

    Mirrors retriever.py's own resolution order so both files agree on where
    "the project" is when run from anywhere inside it.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / "docs" / "corpus_source_register.json").exists():
            return candidate
        if (candidate / "knowledge" / "raw").is_dir():
            return candidate
    if here.parent.name == "rag" and here.parent.parent.name == "src":
        return here.parents[2]
    return here.parent


PROJECT_ROOT = find_project_root()
DOCS_DIR = PROJECT_ROOT / "docs"
REGISTER_PATH = DOCS_DIR / "corpus_source_register.json"
KNOWLEDGE_RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
DATA_DIR = PROJECT_ROOT / "data"
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
CHUNK_MANIFEST_PATH = DATA_DIR / "chunk_manifest.json"


def _set_project_root(root: Path) -> None:
    global PROJECT_ROOT, DOCS_DIR, REGISTER_PATH, KNOWLEDGE_RAW_DIR
    global DATA_DIR, CHUNKS_PATH, CHUNK_MANIFEST_PATH
    PROJECT_ROOT = root
    DOCS_DIR = PROJECT_ROOT / "docs"
    REGISTER_PATH = DOCS_DIR / "corpus_source_register.json"
    KNOWLEDGE_RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
    DATA_DIR = PROJECT_ROOT / "data"
    CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
    CHUNK_MANIFEST_PATH = DATA_DIR / "chunk_manifest.json"


# ==========================================================================
# 2. Chunk sizing
# ==========================================================================
#
# The register expresses target chunk sizes in tokens ("~300-500
# tokens/chunk"). Tokenization here is a plain whitespace word count - the
# same crude, dependency-free proxy the retriever's own coverage signal
# uses - because what matters for chunk sizing is a stable, reproducible
# order of magnitude, not an exact tokenizer match to the embedding model.

TARGET_MIN_WORDS = 120
TARGET_MAX_WORDS = 480


def word_count(text: str) -> int:
    return len(text.split())


# ==========================================================================
# 3. Markdown section parsing
# ==========================================================================
#
# The raw files are hand-cleaned Markdown (page boilerplate - nav, footer,
# social links - already stripped at scrape time). Sections are delimited by
# ATX headings (`#`, `##`, `###`); this parser keeps heading level so the
# hierarchical and record-level strategies can tell a top-level entry apart
# from a sub-heading within it.

HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")


@dataclass
class Section:
    level: int
    title: str
    body: str  # raw text of this section, not including its own heading


def parse_sections(markdown_text: str) -> list[Section]:
    """Split a Markdown document into (heading, body) sections.

    The document's H1 title becomes the title of an implicit leading section
    if there is text before the first H2; that leading text is usually a
    one-line dek/summary and is folded into the first real section instead
    of being dropped.
    """
    lines = markdown_text.splitlines()
    sections: list[Section] = []
    current_title = "(preamble)"
    current_level = 1
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body or sections:
            sections.append(Section(level=current_level, title=current_title, body=body))

    for line in lines:
        match = HEADING_RE.match(line)
        if match:
            flush()
            current_level = len(match.group(1))
            current_title = match.group(2).strip()
            buffer = []
        else:
            buffer.append(line)
    flush()

    # Fold a title-only leading section (the H1 line itself, already
    # consumed as a heading) with no body into the following section instead
    # of emitting an empty chunk.
    cleaned = [s for s in sections if s.body.strip() or s.title != "(preamble)"]
    return cleaned or sections


# ==========================================================================
# 4. Chunk record construction
# ==========================================================================

ChunkKind = Literal[
    "section", "table", "qa_pair", "ordered_steps", "record",
    "hierarchical_entry", "hierarchical_list", "step", "step_intro",
]


@dataclass
class ChunkRecord:
    doc_id: str
    doc_title: str
    category: str
    source_url: str
    retrieval_priority_tier: str
    section_title: str
    chunk_index: int
    chunk_kind: ChunkKind
    text: str
    tags: list[str] = field(default_factory=list)
    overlap_with_previous: bool = False

    def finalize(self) -> dict[str, Any]:
        content_hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]
        chunk_id = f"{self.doc_id}::{self.chunk_index:03d}::{content_hash[:8]}"
        citation = f"{self.doc_title} \u2014 {self.section_title}"
        return {
            "chunk_id": chunk_id,
            "text": self.text,
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "category": self.category,
            "source_url": self.source_url,
            "retrieval_priority_tier": self.retrieval_priority_tier,
            "section_title": self.section_title,
            "chunk_index": self.chunk_index,
            "chunk_kind": self.chunk_kind,
            "token_count": word_count(self.text),
            "content_hash": content_hash,
            "citation": citation,
            "overlap_with_previous": self.overlap_with_previous,
            "tags": self.tags,
        }


class ChunkBuilder:
    """Accumulates ChunkRecords for one document with shared metadata."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc
        self.records: list[ChunkRecord] = []

    def add(
        self,
        section_title: str,
        text: str,
        chunk_kind: ChunkKind,
        tags: list[str] | None = None,
        overlap_with_previous: bool = False,
    ) -> None:
        text = text.strip()
        if not text:
            return
        self.records.append(
            ChunkRecord(
                doc_id=self.doc["doc_id"],
                doc_title=self.doc["doc_title"],
                category=self.doc["category"],
                source_url=self.doc["source_url"],
                retrieval_priority_tier=self.doc["retrieval_priority_tier"],
                section_title=section_title,
                chunk_index=len(self.records),
                chunk_kind=chunk_kind,
                text=text,
                tags=tags or [],
                overlap_with_previous=overlap_with_previous,
            )
        )

    def finalize(self) -> list[dict[str, Any]]:
        return [r.finalize() for r in self.records]


# ==========================================================================
# 5. Per-strategy chunkers
# ==========================================================================
#
# Each function takes the parsed sections of one document and a ChunkBuilder
# already scoped to that document's metadata, and appends chunk records to
# it. Splitting the strategies out this way keeps each one legible on its
# own and makes it obvious, reading the register, which function will run.

NUMBERED_LINE_RE = re.compile(r"^\s*\d+[.)]\s+")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_long_section(paragraphs: list[str], max_words: int) -> list[str]:
    """Greedily group paragraphs into ~max_words-sized groups.

    A single paragraph longer than max_words is kept whole rather than cut
    mid-sentence - going over the target is preferable to producing a chunk
    that ends mid-thought.
    """
    groups: list[str] = []
    current: list[str] = []
    current_words = 0
    for para in paragraphs:
        para_words = word_count(para)
        if current and current_words + para_words > max_words:
            groups.append("\n\n".join(current))
            current = [para]
            current_words = para_words
        else:
            current.append(para)
            current_words += para_words
    if current:
        groups.append("\n\n".join(current))
    return groups


def chunk_section_semantic(sections: list[Section], builder: ChunkBuilder) -> None:
    """Semantic section-based chunking by heading, ~300-500 tokens/chunk.

    Used for: Graduation Requirements, Mature Age Entry, E-Learning,
    Scholarships.
    """
    for section in sections:
        heading = f"## {section.title}\n\n" if section.title != "(preamble)" else ""
        paragraphs = _paragraphs(section.body)
        if not paragraphs:
            continue
        if word_count(section.body) <= TARGET_MAX_WORDS:
            builder.add(section.title, heading + section.body, "section")
            continue
        groups = _split_long_section(paragraphs, TARGET_MAX_WORDS)
        for i, group in enumerate(groups):
            title = section.title if len(groups) == 1 else f"{section.title} (part {i + 1})"
            builder.add(title, heading + group, "section", overlap_with_previous=(i > 0))


def chunk_table_qa_hybrid(sections: list[Section], builder: ChunkBuilder) -> None:
    """Hybrid chunking: markdown tables kept atomic; Q&A pairs one per chunk.

    Used for: Grading (marks table, CGPA table, "What can I do if..." /
    "How do I appeal?" Q&A), Fees & Payment Structure.
    """
    for section in sections:
        lines = section.body.splitlines()
        block: list[str] = []
        block_kind: str | None = None  # "table" | "prose" | None

        def flush_block() -> None:
            nonlocal block, block_kind
            text = "\n".join(block).strip()
            if not text:
                block, block_kind = [], None
                return
            if block_kind == "table":
                # Restate the section heading as a preamble so a lone table
                # chunk is still self-describing once retrieved on its own.
                preamble = f"## {section.title}\n\n" if section.title != "(preamble)" else ""
                builder.add(section.title, preamble + text, "table", tags=["table"])
            else:
                builder.add(section.title, text, "section")
            block, block_kind = [], None

        for line in lines:
            is_table_row = bool(TABLE_ROW_RE.match(line))
            kind = "table" if is_table_row else "prose"
            if block and kind != block_kind:
                flush_block()
            block.append(line)
            block_kind = kind
        flush_block()

        # Q&A-style sub-sections (### heading phrased as a question) were
        # already split out as their own `Section` objects by parse_sections
        # (level 3 headings), so they arrive here individually and each
        # becomes its own chunk via the loop above; retag them explicitly.
        if section.title.strip().endswith("?"):
            if builder.records and builder.records[-1].section_title == section.title:
                builder.records[-1].chunk_kind = "qa_pair"
                builder.records[-1].tags = list(set(builder.records[-1].tags + ["qa"]))


def chunk_ordered_steps(sections: list[Section], builder: ChunkBuilder) -> None:
    """Section-based chunking with numbered procedures kept atomic.

    A numbered list is never split across chunks, even if that makes the
    chunk exceed the normal target size - a partial procedure is worse than
    an oversized one.

    Used for: Examinations (appeal steps, retake steps), Registration
    (withdrawal steps, stay-put steps).
    """
    for section in sections:
        heading = f"## {section.title}\n\n" if section.title != "(preamble)" else ""
        lines = section.body.splitlines()

        has_numbered_list = any(NUMBERED_LINE_RE.match(line) for line in lines)
        if not has_numbered_list:
            paragraphs = _paragraphs(section.body)
            if word_count(section.body) <= TARGET_MAX_WORDS or not paragraphs:
                builder.add(section.title, heading + section.body, "section")
            else:
                groups = _split_long_section(paragraphs, TARGET_MAX_WORDS)
                for i, group in enumerate(groups):
                    title = section.title if len(groups) == 1 else f"{section.title} (part {i + 1})"
                    builder.add(title, heading + group, "section", overlap_with_previous=(i > 0))
            continue

        # Keep the whole section - intro prose plus its numbered list -
        # together as one atomic chunk, so step N is never separated from
        # the step before or after it.
        builder.add(
            section.title,
            heading + section.body,
            "ordered_steps",
            tags=["ordered_steps"],
        )


def chunk_record_level(sections: list[Section], builder: ChunkBuilder) -> None:
    """One chunk per listed record (institute, college), not by token count.

    Used for: Institutes, Colleges & Departments, Courses & Programs.
    """
    for section in sections:
        if section.title == "(preamble)" and not section.body.strip():
            continue
        heading = f"## {section.title}\n\n" if section.title != "(preamble)" else ""
        builder.add(
            section.title,
            heading + section.body,
            "record",
            tags=["academic_structure", "record"],
        )


def chunk_hierarchical(sections: list[Section], builder: ChunkBuilder) -> None:
    """One chunk per category, preserving parent/child as metadata tags.

    Used for: Academic Units (College / School / Institute / Centre /
    Department definitions, plus the list of the University's Colleges).
    """
    for section in sections:
        if section.title == "(preamble)" and not section.body.strip():
            continue
        heading = f"## {section.title}\n\n" if section.title != "(preamble)" else ""
        is_list = section.title.lower().startswith("our colleges")
        kind: ChunkKind = "hierarchical_list" if is_list else "hierarchical_entry"
        parent_tag = "academic_structure:list" if is_list else "academic_structure:definition"
        builder.add(
            section.title,
            heading + section.body,
            kind,
            tags=["academic_structure", parent_tag],
        )


def chunk_step_preserving(sections: list[Section], builder: ChunkBuilder) -> None:
    """One chunk per numbered instruction step, plus a prerequisites intro.

    Used for: Online Application Instructions.
    """
    for section in sections:
        lines = section.body.splitlines()
        has_numbered_list = any(NUMBERED_LINE_RE.match(line) for line in lines)

        if not has_numbered_list:
            heading = f"## {section.title}\n\n" if section.title != "(preamble)" else ""
            builder.add(
                section.title,
                heading + section.body,
                "step_intro",
                tags=["step_intro"],
            )
            continue

        # Split into (optional) intro prose before the first numbered line,
        # and then one chunk per numbered step, each carrying the section
        # heading so a single retrieved step is still self-describing.
        intro_lines: list[str] = []
        steps: list[list[str]] = []
        for line in lines:
            if NUMBERED_LINE_RE.match(line):
                steps.append([line])
            elif steps:
                steps[-1].append(line)
            else:
                intro_lines.append(line)

        intro_text = "\n".join(intro_lines).strip()
        if intro_text:
            builder.add(
                f"{section.title} (prerequisites)",
                f"## {section.title}\n\n{intro_text}",
                "step_intro",
                tags=["step_intro"],
            )
        for i, step_lines in enumerate(steps, start=1):
            step_text = "\n".join(step_lines).strip()
            builder.add(
                f"{section.title} - step {i}",
                f"## {section.title}\n\n{step_text}",
                "step",
                tags=["step_preserving", f"step_{i}"],
            )


STRATEGY_DISPATCH = {
    "section_semantic": chunk_section_semantic,
    "table_qa_hybrid": chunk_table_qa_hybrid,
    "section_ordered_steps": chunk_ordered_steps,
    "record_level": chunk_record_level,
    "hierarchical": chunk_hierarchical,
    "step_preserving": chunk_step_preserving,
}


# ==========================================================================
# 6. Register + document loading
# ==========================================================================


def load_register(path: Path | None = None) -> dict[str, Any]:
    path = path or REGISTER_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"No corpus source register at {path}. Expected "
            "docs/corpus_source_register.json (see docs/mak_knowledge_corpus_register.csv "
            "for the human-authored Week 1 source)."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_raw_text(doc: dict[str, Any]) -> str:
    raw_path = PROJECT_ROOT / doc["raw_file"]
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Register entry {doc['doc_id']} points at {raw_path}, which does not "
            "exist. Scrape/save the source page there before ingesting, or remove "
            "the entry from the register if it is intentionally not yet ready."
        )
    return raw_path.read_text(encoding="utf-8")


# ==========================================================================
# 7. Ingestion driver
# ==========================================================================


def ingest_document(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Chunk one document per its register-declared strategy."""
    strategy = doc["chunking_strategy"]
    chunker = STRATEGY_DISPATCH.get(strategy)
    if chunker is None:
        raise ValueError(
            f"{doc['doc_id']}: unknown chunking_strategy '{strategy}'. "
            f"Known strategies: {sorted(STRATEGY_DISPATCH)}."
        )
    raw_text = load_raw_text(doc)
    sections = parse_sections(raw_text)
    builder = ChunkBuilder(doc)
    chunker(sections, builder)
    if not builder.records:
        raise ValueError(
            f"{doc['doc_id']}: chunking produced zero chunks from "
            f"{doc['raw_file']} - the raw file may be empty or unparsable."
        )
    return builder.finalize()


def run_ingestion(
    register: dict[str, Any],
    only_doc_id: str | None = None,
    verbose: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Chunk every document in the register (or just `only_doc_id`).

    Returns the full list of chunk records plus a manifest summarising the
    run - both are also what `build_index` in retriever.py will read.
    """
    documents = register["documents"]
    if only_doc_id:
        documents = [d for d in documents if d["doc_id"] == only_doc_id]
        if not documents:
            raise ValueError(f"No document with doc_id '{only_doc_id}' in the register.")

    all_chunks: list[dict[str, Any]] = []
    per_doc_counts: dict[str, int] = {}
    per_strategy_counts: dict[str, int] = {}
    errors: list[str] = []

    for doc in documents:
        if verbose:
            print(f"  {doc['doc_id']:<12} {doc['doc_title']:<32} "
                  f"[{doc['chunking_strategy']}] <- {doc['raw_file']}")
        try:
            chunks = ingest_document(doc)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(str(exc))
            if verbose:
                print(f"    SKIPPED: {exc}")
            continue
        all_chunks.extend(chunks)
        per_doc_counts[doc["doc_id"]] = len(chunks)
        strategy = doc["chunking_strategy"]
        per_strategy_counts[strategy] = per_strategy_counts.get(strategy, 0) + len(chunks)
        if verbose:
            print(f"    -> {len(chunks)} chunks")

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": "src/rag/ingest.py",
        "register": {
            "version": register.get("register", {}).get("version"),
            "source_file": register.get("register", {}).get("source_file"),
            "documents_in_register": len(register["documents"]),
            "documents_ingested": len(per_doc_counts),
            "documents_excluded": [d["doc_id"] for d in register.get("excluded", [])],
        },
        "chunking_strategy": per_strategy_counts,
        "total_chunks": len(all_chunks),
        "chunks_per_document": per_doc_counts,
        "errors": errors,
    }
    return all_chunks, manifest


def write_outputs(chunks: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with CHUNKS_PATH.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False))
            fh.write("\n")
    CHUNK_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def print_stats(chunks: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    print(f"\nTotal chunks: {manifest['total_chunks']}")
    print("\nChunks per document:")
    for doc_id, count in manifest["chunks_per_document"].items():
        print(f"  {doc_id:<12} {count:>3}")
    print("\nChunks per chunking strategy:")
    for strategy, count in manifest["chunking_strategy"].items():
        print(f"  {strategy:<24} {count:>3}")
    token_counts = [c["token_count"] for c in chunks]
    if token_counts:
        print(
            f"\nChunk size (words): min={min(token_counts)} "
            f"max={max(token_counts)} avg={sum(token_counts) / len(token_counts):.0f}"
        )
    if manifest["errors"]:
        print("\nErrors:")
        for error in manifest["errors"]:
            print(f"  - {error}")


# ==========================================================================
# 8. Command line entry point
# ==========================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Knowledge corpus ingestion & chunking (BSE4104, Week 1/3 Task 1)"
    )
    parser.add_argument(
        "--doc", default=None, help="rebuild only this doc_id (e.g. MAK-KB-003)"
    )
    parser.add_argument(
        "--stats", action="store_true", help="print a chunking summary after building"
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="project root containing docs/ and knowledge/ (default: auto-detected)",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="suppress per-document progress output"
    )
    args = parser.parse_args(argv)

    if args.root is not None:
        _set_project_root(args.root.expanduser().resolve())

    register = load_register()
    verbose = not args.quiet

    if verbose:
        excluded = register.get("excluded", [])
        print(f"Register: {register['register']['version']} "
              f"({len(register['documents'])} documents"
              + (f", {len(excluded)} excluded" if excluded else "")
              + ")")

    if args.doc:
        # Rebuilding a single document must not clobber the chunks already
        # produced for every other document, so merge into the existing
        # chunks.jsonl rather than overwriting it outright.
        new_chunks, _ = run_ingestion(register, only_doc_id=args.doc, verbose=verbose)
        existing = []
        if CHUNKS_PATH.exists():
            existing = [
                json.loads(line)
                for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        kept = [c for c in existing if c["doc_id"] != args.doc]
        all_chunks = kept + new_chunks
        _, manifest = run_ingestion(register, verbose=False)
        # The merged manifest should reflect what's now on disk, not just the
        # single document just rebuilt.
        manifest["chunks_per_document"] = {
            **manifest["chunks_per_document"],
            args.doc: len(new_chunks),
        }
        manifest["total_chunks"] = len(all_chunks)
        write_outputs(all_chunks, manifest)
        if verbose:
            print(f"\nRebuilt {args.doc}: {len(new_chunks)} chunks. "
                  f"Total corpus now {len(all_chunks)} chunks across "
                  f"{len(kept) and len(manifest['chunks_per_document']) or len(manifest['chunks_per_document'])} documents.")
        if args.stats:
            print_stats(all_chunks, manifest)
        return 0

    chunks, manifest = run_ingestion(register, verbose=verbose)
    write_outputs(chunks, manifest)
    if verbose:
        print(f"\nWrote {len(chunks)} chunks -> {CHUNKS_PATH}")
        print(f"Wrote manifest -> {CHUNK_MANIFEST_PATH}")
    if args.stats:
        print_stats(chunks, manifest)
    return 0 if not manifest["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
