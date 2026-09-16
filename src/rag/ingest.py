"""
src/rag/ingest.py - Knowledge Corpus Ingestion and Chunking.

BSE4104 Agentic AI Capstone - University Student-Support Case Agent.
Week 3, Task 1: "Knowledge Corpus Ingestion & Chunking (referencing the
register created in Week 1)".

What this file does
-------------------
It parses the university policy PDFs and Markdown files that are listed in the
Week 1 Corpus/Source Register into structured, citable chunks with source
metadata:

    docs/corpus_source_register.json      (the Week 1 register)
            |
            |  approved: true entries only - everything else is skipped,
            |  loudly, with the recorded reason
            v
    knowledge/raw/*.pdf, *.md             load, keeping page + section
            |
            v
    clean and normalise                -> knowledge/processed/<doc_id>.txt
            |
            v
    section-aware sentence packing with sentence-level overlap
            |
            v
    data/chunks.jsonl                     one JSON chunk per line
    data/chunk_manifest.json              what was produced, and how

This file is completely self-contained. Register handling, loading, cleaning,
token counting and chunking all live here, and so do the Week 1 register and
the corpus itself (section 1b), so the file runs on its own in an empty
directory with no other project file present. When the surrounding project IS
present - docs/corpus_source_register.json and knowledge/raw/ - those files are
used instead of the built-in copies, and the output is the same either way.

Outside the standard library it needs only pypdf, which reads the six PDF
documents in the corpus.

Usage
-----
    python src/rag/ingest.py              # run the pipeline and write output
    python src/rag/ingest.py --dry-run    # run and report, write nothing
    python src/rag/ingest.py --validate   # only check register vs disk
    python src/rag/ingest.py --root /path/to/project

Or as a library:

    from ingest import load_register, ingest_corpus, load_chunks
    chunks, manifest = ingest_corpus(load_register())

Owner: Pauline Peace (PP).
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import math
import os
import re
import statistics
import tarfile
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# ==========================================================================
# 1. Project paths
# ==========================================================================
#
# The register, the raw corpus and the outputs are located relative to the
# project root rather than to the current working directory, so the script
# behaves the same whether it is run from the repository root, from src/, or
# through an IDE run configuration.


def find_project_root(start: Path | None = None) -> Path:
    """Locate the project root.

    Resolution order:
      1. the RAG_PROJECT_ROOT environment variable, if set;
      2. the nearest ancestor directory that contains the Week 1 register at
         docs/corpus_source_register.json, or a knowledge/raw/ directory;
      3. two levels above this file (i.e. the parent of src/), which is the
         layout this artifact is written for.
    """
    env_root = os.environ.get("RAG_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / "docs" / "corpus_source_register.json").exists():
            return candidate
        if (candidate / "knowledge" / "raw").is_dir():
            return candidate

    # Nothing recognisable nearby. If this file sits at src/rag/<name>.py the
    # project root is two levels up; otherwise the file is running on its own
    # and its own directory is the right place to work in.
    if here.parent.name == "rag" and here.parent.parent.name == "src":
        return here.parents[2]
    return here.parent


def _writable_root(root: Path) -> Path:
    """Fall back to a temporary directory if the detected root is read-only.

    This only matters when the file is run from somewhere it cannot write -
    a marker running it from a read-only checkout, for instance. The pipeline
    then materialises the built-in corpus and its outputs under the system
    temporary directory instead of failing.
    """
    try:
        if os.access(root, os.W_OK):
            return root
    except OSError:
        pass
    fallback = Path(tempfile.gettempdir()) / "bse4104_rag"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


PROJECT_ROOT = _writable_root(find_project_root())

# The Week 1 Corpus/Source Register: the pipeline's authority on what may be
# ingested.
REGISTER_PATH = PROJECT_ROOT / "docs" / "corpus_source_register.json"

# The corpus exactly as received by the pipeline: PDFs and Markdown.
RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"

# Cleaned plain text, one .txt per document (human-inspectable intermediate).
PROCESSED_DIR = PROJECT_ROOT / "knowledge" / "processed"

# Pipeline outputs.
DATA_DIR = PROJECT_ROOT / "data"
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
CHUNK_MANIFEST_PATH = DATA_DIR / "chunk_manifest.json"

# ==========================================================================
# 1b. Built-in copy of the register and the corpus
# ==========================================================================
#
# This file is submitted on its own, so it carries everything it needs to run:
# the Week 1 Corpus/Source Register below, and the corpus itself as a gzipped
# tar archive of the exact bytes of knowledge/raw/ (6 PDFs and 7 Markdown
# files, including the unapproved draft that the register excludes).
#
# Disk always wins. If docs/corpus_source_register.json exists, that register
# is used; if knowledge/raw/ already holds the registered files, those files
# are used. The built-in copies are only unpacked when the surrounding project
# is not there - which is what makes `python ingest.py` work from an empty
# directory. Either way the pipeline produces the same 101 chunks, because the
# bytes are the same bytes.
#
# The archive is checked against a SHA-256 digest before use, so a corrupted
# copy of this file fails loudly instead of silently ingesting damaged text.

EMBEDDED_REGISTER_JSON = r"""
{
  "register_name": "University Student-Support Case Agent - Corpus/Source Register",
  "course": "BSE4104 Agentic AI Capstone",
  "project": "University Student-Support Case Agent",
  "register_version": "1.0",
  "maintained_by": "Group register created in Week 1; machine-readable form maintained by Pauline Peace (PP) for Week 3 ingestion.",
  "provenance_statement": "All documents in this corpus are synthetic. They were authored by the project team to model the structure, register and rule density of genuine Ugandan university policy documents. They contain no real student records, no personal data and no copyrighted third-party text. 'Nakawa University' is a fictional institution used for the purposes of this capstone.",
  "usage_rule": "The ingestion pipeline may only ingest entries whose `approved` field is true. Any other document present in knowledge/raw/ must be skipped and the skip must be logged.",
  "documents": [
    {
      "doc_id": "academic_handbook_2026",
      "title": "Nakawa University Academic Handbook 2025/2026",
      "publisher": "Office of the Academic Registrar",
      "version": "2025/2026 Edition",
      "effective_date": "2025-08-01",
      "format": "pdf",
      "raw_file": "academic_handbook_2026.pdf",
      "category": "academic_regulation",
      "covers": "Registration, add/drop, attendance, grading scale, progression, retakes, deferment, transcripts",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "academic_calendar_2026",
      "title": "Nakawa University Academic Calendar 2025/2026",
      "publisher": "Office of the Academic Registrar",
      "version": "Approved by Senate 2025-06-18",
      "effective_date": "2025-08-01",
      "format": "pdf",
      "raw_file": "academic_calendar_2026.pdf",
      "category": "key_dates",
      "covers": "Semester start and end dates, registration windows, add/drop deadlines, examination periods, results release, recess",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "examination_regulations_2026",
      "title": "Nakawa University Examination Regulations",
      "publisher": "Office of the Academic Registrar",
      "version": "Revised 2025",
      "effective_date": "2025-08-01",
      "format": "pdf",
      "raw_file": "examination_regulations_2026.pdf",
      "category": "assessment",
      "covers": "Examination eligibility, conduct, misconduct penalties, special examinations, remarking, supplementary and retake examinations",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "fees_policy_2026",
      "title": "Nakawa University Student Fees and Financial Policy",
      "publisher": "Directorate of Finance",
      "version": "2025/2026",
      "effective_date": "2025-08-01",
      "format": "pdf",
      "raw_file": "fees_policy_2026.pdf",
      "category": "finance",
      "covers": "Tuition and functional fees, instalment schedule, late payment surcharge, refunds, financial clearance, payment channels",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "ict_portal_guidelines_2026",
      "title": "Nakawa University ICT and Student Portal Guidelines",
      "publisher": "Directorate of ICT Services",
      "version": "3.1",
      "effective_date": "2025-08-01",
      "format": "pdf",
      "raw_file": "ict_portal_guidelines_2026.pdf",
      "category": "ict_support",
      "covers": "Student accounts, password reset, portal availability, acceptable use, Wi-Fi, LMS access, ICT helpdesk service levels",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "library_services_2026",
      "title": "Nakawa University Library Services Guide",
      "publisher": "University Librarian",
      "version": "2025/2026",
      "effective_date": "2025-08-01",
      "format": "pdf",
      "raw_file": "library_services_2026.pdf",
      "category": "student_services",
      "covers": "Membership, loan entitlements and periods, renewals, fines, e-resources, inter-library loans, opening hours",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "student_regulations_2026",
      "title": "Nakawa University Student Regulations and Code of Conduct",
      "publisher": "Office of the Dean of Students",
      "version": "2025 Revision",
      "effective_date": "2025-08-01",
      "format": "md",
      "raw_file": "student_regulations_2026.md",
      "category": "conduct",
      "covers": "Scope of the Code, prohibited conduct, disciplinary procedure, sanctions, appeals against sanctions, student rights",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "course_handbook_bse_2026",
      "title": "Course Handbook: BSc Software Engineering",
      "publisher": "Department of Computer Science, Faculty of Engineering",
      "version": "2025/2026",
      "effective_date": "2025-08-01",
      "format": "md",
      "raw_file": "course_handbook_bse_2026.md",
      "category": "programme_information",
      "covers": "Programme structure, credit requirements, core and elective courses, industrial training, final year project, progression rules",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "student_support_services_2026",
      "title": "Nakawa University Student Support and Welfare Services",
      "publisher": "Office of the Dean of Students",
      "version": "2025/2026",
      "effective_date": "2025-08-01",
      "format": "md",
      "raw_file": "student_support_services_2026.md",
      "category": "student_services",
      "covers": "Counselling, disability support, health services, financial hardship, safeguarding, referral routes and contact points",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "graduation_awards_2026",
      "title": "Nakawa University Graduation and Academic Awards Policy",
      "publisher": "Office of the Academic Registrar",
      "version": "2025/2026",
      "effective_date": "2025-08-01",
      "format": "md",
      "raw_file": "graduation_awards_2026.md",
      "category": "academic_regulation",
      "covers": "Eligibility to graduate, classification of awards, clearance, ceremony arrangements, certificates and academic dress",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "accommodation_policy_2026",
      "title": "Nakawa University Accommodation and Halls of Residence Policy",
      "publisher": "Directorate of Estates and Halls",
      "version": "2025/2026",
      "effective_date": "2025-08-01",
      "format": "md",
      "raw_file": "accommodation_policy_2026.md",
      "category": "student_services",
      "covers": "Hall allocation, application windows, charges, conduct in halls, vacation of rooms, withdrawal and refunds",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "complaints_appeals_2026",
      "title": "Nakawa University Complaints, Appeals and Grievance Procedure",
      "publisher": "Office of the Academic Registrar",
      "version": "2025 Revision",
      "effective_date": "2025-08-01",
      "format": "md",
      "raw_file": "complaints_appeals_2026.md",
      "category": "procedure",
      "covers": "Informal resolution, formal complaint stages, academic appeals, grounds and time limits, outcomes and escalation",
      "provenance": "Synthetic - authored by project team, Week 1",
      "approved": true,
      "exclusion_reason": null
    },
    {
      "doc_id": "draft_fees_circular_2027",
      "title": "DRAFT Fees Circular 2026/2027 (NOT APPROVED)",
      "publisher": "Directorate of Finance",
      "version": "Draft 0.4",
      "effective_date": null,
      "format": "md",
      "raw_file": "draft_fees_circular_2027.md",
      "category": "finance",
      "covers": "Proposed fee changes for 2026/2027",
      "provenance": "Synthetic - authored by project team, Week 1, as a deliberate negative control",
      "approved": false,
      "exclusion_reason": "Unapproved draft. Senate has not ratified the 2026/2027 fees. Answering students from a draft circular would give them figures the University is not bound by, so this document is registered but excluded from the index."
    }
  ]
}
"""

EMBEDDED_CORPUS_SHA256 = "1f7f4cec2ab9cb5fefdb52c53562cca8b606a6a522755e5427850c76c5fdcfdd"

EMBEDDED_CORPUS_TAR_GZ_B64 = """
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
"""

# Where the register actually came from, reported by the CLI and recorded in
# the manifest: either a path on disk or "built-in copy".
REGISTER_SOURCE = "unresolved"

# Whether the corpus had to be unpacked from the built-in archive.
CORPUS_SOURCE = "unresolved"


def embedded_corpus_bytes() -> bytes:
    """Decode and verify the built-in corpus archive."""
    packed = base64.b64decode("".join(EMBEDDED_CORPUS_TAR_GZ_B64.split()))
    data = gzip.decompress(packed)
    digest = hashlib.sha256(data).hexdigest()
    if digest != EMBEDDED_CORPUS_SHA256:
        raise RuntimeError(
            "The built-in corpus archive failed its integrity check "
            f"(expected {EMBEDDED_CORPUS_SHA256}, got {digest}). "
            "This copy of ingest.py has been altered or truncated."
        )
    return data


def materialise_corpus(target_dir: Path) -> list[str]:
    """Write the built-in corpus into `target_dir`, returning the filenames.

    Members are written one at a time by name rather than with extractall, so
    nothing in the archive can write outside the target directory.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(embedded_corpus_bytes()), mode="r:*") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = Path(member.name).name
            handle = tar.extractfile(member)
            if handle is None:
                continue
            (target_dir / name).write_bytes(handle.read())
            written.append(name)
    return sorted(written)


def ensure_corpus_available(register: "Register") -> str:
    """Make sure every registered file is on disk, unpacking it if it is not.

    Returns a short description of where the corpus came from.
    """
    global CORPUS_SOURCE

    missing = [e.raw_file for e in register.entries if not e.path.exists()]
    if not missing:
        CORPUS_SOURCE = str(RAW_DIR)
        return CORPUS_SOURCE

    materialise_corpus(RAW_DIR)
    still_missing = [e.raw_file for e in register.entries if not e.path.exists()]
    if still_missing:
        raise FileNotFoundError(
            "These registered files are neither on disk nor in the built-in "
            f"corpus: {', '.join(still_missing)}"
        )
    CORPUS_SOURCE = f"built-in copy, unpacked into {RAW_DIR}"
    return CORPUS_SOURCE


# ==========================================================================
# 2. Chunking parameters
# ==========================================================================
#
# These values were measured on this corpus, not guessed. Chunking one section
# per chunk gives a section-length distribution of roughly: median 138 tokens,
# 90th percentile 216, maximum 327. A 200-token target therefore leaves the
# large majority of policy sections intact as single coherent chunks, while
# splitting the dozen longest sections (add/drop, academic integrity,
# examination misconduct) which are both the densest and the most frequently
# queried. It also keeps the evidence budget small: top-k of 4 x 200 tokens is
# about 800 tokens of retrieved evidence, which fits in the space the Week 2
# prompt leaves for retrieved passages.

CHUNK_TARGET_TOKENS = 200

# Hard ceiling. A section that packs past the target is still allowed to
# finish its current sentence; this bounds how far past the target that goes.
CHUNK_MAX_TOKENS = 280

# A trailing fragment smaller than this is merged back into the previous chunk
# rather than emitted as a stub that competes for retrieval while carrying
# almost no information.
CHUNK_MIN_TOKENS = 60

# Overlap carried from the end of one chunk into the start of the next, about
# 22% of the target. Policy rules state a condition in one sentence and its
# qualification in the next, so the overlap is sized to hold a complete
# sentence pair rather than a fixed character window.
CHUNK_OVERLAP_TOKENS = 45

# ==========================================================================
# 3. Token counting
# ==========================================================================
#
# Chunk sizes are specified in tokens rather than characters because the
# downstream constraint is the model's context window, which is measured in
# tokens. Exact cl100k_base counts are used when `tiktoken` and its encoding
# file are available; otherwise an offline estimator is used and the manifest
# records which counter produced the numbers.

CHARS_PER_TOKEN = 4.0
_WORD_RE = re.compile(r"\w+|[^\w\s]")


class HeuristicCounter:
    """Offline estimator: blends a character-based and a word-based estimate.

    Pure character counting under-estimates text with many short tokens
    (dates, numbers, punctuation-heavy lists); pure word counting
    under-estimates long technical words. Taking the maximum of the two is
    conservative: it never silently produces chunks larger than the stated
    budget.
    """

    name = "heuristic-chars-words"

    def count(self, text: str) -> int:
        if not text:
            return 0
        char_estimate = len(text) / CHARS_PER_TOKEN
        word_estimate = len(_WORD_RE.findall(text))
        return int(math.ceil(max(char_estimate, word_estimate)))


class TiktokenCounter:
    """Exact counts using the cl100k_base BPE encoding."""

    name = "tiktoken-cl100k_base"

    def __init__(self) -> None:
        import tiktoken  # imported lazily; may not be installed

        self._encoding = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))


def get_token_counter():
    """Return the most accurate counter available in this environment."""
    try:
        return TiktokenCounter()
    except Exception:
        return HeuristicCounter()


# Module-level singleton so the whole pipeline agrees on one counter.
COUNTER = get_token_counter()


def count_tokens(text: str) -> int:
    """Count the tokens in `text` using the active counter."""
    return COUNTER.count(text)


# ==========================================================================
# 4. The Week 1 Corpus/Source Register
# ==========================================================================
#
# Nothing reaches the chunk set unless it appears in the register with
# `approved: true`, and every skipped file is reported so the exclusion is
# visible in the ingestion log rather than silent. This is the "referencing
# the register created in Week 1" part of the task, expressed as code.


@dataclass(frozen=True)
class RegisterEntry:
    """One row of the Corpus/Source Register."""

    doc_id: str
    title: str
    publisher: str
    version: str
    effective_date: str | None
    format: str
    raw_file: str
    category: str
    covers: str
    provenance: str
    approved: bool
    exclusion_reason: str | None

    @property
    def path(self) -> Path:
        return RAW_DIR / self.raw_file


@dataclass(frozen=True)
class Register:
    """The register as a whole, plus its provenance statement."""

    register_name: str
    register_version: str
    provenance_statement: str
    entries: list[RegisterEntry]

    @property
    def approved(self) -> list[RegisterEntry]:
        return [e for e in self.entries if e.approved]

    @property
    def excluded(self) -> list[RegisterEntry]:
        return [e for e in self.entries if not e.approved]

    def get(self, doc_id: str) -> RegisterEntry:
        for entry in self.entries:
            if entry.doc_id == doc_id:
                return entry
        raise KeyError(f"'{doc_id}' is not in the Corpus/Source Register")


_ENTRY_FIELDS = {f.name for f in fields(RegisterEntry)}
_OPTIONAL_ENTRY_FIELDS = {"effective_date", "exclusion_reason"}


def _entry_from_row(row: dict) -> RegisterEntry:
    """Build a RegisterEntry from one register row, rejecting bad rows."""
    missing = _ENTRY_FIELDS - _OPTIONAL_ENTRY_FIELDS - set(row)
    if missing:
        raise ValueError(
            f"Register row {row.get('doc_id', '<no doc_id>')} is missing "
            f"required field(s): {', '.join(sorted(missing))}"
        )
    return RegisterEntry(**{key: row.get(key) for key in _ENTRY_FIELDS})


def load_register(path: Path | None = None) -> Register:
    """Read the register: from disk if it is there, otherwise the built-in copy.

    Passing an explicit `path` requires that file to exist - an explicit
    request for a register that is missing is an error, not a reason to fall
    back silently.
    """
    global REGISTER_SOURCE

    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"Corpus/Source Register not found at {path}.")
        REGISTER_SOURCE = str(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif REGISTER_PATH.exists():
        REGISTER_SOURCE = str(REGISTER_PATH)
        payload = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    else:
        REGISTER_SOURCE = "built-in copy"
        payload = json.loads(EMBEDDED_REGISTER_JSON)
    entries = [_entry_from_row(row) for row in payload["documents"]]
    return Register(
        register_name=payload["register_name"],
        register_version=str(payload["register_version"]),
        provenance_statement=payload.get("provenance_statement", ""),
        entries=entries,
    )


def validate_register(register: Register) -> list[str]:
    """Check the register against what is actually on disk.

    Returns a list of human-readable problems. An empty list means the
    register and knowledge/raw/ agree with each other.
    """
    problems: list[str] = []
    seen_ids: set[str] = set()

    for entry in register.entries:
        if entry.doc_id in seen_ids:
            problems.append(f"duplicate doc_id in register: {entry.doc_id}")
        seen_ids.add(entry.doc_id)

        if not entry.path.exists():
            problems.append(
                f"{entry.doc_id}: registered file '{entry.raw_file}' is missing "
                f"from {RAW_DIR}"
            )
            continue

        suffix = entry.path.suffix.lstrip(".").lower()
        if suffix != entry.format.lower():
            problems.append(
                f"{entry.doc_id}: register declares format '{entry.format}' "
                f"but the file on disk is '.{suffix}'"
            )

        if not entry.approved and not entry.exclusion_reason:
            problems.append(
                f"{entry.doc_id}: excluded from the corpus without a recorded reason"
            )

    registered_files = {e.raw_file for e in register.entries}
    if RAW_DIR.is_dir():
        for found in sorted(RAW_DIR.glob("*")):
            if found.is_file() and found.name not in registered_files:
                problems.append(
                    f"unregistered file present in knowledge/raw: {found.name} "
                    "(it will not be ingested)"
                )

    return problems


# ==========================================================================
# 5. Loading: PDF and Markdown -> page/section-aware blocks
# ==========================================================================
#
# The job here is not simply to get the words out of a file. It is to get them
# out together with the two pieces of provenance a student answer needs: which
# page the words were on, and which numbered section of the policy they belong
# to. Once the text is flattened, page and section cannot be recovered.

META_RE = re.compile(r"<!--\s*meta:\s*(.*?)\s*-->")
PAGE_MARKER = "<!-- page -->"
SECTION_PREFIX = "SECTION "

# "3. Course Add and Drop" -> number "3", title "Course Add and Drop"
SECTION_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+(.*)$")

# A bullet or numbered list item in extracted PDF text, marker and content on
# the same line.
PDF_LIST_RE = re.compile(r"^\s*(?:[\u2022\-]|\d+[.)])\s+")

# Some PDF producers place the bullet glyph or the list number on its own text
# line, separate from the item's text. The glyph often extracts as a control
# or private-use code point rather than a printable bullet, so the test is
# "short line that is not a normal word" rather than a fixed character set.
PDF_BARE_MARKER_RE = re.compile(r"^\s*(?:\d{1,2}[.)]?|[^\w\s]{1,2})\s*$")

# Word split across a line break by hyphenation: "with-\ndrawal".
HYPHEN_BREAK_RE = re.compile(r"(\w)-\s*$")


@dataclass
class Block:
    """A contiguous piece of text with its provenance inside the document."""

    text: str
    page: int
    section_number: str | None
    section_title: str | None
    kind: str  # "paragraph" | "list_item"

    @property
    def section(self) -> str | None:
        """Section as it should be cited, e.g. "3. Course Add and Drop"."""
        if self.section_title is None:
            return None
        if self.section_number:
            return f"{self.section_number}. {self.section_title}"
        return self.section_title


@dataclass
class LoadedDocument:
    """A whole document after loading, before cleaning and chunking."""

    doc_id: str
    source_path: Path
    page_count: int
    blocks: list[Block]
    meta: dict[str, str]

    @property
    def text(self) -> str:
        """Flat plain text, used for the human-inspectable processed/ output."""
        parts: list[str] = []
        current_section: str | None = None
        for block in self.blocks:
            if block.section != current_section:
                current_section = block.section
                if current_section:
                    parts.append(f"\n## {current_section}\n")
            prefix = "- " if block.kind == "list_item" else ""
            parts.append(f"{prefix}{block.text}")
        return "\n\n".join(p for p in parts if p.strip())


def parse_meta(text: str) -> dict[str, str]:
    """Read a `<!-- meta: k=v | k=v -->` header if the document carries one."""
    match = META_RE.search(text)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for part in match.group(1).split("|"):
        if "=" in part:
            key, value = part.split("=", 1)
            meta[key.strip()] = value.strip()
    return meta


def _split_heading(heading: str) -> tuple[str | None, str]:
    """Split "3. Course Add and Drop" into ("3", "Course Add and Drop")."""
    match = SECTION_NUMBER_RE.match(heading.strip())
    if match:
        return match.group(1), match.group(2).strip()
    return None, heading.strip()


def load_markdown(path: Path, doc_id: str) -> LoadedDocument:
    """Load a Markdown corpus document into page/section-aware blocks.

    Page boundaries are marked by `<!-- page -->`, sections by `## ` headings.
    """
    raw = path.read_text(encoding="utf-8")
    meta = parse_meta(raw)

    blocks: list[Block] = []
    page = 1
    section_number: str | None = None
    section_title: str | None = None
    buffer: list[str] = []

    def flush(kind: str = "paragraph") -> None:
        nonlocal buffer
        joined = " ".join(line.strip() for line in buffer).strip()
        if joined:
            blocks.append(
                Block(
                    text=joined,
                    page=page,
                    section_number=section_number,
                    section_title=section_title,
                    kind=kind,
                )
            )
        buffer = []

    for raw_line in raw.splitlines():
        stripped = raw_line.strip()

        if stripped == PAGE_MARKER:
            flush()
            page += 1
            continue
        if stripped.startswith("<!--"):
            continue
        if not stripped:
            flush()
            continue
        if stripped.startswith("# "):
            flush()
            continue
        if stripped.startswith("## "):
            flush()
            section_number, section_title = _split_heading(stripped[3:])
            continue
        if stripped.startswith("- ") or re.match(r"^\d+\.\s+", stripped):
            # A list item is its own block so that a rule expressed as a list
            # is never merged into the sentence that introduces it.
            flush()
            item = re.sub(r"^(?:-\s+|\d+\.\s+)", "", stripped)
            buffer = [item]
            flush(kind="list_item")
            continue

        buffer.append(stripped)

    flush()

    return LoadedDocument(
        doc_id=doc_id,
        source_path=path,
        page_count=page,
        blocks=blocks,
        meta=meta,
    )


def load_pdf(path: Path, doc_id: str) -> LoadedDocument:
    """Load a PDF corpus document into page/section-aware blocks.

    Page numbers come from the PDF page index (1-based), so a chunk can be
    cited as "Academic Handbook 2026, p. 3" and a reader can turn to that page
    and find the text. Sections are recovered from the `SECTION ` prefix the
    publisher applies to headings, because PDF text extraction loses font
    information and so cannot tell a heading from body text by style.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment problem
        raise ImportError(
            "pypdf is required to ingest the PDF documents in the corpus. "
            "Install it with: pip install pypdf"
        ) from exc

    reader = PdfReader(str(path))

    blocks: list[Block] = []
    section_number: str | None = None
    section_title: str | None = None
    meta: dict[str, str] = {}

    for page_index, pdf_page in enumerate(reader.pages, start=1):
        extracted = pdf_page.extract_text() or ""
        buffer: list[str] = []
        kind = "paragraph"
        pending_marker = False  # a bare bullet/number line was just seen

        def flush(page_no: int = page_index) -> None:
            nonlocal buffer, kind
            joined = " ".join(buffer).strip()
            joined = re.sub(r"\s{2,}", " ", joined)
            if joined:
                blocks.append(
                    Block(
                        text=joined,
                        page=page_no,
                        section_number=section_number,
                        section_title=section_title,
                        kind=kind,
                    )
                )
            buffer = []
            kind = "paragraph"

        for raw_line in extracted.splitlines():
            line = raw_line.strip()
            if not line:
                flush()
                pending_marker = False
                continue

            if line.startswith(SECTION_PREFIX):
                flush()
                pending_marker = False
                section_number, section_title = _split_heading(
                    line[len(SECTION_PREFIX):]
                )
                continue

            if PDF_LIST_RE.match(line):
                flush()
                kind = "list_item"
                buffer = [PDF_LIST_RE.sub("", line)]
                pending_marker = False
                continue

            if PDF_BARE_MARKER_RE.match(line):
                # The marker arrived on its own line; the item's text follows.
                flush()
                pending_marker = True
                continue

            if pending_marker:
                kind = "list_item"
                buffer = [line]
                pending_marker = False
                continue

            if buffer and HYPHEN_BREAK_RE.search(buffer[-1]):
                # Re-join a word broken across lines by hyphenation.
                buffer[-1] = HYPHEN_BREAK_RE.sub(r"\1", buffer[-1]) + line
            else:
                buffer.append(line)

        flush()

    return LoadedDocument(
        doc_id=doc_id,
        source_path=path,
        page_count=len(reader.pages),
        blocks=blocks,
        meta=meta,
    )


def load_document(path: Path, doc_id: str) -> LoadedDocument:
    """Dispatch to the right loader based on file extension."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path, doc_id)
    if suffix in {".md", ".markdown", ".txt"}:
        return load_markdown(path, doc_id)
    raise ValueError(
        f"No loader for '{suffix}' ({path.name}). "
        "Supported corpus formats are .pdf and .md."
    )


# ==========================================================================
# 6. Cleaning and normalisation
# ==========================================================================
#
# The aim is narrow: remove the artefacts of the file format, and nothing
# else. The policy wording itself is never rewritten, because the agent is
# expected to quote and cite these documents, and text that has been "tidied"
# cannot honestly be presented as what the University published.
#
# Front matter (the title block and publication descriptor before the first
# numbered section) is dropped: it carries no answerable policy content but
# does contain document-level keywords, so leaving it in creates chunks that
# match many queries weakly and none of them well.

# Characters that typesetting introduces and keyboards do not produce.
CHAR_REPLACEMENTS = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": " - ",
    "\u2026": "...",
    "\u00a0": " ",
    "\u2022": "-",
    "\ufb01": "fi",
    "\ufb02": "fl",
}

# A line that is nothing but a page number.
PAGE_NUMBER_RE = re.compile(r"^\s*(?:page\s*)?\d{1,3}\s*$", re.IGNORECASE)

# The publication descriptor line emitted under the document title.
DESCRIPTOR_RE = re.compile(
    r"version:\s*.+?\|\s*effective:\s*.+?\|\s*owner:\s*.+", re.IGNORECASE
)

MARKDOWN_EMPHASIS_RE = re.compile(r"\*{1,2}(.+?)\*{1,2}")
MULTISPACE_RE = re.compile(r"[ \t]{2,}")


def normalise_text(text: str) -> str:
    """Apply character, emphasis and whitespace normalisation to one string."""
    text = unicodedata.normalize("NFKC", text)
    for source, target in CHAR_REPLACEMENTS.items():
        text = text.replace(source, target)
    text = MARKDOWN_EMPHASIS_RE.sub(r"\1", text)
    text = DESCRIPTOR_RE.sub("", text)
    text = text.replace("\r", " ").replace("\n", " ")
    text = MULTISPACE_RE.sub(" ", text)
    # Space introduced before punctuation by line re-joining.
    text = re.sub(r"\s+([,.;:!?%)])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    return text.strip()


def is_noise(text: str) -> bool:
    """True if a block carries no answerable content."""
    if not text or len(text) < 3:
        return True
    if PAGE_NUMBER_RE.match(text):
        return True
    if not re.search(r"[A-Za-z]", text):
        return True
    return False


def clean_blocks(blocks: list[Block], drop_front_matter: bool = True) -> list[Block]:
    """Clean a document's blocks, dropping noise and optionally front matter."""
    cleaned: list[Block] = []
    seen_first_section = False

    for block in blocks:
        if block.section_title is not None:
            seen_first_section = True
        elif drop_front_matter and not seen_first_section:
            continue  # title block / descriptor before section 1

        text = normalise_text(block.text)
        if is_noise(text):
            continue

        cleaned.append(
            Block(
                text=text,
                page=block.page,
                section_number=block.section_number,
                section_title=block.section_title,
                kind=block.kind,
            )
        )

    return cleaned


def clean_document(document: LoadedDocument) -> LoadedDocument:
    """Return a copy of `document` with its blocks cleaned."""
    return LoadedDocument(
        doc_id=document.doc_id,
        source_path=document.source_path,
        page_count=document.page_count,
        blocks=clean_blocks(document.blocks),
        meta=document.meta,
    )


# ==========================================================================
# 7. Chunking
# ==========================================================================
#
# Strategy: section-aware sentence packing with sentence-level overlap.
#
# 1. Chunks never cross a section boundary. University policy is written so
#    that a numbered section is a self-contained rule. A chunk that begins in
#    "6. Grading Scheme" and ends in "7. Retakes and Progression" would
#    produce an answer that cites one section while quoting another - exactly
#    the mis-grounding the evaluation suite is meant to catch.
# 2. Within a section, sentences are packed into a chunk until the token
#    target is reached, so a chunk never ends mid-rule.
# 3. Consecutive chunks overlap by whole sentences, so a condition and its
#    qualifying clause stay together in at least one chunk.
# 4. A trailing fragment below the minimum size is merged back into the
#    previous chunk instead of becoming a stub.
# 5. A single sentence larger than the hard ceiling is split on word
#    boundaries as a last resort.

# Sentence boundary: terminal punctuation followed by whitespace and a capital
# letter, a digit or an opening quote.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'(]?[A-Z0-9])")

# Abbreviations and section references ("s. 4", "No. 12", "p. 42") that must
# not be mistaken for the end of a sentence.
ABBREVIATIONS = {
    "s.", "ss.", "no.", "p.", "pp.", "art.", "reg.", "para.",
    "e.g.", "i.e.", "cf.", "vs.", "dr.", "prof.", "mr.", "mrs.", "ms.",
}


@dataclass
class Chunk:
    """One retrievable unit of the knowledge corpus."""

    chunk_id: str
    text: str

    # Document provenance (from the Corpus/Source Register).
    doc_id: str
    doc_title: str
    publisher: str
    version: str
    effective_date: str | None
    category: str
    source_file: str
    source_format: str

    # Position within the document.
    section_number: str | None
    section_title: str | None
    page_start: int
    page_end: int
    chunk_index: int

    # Measurements.
    token_count: int
    char_count: int
    content_hash: str

    # Human-readable citation used in the agent's answer.
    citation: str

    overlap_with_previous: bool = False
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def section(self) -> str | None:
        if self.section_title is None:
            return None
        if self.section_number:
            return f"{self.section_number}. {self.section_title}"
        return self.section_title


def split_sentences(text: str) -> list[str]:
    """Split a block of text into sentences, respecting common abbreviations."""
    if not text.strip():
        return []

    candidates = SENTENCE_SPLIT_RE.split(text.strip())
    sentences: list[str] = []

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        # Re-join a false split caused by an abbreviation ending the previous
        # fragment, e.g. "... under s." + "4 of the Regulations ...".
        if sentences:
            tail = sentences[-1].split()[-1].lower() if sentences[-1].split() else ""
            if tail in ABBREVIATIONS:
                sentences[-1] = f"{sentences[-1]} {candidate}"
                continue
        sentences.append(candidate)

    return sentences


def _hard_split(sentence: str, limit: int) -> list[str]:
    """Split an over-long sentence on word boundaries as a last resort."""
    words = sentence.split()
    pieces: list[str] = []
    current: list[str] = []

    for word in words:
        current.append(word)
        if count_tokens(" ".join(current)) >= limit:
            pieces.append(" ".join(current))
            current = []

    if current:
        pieces.append(" ".join(current))
    return pieces


def _citation_for(
    entry: RegisterEntry,
    section_number: str | None,
    section_title: str | None,
    page_start: int,
    page_end: int,
) -> str:
    """Build the citation string shown to the student."""
    parts = [entry.title]
    if section_number and section_title:
        parts.append(f"s. {section_number} ({section_title})")
    elif section_title:
        parts.append(section_title)
    if page_start == page_end:
        parts.append(f"p. {page_start}")
    else:
        parts.append(f"pp. {page_start}-{page_end}")
    return ", ".join(parts)


@dataclass
class _Unit:
    """A sentence together with the page it came from."""

    text: str
    page: int
    tokens: int


def _units_for_section(blocks: Iterable[Block]) -> list[_Unit]:
    """Flatten a section's blocks into page-tagged sentence units."""
    units: list[_Unit] = []
    for block in blocks:
        pieces = (
            [block.text] if block.kind == "list_item" else split_sentences(block.text)
        )
        for piece in pieces:
            tokens = count_tokens(piece)
            if tokens > CHUNK_MAX_TOKENS:
                for sub in _hard_split(piece, CHUNK_TARGET_TOKENS):
                    units.append(_Unit(sub, block.page, count_tokens(sub)))
            else:
                units.append(_Unit(piece, block.page, tokens))
    return units


def _overlap_units(units: list[_Unit], budget: int) -> list[_Unit]:
    """Take whole sentences from the end of a chunk, up to the token budget."""
    if budget <= 0:
        return []
    taken: list[_Unit] = []
    total = 0
    for unit in reversed(units):
        if total + unit.tokens > budget and taken:
            break
        taken.insert(0, unit)
        total += unit.tokens
        if total >= budget:
            break
    # Never carry the entire previous chunk forward.
    if len(taken) == len(units) and len(units) > 1:
        taken = taken[1:]
    return taken


def chunk_document(
    blocks: list[Block],
    entry: RegisterEntry,
    register_version: str = "1.0",
) -> list[Chunk]:
    """Chunk one cleaned document into retrievable units with metadata."""
    # Group consecutive blocks by section, preserving document order.
    sections: list[tuple[str | None, str | None, list[Block]]] = []
    for block in blocks:
        key = (block.section_number, block.section_title)
        if sections and (sections[-1][0], sections[-1][1]) == key:
            sections[-1][2].append(block)
        else:
            sections.append((block.section_number, block.section_title, [block]))

    chunks: list[Chunk] = []
    sequence = 0

    for section_number, section_title, section_blocks in sections:
        units = _units_for_section(section_blocks)
        if not units:
            continue

        packed: list[list[_Unit]] = []
        current: list[_Unit] = []
        current_tokens = 0
        carried = 0  # tokens of the current chunk that are overlap

        for unit in units:
            if current and current_tokens + unit.tokens > CHUNK_TARGET_TOKENS:
                packed.append(current)
                overlap = _overlap_units(current, CHUNK_OVERLAP_TOKENS)
                current = list(overlap)
                current_tokens = sum(u.tokens for u in overlap)
                carried = current_tokens
            current.append(unit)
            current_tokens += unit.tokens

        if current:
            # Merge a too-small tail back into the previous chunk when the
            # combined size still fits under the hard ceiling.
            real_tokens = current_tokens - carried
            if packed and real_tokens < CHUNK_MIN_TOKENS:
                previous_tokens = sum(u.tokens for u in packed[-1])
                new_units = [u for u in current if u not in packed[-1]]
                if previous_tokens + sum(u.tokens for u in new_units) <= CHUNK_MAX_TOKENS:
                    packed[-1] = packed[-1] + new_units
                else:
                    packed.append(current)
            else:
                packed.append(current)

        for position, group in enumerate(packed):
            text = " ".join(u.text for u in group).strip()
            if not text:
                continue
            page_start = min(u.page for u in group)
            page_end = max(u.page for u in group)

            chunks.append(
                Chunk(
                    chunk_id=f"{entry.doc_id}_{sequence:03d}",
                    text=text,
                    doc_id=entry.doc_id,
                    doc_title=entry.title,
                    publisher=entry.publisher,
                    version=entry.version,
                    effective_date=entry.effective_date,
                    category=entry.category,
                    source_file=entry.raw_file,
                    source_format=entry.format,
                    section_number=section_number,
                    section_title=section_title,
                    page_start=page_start,
                    page_end=page_end,
                    chunk_index=sequence,
                    token_count=count_tokens(text),
                    char_count=len(text),
                    content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                    citation=_citation_for(
                        entry, section_number, section_title, page_start, page_end
                    ),
                    overlap_with_previous=position > 0,
                    tags=[entry.category, f"register_v{register_version}"],
                )
            )
            sequence += 1

    return chunks


# ==========================================================================
# 8. The ingestion pipeline
# ==========================================================================


def ingest_corpus(register: Register, write: bool = True) -> tuple[list[Chunk], dict]:
    """Ingest every approved document in the register.

    Returns the chunks and a manifest describing the run. Every decision that
    affects the output is recorded in the manifest, so the chunk set can be
    traced back to the register version, the chunking parameters and the token
    counter that produced it.
    """
    ensure_corpus_available(register)

    all_chunks: list[Chunk] = []
    per_document: list[dict] = []

    if write:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    for entry in register.approved:
        loaded = load_document(entry.path, entry.doc_id)
        cleaned = clean_document(loaded)

        if write:
            processed_path = PROCESSED_DIR / f"{entry.doc_id}.txt"
            processed_path.write_text(cleaned.text, encoding="utf-8")

        chunks = chunk_document(
            cleaned.blocks, entry, register_version=register.register_version
        )
        all_chunks.extend(chunks)

        token_counts = [c.token_count for c in chunks]
        per_document.append(
            {
                "doc_id": entry.doc_id,
                "title": entry.title,
                "format": entry.format,
                "source_file": entry.raw_file,
                "pages": cleaned.page_count,
                "blocks_after_cleaning": len(cleaned.blocks),
                "sections": len(
                    {b.section for b in cleaned.blocks if b.section is not None}
                ),
                "chunks": len(chunks),
                "tokens_total": sum(token_counts),
                "tokens_mean": round(statistics.mean(token_counts), 1)
                if token_counts
                else 0,
                "tokens_min": min(token_counts) if token_counts else 0,
                "tokens_max": max(token_counts) if token_counts else 0,
            }
        )

        print(
            f"  {entry.doc_id:<32} {entry.format:<4} "
            f"{cleaned.page_count:>2} pages  "
            f"{len(cleaned.blocks):>3} blocks  "
            f"{len(chunks):>3} chunks"
        )

    skipped = [
        {
            "doc_id": entry.doc_id,
            "title": entry.title,
            "reason": entry.exclusion_reason,
        }
        for entry in register.excluded
    ]

    token_counts = [c.token_count for c in all_chunks]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/rag/ingest.py",
        "register": {
            "name": register.register_name,
            "version": register.register_version,
            "loaded_from": REGISTER_SOURCE,
            "corpus_read_from": CORPUS_SOURCE,
            "documents_registered": len(register.entries),
            "documents_ingested": len(register.approved),
            "documents_skipped": skipped,
        },
        "chunking_strategy": {
            "method": "section-aware sentence packing with sentence-level overlap",
            "target_tokens": CHUNK_TARGET_TOKENS,
            "max_tokens": CHUNK_MAX_TOKENS,
            "min_tokens": CHUNK_MIN_TOKENS,
            "overlap_tokens": CHUNK_OVERLAP_TOKENS,
            "boundaries_respected": ["document", "section"],
            "token_counter": COUNTER.name,
        },
        "totals": {
            "chunks": len(all_chunks),
            "tokens": sum(token_counts),
            "tokens_mean": round(statistics.mean(token_counts), 1)
            if token_counts
            else 0,
            "tokens_median": statistics.median(token_counts) if token_counts else 0,
            "tokens_min": min(token_counts) if token_counts else 0,
            "tokens_max": max(token_counts) if token_counts else 0,
            "chunks_with_overlap": sum(1 for c in all_chunks if c.overlap_with_previous),
        },
        "documents": per_document,
    }

    if write:
        with CHUNKS_PATH.open("w", encoding="utf-8") as handle:
            for chunk in all_chunks:
                handle.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
        CHUNK_MANIFEST_PATH.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return all_chunks, manifest


def load_chunks(path: Path | None = None) -> list[Chunk]:
    """Read chunks back from disk (used by indexing, retrieval and tests)."""
    path = path or CHUNKS_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python src/rag/ingest.py` first."
        )
    chunks: list[Chunk] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                chunks.append(Chunk(**json.loads(line)))
    return chunks


# ==========================================================================
# 9. Command line entry point
# ==========================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest and chunk the knowledge corpus (BSE4104, Week 3 Task 1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run the pipeline and report, but write nothing to disk",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="only check the register against knowledge/raw/, then exit",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="project root containing docs/, knowledge/ and data/ "
        "(default: auto-detected)",
    )
    args = parser.parse_args(argv)

    if args.root is not None:
        _set_project_root(args.root.expanduser().resolve())

    print(f"Project root: {PROJECT_ROOT}")
    register = load_register()
    print(f"Register: {register.register_name} (v{register.register_version})")
    print(f"Register source: {REGISTER_SOURCE}")
    print(f"Corpus source: {ensure_corpus_available(register)}")

    problems = validate_register(register)
    if problems:
        print("\nRegister validation failed:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        f"Register validated: {len(register.approved)} approved, "
        f"{len(register.excluded)} excluded\n"
    )

    if args.validate:
        return 0

    for entry in register.excluded:
        print(f"  SKIPPED {entry.doc_id}: {entry.exclusion_reason}")
    if register.excluded:
        print()

    chunks, manifest = ingest_corpus(register, write=not args.dry_run)

    totals = manifest["totals"]
    print(
        f"\n{totals['chunks']} chunks | {totals['tokens']} tokens | "
        f"mean {totals['tokens_mean']} | median {totals['tokens_median']} | "
        f"range {totals['tokens_min']}-{totals['tokens_max']} | "
        f"{totals['chunks_with_overlap']} carry overlap"
    )
    print(f"Token counter: {manifest['chunking_strategy']['token_counter']}")

    if args.dry_run:
        print("\nDry run - nothing written.")
    else:
        print(f"\nWrote {CHUNKS_PATH}")
        print(f"Wrote {CHUNK_MANIFEST_PATH}")
        print(f"Wrote {PROCESSED_DIR}/*.txt")

    return 0


def _set_project_root(root: Path) -> None:
    """Point every path in this module at a different project root."""
    global PROJECT_ROOT, REGISTER_PATH, RAW_DIR, PROCESSED_DIR
    global DATA_DIR, CHUNKS_PATH, CHUNK_MANIFEST_PATH

    PROJECT_ROOT = root
    REGISTER_PATH = PROJECT_ROOT / "docs" / "corpus_source_register.json"
    RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
    PROCESSED_DIR = PROJECT_ROOT / "knowledge" / "processed"
    DATA_DIR = PROJECT_ROOT / "data"
    CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
    CHUNK_MANIFEST_PATH = DATA_DIR / "chunk_manifest.json"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # Output was piped into something that closed early (e.g. `| head`).
        raise SystemExit(0)
