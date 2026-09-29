"""
src/rag/retriever.py - Vector Store Setup and Retrieval Pipeline.

BSE4104 Agentic AI Capstone - University Student-Support Case Agent.
Week 3, Task 2: "Vector Store Setup & Retrieval Pipeline".

What this file does
-------------------
It initialises the local vector index over the chunks produced by
`src/rag/ingest.py` and implements top-k semantic retrieval with similarity
thresholds, so that answers to student policy questions are grounded in
approved sources - or honestly refused.

    data/chunks.jsonl                     (output of Task 1)
          |
          v
    fit TF-IDF + Truncated SVD         -> data/vector_store/embedder.joblib
          |
          v
    embed every chunk, index in ChromaDB -> data/vector_store/chroma/
          |                                data/vector_store/index_report.json
          v
    question -> embed -> cosine nearest neighbours (candidate pool)
          |
          v
    re-rank: hybrid score = 0.6 * dense + 0.4 * lexical
          |
          v
    apply thresholds
          |
          +--> nothing clears the floor  -> status "ungrounded", no passages
          +--> clears it but weakly      -> status "weak", passages flagged
          +--> clears the strong bar     -> status "grounded", top-k passages

This file is completely self-contained. The embedder, the vector store wrapper,
the grounding signal and the retriever all live here, and so does the chunked
corpus itself (section 1b), so the file runs on its own in an empty directory
with no other project file present. When data/chunks.jsonl is there - because
ingest.py has been run - that file is used instead of the built-in copy, so a
change to the corpus flows straight through to the index.

Usage
-----
    # just ask - the index is built automatically on first use
    python src/rag/retriever.py "When is the add drop deadline?"

    # or build the index explicitly (e.g. after re-running ingest.py)
    python src/rag/retriever.py --build
    python src/rag/retriever.py "How do I appeal a grade?" --top-k 3
    python src/rag/retriever.py "What are the library fines?" --doc library_services_2026
    python src/rag/retriever.py "Can I get a parking permit?" --json

Or as a library:

    from retriever import Retriever
    result = Retriever().retrieve("When is the add drop deadline?")
    if result.is_grounded:
        for passage in result.passages:
            print(passage.citation, passage.text)

Requirements: scikit-learn and numpy (which bring in scipy and joblib).
chromadb is used when it is installed; when it is not, the same interface is
served from a built-in NumPy embeddings cache that returns identical rankings
and identical cosine distances, so the file still runs. Set
RAG_VECTOR_BACKEND=chroma or =numpy to pin one explicitly.

Owner: Pauline Peace (PP).
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.preprocessing import normalize

# ==========================================================================
# 1. Project paths
# ==========================================================================


def find_project_root(start: Path | None = None) -> Path:
    """Locate the project root.

    Resolution order:
      1. the RAG_PROJECT_ROOT environment variable, if set;
      2. the nearest ancestor directory holding data/chunks.jsonl, the Week 1
         register at docs/corpus_source_register.json, or knowledge/raw/;
      3. two levels above this file (i.e. the parent of src/).
    """
    env_root = os.environ.get("RAG_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / "data" / "chunks.jsonl").exists():
            return candidate
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

    The index and the fitted embedder have to be written somewhere. If this
    file is run from a place it cannot write to, they go under the system
    temporary directory instead of the run failing.
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

DATA_DIR = PROJECT_ROOT / "data"
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
CHUNK_MANIFEST_PATH = DATA_DIR / "chunk_manifest.json"

VECTOR_STORE_DIR = DATA_DIR / "vector_store"
CHROMA_DIR = VECTOR_STORE_DIR / "chroma"
EMBEDDER_PATH = VECTOR_STORE_DIR / "embedder.joblib"
INDEX_REPORT_PATH = VECTOR_STORE_DIR / "index_report.json"

COLLECTION_NAME = "university_policy_corpus"

# ==========================================================================
# 1b. Built-in copy of the chunked corpus
# ==========================================================================
#
# This file is submitted on its own, so it carries its own input: the 101
# chunks produced by src/rag/ingest.py, gzipped and base64-encoded below.
#
# Disk always wins. If data/chunks.jsonl exists - because ingest.py has been
# run in this project - that file is used, so a change to the corpus flows
# straight through to the index. The built-in copy is only used when the file
# is not there, which is what makes `python retriever.py "question"` work from
# an empty directory.
#
# The payload is checked against a SHA-256 digest before use, so a corrupted
# copy of this file fails loudly instead of quietly indexing damaged text.

EMBEDDED_CHUNKS_SHA256 = "1dbd56668d0efdc6252e0d5bda5b2dec6c53caac2af1175a1fd41130ab0d25b5"

EMBEDDED_CHUNKS_JSONL_GZ_B64 = """
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
"""

# Where the chunks actually came from, reported by the CLI and recorded in the
# index report.
CHUNKS_SOURCE = "unresolved"


def embedded_chunks_bytes() -> bytes:
    """Decode and verify the built-in chunk file."""
    packed = base64.b64decode("".join(EMBEDDED_CHUNKS_JSONL_GZ_B64.split()))
    data = gzip.decompress(packed)
    digest = hashlib.sha256(data).hexdigest()
    if digest != EMBEDDED_CHUNKS_SHA256:
        raise RuntimeError(
            "The built-in chunk archive failed its integrity check "
            f"(expected {EMBEDDED_CHUNKS_SHA256}, got {digest}). "
            "This copy of retriever.py has been altered or truncated."
        )
    return data


# ==========================================================================
# 2. Embedding parameters
# ==========================================================================

# Requested dimensionality of the dense vector produced by TF-IDF + Truncated
# SVD (LSA). SVD cannot return more components than min(n_chunks, n_features)
# - 1, so with a deliberately small corpus the embedder clamps this and
# reports the effective dimensionality in the index report.
EMBEDDING_DIM = 128

# Fixed seed so that rebuilding the index produces identical vectors.
EMBEDDING_RANDOM_STATE = 42

# n-gram range for the TF-IDF stage. Bigrams matter because university policy
# language is full of two-word terms ("add/drop", "grade point",
# "supplementary examination").
TFIDF_NGRAM_RANGE = (1, 2)

EMBEDDING_MODEL_NAME = "tfidf-svd-lsa-v1"

# ==========================================================================
# 3. Retrieval parameters
# ==========================================================================

# Number of chunks fetched from the vector store before re-ranking.
CANDIDATE_POOL = 12

# Number of chunks finally handed to the model as evidence.
TOP_K = 4

# Hybrid score weights. The dense (semantic) component handles paraphrase; the
# sparse (lexical) component protects exact policy terms from being smoothed
# away by dimensionality reduction.
DENSE_WEIGHT = 0.6
SPARSE_WEIGHT = 0.4

# Relevance floor. Below this, nothing in the corpus is even topically related
# and no passages are returned at all.
#
# Calibrated against 23 answerable and 10 unanswerable questions. The measured
# hybrid-score ranges were:
#     answerable   0.248 - 0.669
#     unanswerable 0.281 - 0.569
# Those ranges overlap, so similarity alone cannot decide whether to answer.
# The floor is therefore set just below the weakest genuinely answerable
# question rather than high enough to exclude the unanswerable ones, and the
# coverage signal below carries the rest of the judgement.
SIMILARITY_THRESHOLD = 0.24

# Above this score AND above COVERAGE_THRESHOLD, a retrieval is reported as
# "grounded". Anything in between is "weak": the passages are still returned,
# but flagged so the agent verifies them and hedges rather than asserting.
STRONG_EVIDENCE_THRESHOLD = 0.40

# Minimum share of the question's content words that must appear in the
# retrieved evidence for the result to count as grounded. See section 6 for
# why this second signal exists and why it is a reported confidence label
# rather than a hard gate.
COVERAGE_THRESHOLD = 0.70

# ==========================================================================
# 4. Embeddings
# ==========================================================================
#
# The embedding model is TF-IDF followed by Truncated SVD (Latent Semantic
# Analysis), producing a dense, L2-normalised vector per chunk, fitted on the
# project's own corpus. It was chosen over a pre-trained transformer encoder
# for reasons that are properties of this project:
#
# * It runs offline and installs from the standard scientific Python stack, so
#   the agent is reproducible by every group member and by the marker without
#   a model download or an embedding API key.
# * It is deterministic. With a fixed seed the same corpus produces identical
#   vectors, so a retrieval result recorded in the evaluation suite can be
#   reproduced exactly later.
# * The corpus is a single narrow domain with a small, repetitive vocabulary.
#   LSA over 12 policy documents captures that domain's term co-occurrence
#   structure well: "withdraw", "withdrawal" and "drop" occur with the same
#   surrounding vocabulary and end up close in the reduced space.
# * There is no token cost and no data leaves the machine, which matters
#   because the wider agent handles student case data.
#
# Its known weakness is that it cannot recognise a paraphrase that shares no
# vocabulary with the source document and never co-occurs with it in the
# corpus. The hybrid retriever below mitigates it, and this interface is
# narrow enough that the model can be swapped for a transformer encoder later
# without touching the vector store or the retriever.
#
# Two deliberate configuration choices:
#
# * No stop-word removal. Standard English stop lists delete "may", "must",
#   "not" and "only". In policy text those words carry the rule: "a student
#   may not drop a core course" and "a student may drop a core course" would
#   otherwise become identical.
# * Unigrams and bigrams, because two-word policy terms do not mean the sum of
#   their parts.


@dataclass
class EmbedderInfo:
    """Facts about a fitted embedder, recorded in the index report."""

    model_name: str
    requested_dim: int
    effective_dim: int
    vocabulary_size: int
    documents_fitted: int
    explained_variance: float
    random_state: int

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "requested_dim": self.requested_dim,
            "effective_dim": self.effective_dim,
            "vocabulary_size": self.vocabulary_size,
            "documents_fitted": self.documents_fitted,
            "explained_variance": round(self.explained_variance, 4),
            "random_state": self.random_state,
        }


class CorpusEmbedder:
    """TF-IDF + SVD embedder fitted on the knowledge corpus."""

    def __init__(
        self,
        dim: int = EMBEDDING_DIM,
        ngram_range: tuple[int, int] = TFIDF_NGRAM_RANGE,
        random_state: int = EMBEDDING_RANDOM_STATE,
    ) -> None:
        self.requested_dim = dim
        self.random_state = random_state
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=ngram_range,
            sublinear_tf=True,      # dampens repeated boilerplate terms
            min_df=1,               # the corpus is small; rare terms are signal
            stop_words=None,        # see section note: modal verbs matter
            token_pattern=r"(?u)\b\w[\w/\-]+\b",  # keeps "add/drop", "re-sit"
        )
        self.svd: TruncatedSVD | None = None
        self.info: EmbedderInfo | None = None

    # -- fitting ---------------------------------------------------------

    def fit(self, texts: list[str]) -> "CorpusEmbedder":
        """Fit the vectorizer and the SVD projection on the corpus chunks."""
        if not texts:
            raise ValueError("Cannot fit the embedder on an empty corpus.")

        tfidf = self.vectorizer.fit_transform(texts)
        n_samples, n_features = tfidf.shape

        # Truncated SVD cannot produce more components than the smaller
        # dimension of the matrix. With a small corpus this bound binds, so
        # the effective dimensionality is clamped and reported rather than
        # silently failing.
        effective_dim = min(self.requested_dim, n_samples - 1, n_features - 1)
        if effective_dim < 2:
            raise ValueError(
                f"Corpus too small to embed: {n_samples} chunks, {n_features} features."
            )

        self.svd = TruncatedSVD(
            n_components=effective_dim,
            random_state=self.random_state,
            algorithm="randomized",
            n_iter=10,
        )
        self.svd.fit(tfidf)

        self.info = EmbedderInfo(
            model_name=EMBEDDING_MODEL_NAME,
            requested_dim=self.requested_dim,
            effective_dim=effective_dim,
            vocabulary_size=n_features,
            documents_fitted=n_samples,
            explained_variance=float(self.svd.explained_variance_ratio_.sum()),
            random_state=self.random_state,
        )
        return self

    # -- transforming ----------------------------------------------------

    def _dense(self, texts: list[str]) -> np.ndarray:
        if self.svd is None:
            raise RuntimeError("Embedder is not fitted. Call fit() or load().")
        tfidf = self.vectorizer.transform(texts)
        dense = self.svd.transform(tfidf)
        # L2 normalisation makes the dot product equal cosine similarity,
        # which is what the vector store is configured to use.
        return normalize(dense).astype(np.float32)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """Embed corpus chunks. Shape: (n_texts, effective_dim)."""
        return self._dense(texts)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single student question. Shape: (effective_dim,)."""
        return self._dense([text])[0]

    def lexical_similarity(self, query: str, texts: list[str]) -> np.ndarray:
        """Cosine similarity between the query and each text in TF-IDF space.

        This is the component that protects exact policy vocabulary. SVD
        compresses the corpus into a low-rank space and can blur a rare but
        decisive term; the sparse space still has that term as its own
        dimension.
        """
        if not texts:
            return np.zeros(0, dtype=np.float32)
        query_vector = normalize(self.vectorizer.transform([query]))
        text_vectors = normalize(self.vectorizer.transform(texts))
        similarities = (text_vectors @ query_vector.T).toarray()
        return np.asarray(similarities).ravel().astype(np.float32)

    # -- persistence -----------------------------------------------------

    def save(self, path: Path | None = None) -> Path:
        """Persist the fitted embedder next to the vector index."""
        import joblib

        path = path or EMBEDDER_PATH
        if self.svd is None or self.info is None:
            raise RuntimeError("Refusing to save an unfitted embedder.")
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "vectorizer": self.vectorizer,
                "svd": self.svd,
                "info": self.info,
                "requested_dim": self.requested_dim,
                "random_state": self.random_state,
            },
            path,
        )
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "CorpusEmbedder":
        """Load a previously fitted embedder."""
        import joblib

        path = path or EMBEDDER_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"No fitted embedder at {path}. "
                "Run `python src/rag/retriever.py --build` first."
            )
        payload = joblib.load(path)
        embedder = cls(
            dim=payload["requested_dim"], random_state=payload["random_state"]
        )
        embedder.vectorizer = payload["vectorizer"]
        embedder.svd = payload["svd"]
        embedder.info = payload["info"]
        return embedder


# ==========================================================================
# 5. Vector store
# ==========================================================================
#
# ChromaDB was chosen from the options named in the task (ChromaDB, FAISS, or
# an embeddings cache) because it is the only one of the three that stores the
# chunk text and its metadata alongside the vector. Source grounding is the
# point of this pipeline: a retrieval result has to come back carrying its
# document, section and page, not just a row index that the application then
# has to look up in a side table it could get out of sync with. FAISS would
# require exactly that side table.
#
# The collection is configured for cosine distance, which matches the
# L2-normalised vectors the embedder produces. Vectors are computed by
# CorpusEmbedder and passed in explicitly rather than letting Chroma call its
# own default embedding function, so the embedding model stays under the
# project's control and the store never silently downloads one.

# Metadata fields carried into the store. Chroma metadata values must be
# scalars, so list-valued fields are flattened on the way in.
METADATA_FIELDS = (
    "doc_id",
    "doc_title",
    "category",
    "source_url",
    "retrieval_priority_tier",
    "section_title",
    "chunk_index",
    "chunk_kind",
    "token_count",
    "content_hash",
    "citation",
    "overlap_with_previous",
)


@dataclass
class StoredChunk:
    """A chunk as it comes back out of the vector store."""

    chunk_id: str
    text: str
    metadata: dict[str, Any]
    distance: float | None = None


def _to_metadata(chunk: dict) -> dict[str, Any]:
    """Flatten a chunk record's metadata into Chroma-compatible scalars."""
    metadata: dict[str, Any] = {}
    for name in METADATA_FIELDS:
        value = chunk.get(name)
        # Chroma rejects None; an empty string keeps the key present so
        # downstream code can rely on the schema being stable.
        metadata[name] = "" if value is None else value
    metadata["tags"] = "|".join(chunk.get("tags") or [])
    return metadata


class VectorStore:
    """Thin, explicit wrapper over a persistent Chroma collection."""

    backend = "chromadb (PersistentClient)"

    def __init__(
        self,
        persist_dir: Path | None = None,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:  # handled by create_store()
            raise ImportError(
                "chromadb is not installed. Install it with `pip install chromadb`, "
                "or set RAG_VECTOR_BACKEND=numpy to use the built-in embeddings "
                "cache instead."
            ) from exc

        self.persist_dir = persist_dir or CHROMA_DIR
        self.collection_name = collection_name
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # -- writing ---------------------------------------------------------

    def reset(self) -> None:
        """Drop and recreate the collection so a rebuild is never additive.

        An additive rebuild would leave chunks from a previous corpus version
        in the store, and the agent would then cite a policy the register no
        longer approves.
        """
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        chunks: list[dict],
        embeddings: np.ndarray,
        batch_size: int = 100,
    ) -> int:
        """Index chunk records with their pre-computed embeddings."""
        if len(chunks) != embeddings.shape[0]:
            raise ValueError(
                f"{len(chunks)} chunks but {embeddings.shape[0]} embeddings."
            )

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            self.collection.add(
                ids=[c["chunk_id"] for c in batch],
                documents=[c["text"] for c in batch],
                embeddings=embeddings[start : start + batch_size].tolist(),
                metadatas=[_to_metadata(c) for c in batch],
            )
        return self.collection.count()

    # -- reading ---------------------------------------------------------

    def count(self) -> int:
        return self.collection.count()

    def query(
        self,
        embedding: np.ndarray,
        n_results: int = CANDIDATE_POOL,
        where: dict | None = None,
    ) -> list[StoredChunk]:
        """Nearest-neighbour search, optionally filtered by metadata.

        `where` supports filters such as {"doc_id": "fees_policy_2026"} or
        {"category": "assessment"}, which is what lets the agent scope a
        search to, say, examination rules only.
        """
        n_results = min(n_results, max(self.count(), 1))
        response = self.collection.query(
            query_embeddings=[embedding.tolist()],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        results: list[StoredChunk] = []
        for chunk_id, text, metadata, distance in zip(
            response["ids"][0],
            response["documents"][0],
            response["metadatas"][0],
            response["distances"][0],
        ):
            results.append(
                StoredChunk(
                    chunk_id=chunk_id,
                    text=text,
                    metadata=dict(metadata),
                    distance=float(distance),
                )
            )
        return results

    def get_by_id(self, chunk_id: str) -> StoredChunk | None:
        response = self.collection.get(
            ids=[chunk_id], include=["documents", "metadatas"]
        )
        if not response["ids"]:
            return None
        return StoredChunk(
            chunk_id=response["ids"][0],
            text=response["documents"][0],
            metadata=dict(response["metadatas"][0]),
        )

    def stats(self) -> dict[str, Any]:
        """Summary of what is indexed, used by the build report and tests."""
        response = self.collection.get(include=["metadatas"])
        metadatas = response["metadatas"]
        by_document: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for metadata in metadatas:
            by_document[metadata["doc_id"]] = by_document.get(metadata["doc_id"], 0) + 1
            by_category[metadata["category"]] = (
                by_category.get(metadata["category"], 0) + 1
            )
        return {
            "collection": self.collection_name,
            "persist_dir": str(self.persist_dir),
            "chunks": len(metadatas),
            "documents": len(by_document),
            "chunks_per_document": dict(sorted(by_document.items())),
            "chunks_per_category": dict(sorted(by_category.items())),
        }


class NumpyVectorStore:
    """Fallback vector store: a persistent embeddings cache over NumPy.

    The task allows "ChromaDB, FAISS, or an embeddings cache". ChromaDB is the
    default because it stores text and metadata alongside the vector, but it is
    a sizeable install, and this file has to run wherever it is submitted. If
    chromadb is not importable, the same interface is served from a single .npz
    file holding the embedding matrix plus a JSON sidecar holding the chunk
    text and metadata.

    With 101 L2-normalised vectors an exhaustive dot product is exact and
    instant, so this fallback returns the same ranking and the same cosine
    distances as the Chroma collection - not an approximation of them.
    """

    backend = "numpy embeddings cache"

    def __init__(
        self,
        persist_dir: Path | None = None,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self.persist_dir = persist_dir or CHROMA_DIR.parent / "numpy_index"
        self.collection_name = collection_name
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.vectors_path = self.persist_dir / f"{collection_name}.npz"
        self.records_path = self.persist_dir / f"{collection_name}.json"
        self._vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self._records: list[dict] = []
        self._load()

    # -- persistence -----------------------------------------------------

    def _load(self) -> None:
        if self.vectors_path.exists() and self.records_path.exists():
            self._vectors = np.load(self.vectors_path)["embeddings"].astype(np.float32)
            self._records = json.loads(self.records_path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        np.savez_compressed(self.vectors_path, embeddings=self._vectors)
        self.records_path.write_text(
            json.dumps(self._records, ensure_ascii=False), encoding="utf-8"
        )

    # -- writing ---------------------------------------------------------

    def reset(self) -> None:
        """Drop the index so a rebuild is never additive."""
        self._vectors = np.zeros((0, 0), dtype=np.float32)
        self._records = []
        for path in (self.vectors_path, self.records_path):
            if path.exists():
                path.unlink()

    def add_chunks(
        self,
        chunks: list[dict],
        embeddings: np.ndarray,
        batch_size: int = 100,  # accepted for interface parity; unused here
    ) -> int:
        if len(chunks) != embeddings.shape[0]:
            raise ValueError(
                f"{len(chunks)} chunks but {embeddings.shape[0]} embeddings."
            )
        new_records = [
            {
                "chunk_id": c["chunk_id"],
                "text": c["text"],
                "metadata": _to_metadata(c),
            }
            for c in chunks
        ]
        if self._records:
            self._vectors = np.vstack([self._vectors, embeddings.astype(np.float32)])
            self._records.extend(new_records)
        else:
            self._vectors = embeddings.astype(np.float32)
            self._records = new_records
        self._save()
        return len(self._records)

    # -- reading ---------------------------------------------------------

    def count(self) -> int:
        return len(self._records)

    @staticmethod
    def _matches(metadata: dict[str, Any], where: dict | None) -> bool:
        """Support the same equality and $and filters used with Chroma."""
        if not where:
            return True
        if "$and" in where:
            return all(
                NumpyVectorStore._matches(metadata, clause) for clause in where["$and"]
            )
        return all(metadata.get(key) == value for key, value in where.items())

    def query(
        self,
        embedding: np.ndarray,
        n_results: int = CANDIDATE_POOL,
        where: dict | None = None,
    ) -> list[StoredChunk]:
        if not self._records:
            return []

        indices = [
            i
            for i, record in enumerate(self._records)
            if self._matches(record["metadata"], where)
        ]
        if not indices:
            return []

        query_vector = np.asarray(embedding, dtype=np.float32).ravel()
        similarities = self._vectors[indices] @ query_vector
        order = np.argsort(-similarities)[:n_results]

        return [
            StoredChunk(
                chunk_id=self._records[indices[int(j)]]["chunk_id"],
                text=self._records[indices[int(j)]]["text"],
                metadata=dict(self._records[indices[int(j)]]["metadata"]),
                # Cosine distance, exactly as Chroma reports it.
                distance=float(1.0 - similarities[int(j)]),
            )
            for j in order
        ]

    def get_by_id(self, chunk_id: str) -> StoredChunk | None:
        for record in self._records:
            if record["chunk_id"] == chunk_id:
                return StoredChunk(
                    chunk_id=record["chunk_id"],
                    text=record["text"],
                    metadata=dict(record["metadata"]),
                )
        return None

    def stats(self) -> dict[str, Any]:
        by_document: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for record in self._records:
            metadata = record["metadata"]
            by_document[metadata["doc_id"]] = by_document.get(metadata["doc_id"], 0) + 1
            by_category[metadata["category"]] = (
                by_category.get(metadata["category"], 0) + 1
            )
        return {
            "collection": self.collection_name,
            "persist_dir": str(self.persist_dir),
            "chunks": len(self._records),
            "documents": len(by_document),
            "chunks_per_document": dict(sorted(by_document.items())),
            "chunks_per_category": dict(sorted(by_category.items())),
        }


def create_store(**kwargs):
    """Open the vector store: ChromaDB when it is installed, NumPy otherwise.

    Set RAG_VECTOR_BACKEND=numpy to force the fallback (useful for checking
    that both paths give the same answers).
    """
    preference = os.environ.get("RAG_VECTOR_BACKEND", "").strip().lower()
    if preference == "numpy":
        return NumpyVectorStore(**kwargs)
    if preference in {"", "auto", "chroma", "chromadb"}:
        try:
            return VectorStore(**kwargs)
        except ImportError:
            if preference in {"chroma", "chromadb"}:
                raise
            return NumpyVectorStore(**kwargs)
    raise ValueError(
        f"Unknown RAG_VECTOR_BACKEND '{preference}' (use 'chroma' or 'numpy')."
    )



# ==========================================================================
# 6. Grounding signal: does the evidence talk about what was asked?
# ==========================================================================
#
# Cosine similarity alone cannot tell an answerable question from an
# unanswerable one in a corpus this narrow. That is a measured result, not an
# assumption: scoring 23 answerable and 10 unanswerable questions against the
# index gave answerable 0.248-0.669 and unanswerable 0.281-0.569. The ranges
# overlap almost completely. "How do I apply for a PhD in Computer Science
# here?" scores 0.569 - higher than most genuinely answerable questions -
# because the corpus is full of text about applying, computer science and
# programmes. It contains nothing about doctoral admission.
#
# The reason is structural: every chunk is a university policy written in the
# same register, so everything is somewhat similar to everything else.
# Similarity measures topical closeness, not whether the answer is present.
#
# Coverage asks a different, more literal question: of the content words the
# student actually used, how many appear anywhere in the passages we are about
# to hand the model?
#
#     coverage = |query content terms found in evidence| / |query content terms|
#
# It is reported, not used as a hard gate. Grid-searching both thresholds
# showed that a gate strict enough to refuse every unanswerable question also
# refused more than half of the answerable ones - an agent that unhelpful is a
# worse outcome than one that occasionally hands over evidence that turns out
# not to answer the question. So retrieval keeps recall high and labels its own
# confidence, and the final refusal is made by the model, which can read the
# passages and see that a paragraph about an undergraduate programme does not
# answer a question about doctoral admission.

WORD_RE = re.compile(r"[\w/\-]+")

# Suffixes stripped, longest first, so that "payments" -> "pay" rather than
# "payment". Intentionally cruder than a real stemmer: it only has to be
# consistent between the query and the evidence, not linguistically correct.
SUFFIXES = ("ities", "ment", "ing", "ied", "ies", "ed", "ly", "s")

# Words common in questions that say nothing about topic coverage. Removed
# only for the coverage calculation - the index itself keeps every word,
# because "may not" and "may" mean different things in a policy document.
QUESTION_WORDS = {
    "what", "when", "where", "who", "whom", "which", "how", "why",
    "can", "could", "should", "would", "will", "shall", "may", "must",
    "do", "does", "did", "is", "are", "was", "were", "am", "be", "been",
    "get", "got", "need", "want", "like", "know", "tell", "say", "said",
    "please", "thanks", "hi", "hello", "university", "student", "students",
    "many", "much", "long", "happen", "happens",
}

MIN_TERM_LENGTH = 3


def stem(term: str) -> str:
    """Strip a common suffix, leaving a stable stem of at least 4 characters."""
    for suffix in SUFFIXES:
        if len(term) > len(suffix) + 3 and term.endswith(suffix):
            return term[: -len(suffix)]
    return term


def content_terms(text: str) -> list[str]:
    """Stemmed content words of a query, in first-seen order."""
    terms: list[str] = []
    for raw in WORD_RE.findall(text.lower()):
        if len(raw) < MIN_TERM_LENGTH:
            continue
        if raw in ENGLISH_STOP_WORDS or raw in QUESTION_WORDS:
            continue
        stemmed = stem(raw)
        if stemmed in QUESTION_WORDS:
            continue
        if stemmed not in terms:
            terms.append(stemmed)
    return terms


@dataclass
class Coverage:
    """How much of the question the retrieved evidence actually addresses."""

    score: float
    matched: list[str]
    missing: list[str]
    total_terms: int

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "matched_terms": self.matched,
            "missing_terms": self.missing,
            "total_terms": self.total_terms,
        }


def compute_coverage(query: str, passage_texts: list[str]) -> Coverage:
    """Measure content-term coverage of `query` by the retrieved passages."""
    terms = content_terms(query)
    if not terms:
        # A query with no content words ("what about that?") cannot be judged
        # this way. Returning 1.0 means "this signal has no opinion" rather
        # than falsely reporting perfect grounding; the similarity floor and
        # the model's own check still apply.
        return Coverage(score=1.0, matched=[], missing=[], total_terms=0)

    blob = " ".join(passage_texts).lower()
    evidence_terms: set[str] = set()
    for word in WORD_RE.findall(blob):
        evidence_terms.add(stem(word))
        # A compound like "add/drop" or "re-sit" must also satisfy a query
        # that uses only one half of it ("drop", "sit").
        if "/" in word or "-" in word:
            for part in re.split(r"[/\-]", word):
                if part:
                    evidence_terms.add(stem(part))

    matched = [t for t in terms if t in evidence_terms]
    missing = [t for t in terms if t not in evidence_terms]

    return Coverage(
        score=len(matched) / len(terms),
        matched=matched,
        missing=missing,
        total_terms=len(terms),
    )


# ==========================================================================
# 7. Retrieval
# ==========================================================================
#
# Why two stages: the dense vector search is what makes "How late can I leave
# a course?" find a section that only ever says "withdraw". But dimensionality
# reduction blurs rare decisive terms, so a purely dense ranking will sometimes
# put a topically-similar chunk above the one that actually contains the rule.
# The lexical re-rank restores exact terms - "add/drop", "UGX", a specific date
# - over a small candidate pool where it is cheap to compute.
#
# Why the threshold matters: a nearest-neighbour search always returns
# something. Without a floor, a question about a policy the University has
# never published would return the four least-irrelevant chunks in the corpus,
# and the model would be handed plausible-looking evidence for an answer that
# does not exist.

GroundingStatus = Literal["grounded", "weak", "ungrounded"]


@dataclass
class RetrievedPassage:
    """One passage of evidence, with everything needed to cite it."""

    chunk_id: str
    text: str
    score: float
    dense_score: float
    lexical_score: float
    rank: int
    citation: str
    doc_id: str
    doc_title: str
    section: str
    source_url: str
    category: str
    chunk_kind: str
    retrieval_priority_tier: str

    @classmethod
    def from_stored(
        cls,
        stored: StoredChunk,
        score: float,
        dense: float,
        lexical: float,
        rank: int,
    ) -> "RetrievedPassage":
        metadata = stored.metadata
        return cls(
            chunk_id=stored.chunk_id,
            text=stored.text,
            score=round(float(score), 4),
            dense_score=round(float(dense), 4),
            lexical_score=round(float(lexical), 4),
            rank=rank,
            citation=metadata.get("citation", ""),
            doc_id=metadata.get("doc_id", ""),
            doc_title=metadata.get("doc_title", ""),
            section=metadata.get("section_title") or "(unsectioned)",
            source_url=metadata.get("source_url", ""),
            category=metadata.get("category", ""),
            chunk_kind=metadata.get("chunk_kind", ""),
            retrieval_priority_tier=metadata.get("retrieval_priority_tier", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "rank": self.rank,
            "score": self.score,
            "dense_score": self.dense_score,
            "lexical_score": self.lexical_score,
            "citation": self.citation,
            "doc_id": self.doc_id,
            "section": self.section,
            "source_url": self.source_url,
            "category": self.category,
            "chunk_kind": self.chunk_kind,
            "retrieval_priority_tier": self.retrieval_priority_tier,
            "text": self.text,
        }


@dataclass
class RetrievalResult:
    """The outcome of one retrieval, including the decision not to answer."""

    query: str
    status: GroundingStatus
    passages: list[RetrievedPassage] = field(default_factory=list)
    best_score: float = 0.0
    threshold: float = SIMILARITY_THRESHOLD
    strong_threshold: float = STRONG_EVIDENCE_THRESHOLD
    candidates_considered: int = 0
    rejection_reason: str | None = None
    filters: dict | None = None
    coverage: Coverage | None = None
    coverage_threshold: float = COVERAGE_THRESHOLD

    @property
    def is_grounded(self) -> bool:
        return self.status == "grounded"

    @property
    def has_evidence(self) -> bool:
        return bool(self.passages)

    @property
    def sources(self) -> list[str]:
        """Unique citations, in rank order - what the answer should cite."""
        seen: list[str] = []
        for passage in self.passages:
            if passage.citation not in seen:
                seen.append(passage.citation)
        return seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "status": self.status,
            "best_score": round(self.best_score, 4),
            "threshold": self.threshold,
            "strong_threshold": self.strong_threshold,
            "candidates_considered": self.candidates_considered,
            "coverage": self.coverage.to_dict() if self.coverage else None,
            "coverage_threshold": self.coverage_threshold,
            "rejection_reason": self.rejection_reason,
            "filters": self.filters,
            "sources": self.sources,
            "passages": [p.to_dict() for p in self.passages],
        }


class Retriever:
    """Hybrid semantic + lexical retriever over the indexed corpus."""

    def __init__(
        self,
        store: VectorStore | None = None,
        embedder: CorpusEmbedder | None = None,
        top_k: int = TOP_K,
        candidate_pool: int = CANDIDATE_POOL,
        threshold: float = SIMILARITY_THRESHOLD,
        strong_threshold: float = STRONG_EVIDENCE_THRESHOLD,
        coverage_threshold: float = COVERAGE_THRESHOLD,
        dense_weight: float = DENSE_WEIGHT,
        sparse_weight: float = SPARSE_WEIGHT,
    ) -> None:
        self.store = store or create_store()
        self.embedder = embedder or CorpusEmbedder.load()
        self.top_k = top_k
        self.candidate_pool = candidate_pool
        self.threshold = threshold
        self.strong_threshold = strong_threshold
        self.coverage_threshold = coverage_threshold
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        where: dict | None = None,
    ) -> RetrievalResult:
        """Retrieve evidence for `query`, or report that there is none."""
        top_k = top_k or self.top_k
        query = (query or "").strip()

        if not query:
            return RetrievalResult(
                query=query,
                status="ungrounded",
                rejection_reason="Empty query.",
                threshold=self.threshold,
                strong_threshold=self.strong_threshold,
            )

        query_vector = self.embedder.embed_query(query)
        candidates = self.store.query(
            query_vector, n_results=self.candidate_pool, where=where
        )

        if not candidates:
            return RetrievalResult(
                query=query,
                status="ungrounded",
                rejection_reason="The vector store returned no candidates.",
                threshold=self.threshold,
                strong_threshold=self.strong_threshold,
                filters=where,
            )

        # Chroma returns cosine *distance*; convert to similarity.
        dense_scores = np.array(
            [1.0 - (c.distance if c.distance is not None else 1.0) for c in candidates],
            dtype=np.float32,
        )
        lexical_scores = self.embedder.lexical_similarity(
            query, [c.text for c in candidates]
        )
        hybrid = self.dense_weight * dense_scores + self.sparse_weight * lexical_scores

        order = np.argsort(-hybrid)
        best_score = float(hybrid[order[0]])

        if best_score < self.threshold:
            return RetrievalResult(
                query=query,
                status="ungrounded",
                best_score=best_score,
                threshold=self.threshold,
                strong_threshold=self.strong_threshold,
                candidates_considered=len(candidates),
                filters=where,
                rejection_reason=(
                    f"No chunk reached the similarity threshold "
                    f"({best_score:.3f} < {self.threshold:.3f}). The approved corpus "
                    "does not appear to cover this question."
                ),
            )

        passages: list[RetrievedPassage] = []
        for rank, index in enumerate(order[:top_k], start=1):
            score = float(hybrid[index])
            if score < self.threshold:
                # Keep the evidence set clean: below-threshold chunks are not
                # passed to the model merely to fill up top_k.
                break
            passages.append(
                RetrievedPassage.from_stored(
                    candidates[int(index)],
                    score=score,
                    dense=float(dense_scores[index]),
                    lexical=float(lexical_scores[index]),
                    rank=rank,
                )
            )

        # Second signal: do the passages actually mention what was asked?
        coverage = compute_coverage(query, [p.text for p in passages])

        strong_similarity = best_score >= self.strong_threshold
        strong_coverage = coverage.score >= self.coverage_threshold

        if strong_similarity and strong_coverage:
            status: GroundingStatus = "grounded"
            rejection_reason = None
        else:
            status = "weak"
            reasons: list[str] = []
            if not strong_similarity:
                reasons.append(
                    f"best match scored {best_score:.3f}, below the strong-evidence "
                    f"threshold of {self.strong_threshold:.3f}"
                )
            if not strong_coverage:
                missing = ", ".join(coverage.missing[:5]) or "none"
                reasons.append(
                    f"the passages cover only {coverage.score:.0%} of the question's "
                    f"content terms (missing: {missing})"
                )
            rejection_reason = (
                "Weak evidence: "
                + "; ".join(reasons)
                + ". Passages are returned, but the agent must confirm they answer "
                "the question and say so plainly if they do not."
            )

        return RetrievalResult(
            query=query,
            status=status,
            passages=passages,
            best_score=best_score,
            threshold=self.threshold,
            strong_threshold=self.strong_threshold,
            candidates_considered=len(candidates),
            rejection_reason=rejection_reason,
            filters=where,
            coverage=coverage,
            coverage_threshold=self.coverage_threshold,
        )


# ==========================================================================
# 8. Index construction
# ==========================================================================


def load_chunk_records(path: Path | None = None) -> list[dict]:
    """Read the chunk records: from disk if present, else the built-in copy.

    Passing an explicit `path` requires that file to exist - an explicit
    request for a chunk file that is missing is an error, not a reason to fall
    back silently.
    """
    global CHUNKS_SOURCE

    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"Chunk file not found at {path}.")
        text = path.read_text(encoding="utf-8")
        CHUNKS_SOURCE = str(path)
    elif CHUNKS_PATH.exists():
        text = CHUNKS_PATH.read_text(encoding="utf-8")
        CHUNKS_SOURCE = str(CHUNKS_PATH)
    else:
        text = embedded_chunks_bytes().decode("utf-8")
        CHUNKS_SOURCE = "built-in copy"

    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records:
        raise ValueError(f"No chunks found in {CHUNKS_SOURCE} - nothing to index.")
    return records


def build_index(chunks: list[dict] | None = None, verbose: bool = True) -> dict:
    """Fit the embedder, embed every chunk and rebuild the vector store.

    Returns the index report, which is also written to
    data/vector_store/index_report.json.
    """
    chunks = chunks if chunks is not None else load_chunk_records()
    texts = [c["text"] for c in chunks]

    if verbose:
        print(f"Loaded {len(chunks)} chunks from: {CHUNKS_SOURCE}")
        print("Fitting the embedder on the corpus...")

    embedder = CorpusEmbedder().fit(texts)
    info = embedder.info
    assert info is not None
    if verbose:
        print(
            f"  model={info.model_name} "
            f"dim={info.effective_dim} (requested {info.requested_dim}) "
            f"vocab={info.vocabulary_size} "
            f"explained_variance={info.explained_variance:.3f}"
        )
    embedder.save(EMBEDDER_PATH)
    if verbose:
        print(f"  saved -> {EMBEDDER_PATH}")
        print("Embedding chunks...")

    embeddings = embedder.embed_documents(texts)
    if verbose:
        print(f"  embeddings shape: {embeddings.shape}")

    store = create_store()
    if verbose:
        print(f"Building the vector store ({store.backend})...")
    store.reset()
    count = store.add_chunks(chunks, embeddings)
    if verbose:
        print(f"  indexed {count} chunks")

    stats = store.stats()
    manifest = (
        json.loads(CHUNK_MANIFEST_PATH.read_text(encoding="utf-8"))
        if CHUNK_MANIFEST_PATH.exists()
        else {}
    )

    report = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": "src/rag/retriever.py --build",
        "embedding": info.to_dict(),
        "vector_store": {
            "backend": store.backend,
            "distance": "cosine",
            **stats,
        },
        "retrieval_defaults": {
            "candidate_pool": CANDIDATE_POOL,
            "top_k": TOP_K,
            "dense_weight": DENSE_WEIGHT,
            "sparse_weight": SPARSE_WEIGHT,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "strong_evidence_threshold": STRONG_EVIDENCE_THRESHOLD,
            "coverage_threshold": COVERAGE_THRESHOLD,
        },
        "source_chunks": {
            "loaded_from": CHUNKS_SOURCE,
            "register_version": manifest.get("register", {}).get("version"),
            "chunking_strategy": manifest.get("chunking_strategy"),
            "chunk_count": len(chunks),
        },
    }
    INDEX_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if verbose:
        print("\nChunks per document:")
        for doc_id, n in stats["chunks_per_document"].items():
            print(f"  {doc_id:<32} {n:>3}")
        print(f"\nWrote {INDEX_REPORT_PATH}")

    return report


# ==========================================================================
# 9. Command line entry point
# ==========================================================================


def _print_result(result: RetrievalResult) -> None:
    """Human-readable rendering of one retrieval."""
    print(f"\nQuery: {result.query}")
    print(f"Status: {result.status.upper()}")
    print(
        f"Best hybrid score: {result.best_score:.3f} "
        f"(floor {result.threshold:.2f}, strong {result.strong_threshold:.2f}) "
        f"over {result.candidates_considered} candidates"
    )
    if result.coverage is not None:
        print(
            f"Coverage: {result.coverage.score:.0%} of "
            f"{result.coverage.total_terms} content terms"
            + (
                f" (missing: {', '.join(result.coverage.missing)})"
                if result.coverage.missing
                else ""
            )
        )
    if result.rejection_reason:
        print(f"Note: {result.rejection_reason}")

    if not result.passages:
        print("\nNo passages returned - the agent should say it cannot answer.")
        return

    print(f"\n{len(result.passages)} passage(s):")
    for passage in result.passages:
        print(f"\n  [{passage.rank}] {passage.citation}")
        print(
            f"      score={passage.score:.3f} "
            f"(dense={passage.dense_score:.3f}, lexical={passage.lexical_score:.3f}) "
            f"chunk={passage.chunk_id}"
        )
        text = passage.text if len(passage.text) <= 400 else passage.text[:400] + "..."
        print(f"      {text}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vector store setup and retrieval (BSE4104, Week 3 Task 2)"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="the student question to retrieve evidence for",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="(re)build the vector index from data/chunks.jsonl, then exit",
    )
    parser.add_argument("--top-k", type=int, default=TOP_K, help="passages to return")
    parser.add_argument("--doc", default=None, help="restrict to one doc_id")
    parser.add_argument("--category", default=None, help="restrict to one category")
    parser.add_argument(
        "--json", action="store_true", help="print the full result as JSON"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="project root containing data/ (default: auto-detected)",
    )
    args = parser.parse_args(argv)

    if args.root is not None:
        _set_project_root(args.root.expanduser().resolve())

    if args.build:
        build_index()
        return 0

    if not args.query:
        parser.error("give a query, or use --build to build the index first")

    filters: dict[str, Any] = {}
    if args.doc:
        filters["doc_id"] = args.doc
    if args.category:
        filters["category"] = args.category
    where = filters or None
    if len(filters) > 1:
        where = {"$and": [{key: value} for key, value in filters.items()]}

    # Build the index on first use rather than telling the user to run a
    # command they would only run once: an empty store is a setup step, not an
    # error the person needs to hear about.
    if create_store().count() == 0:
        # To stderr, so that `--json` output stays machine-readable.
        print(
            "No index found - building it now (this happens once).",
            file=sys.stderr,
        )
        build_index(verbose=False)
        print("Index built.", file=sys.stderr)

    retriever = Retriever(top_k=args.top_k)

    result = retriever.retrieve(args.query, top_k=args.top_k, where=where)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_result(result)

    # Exit code 0 when evidence was returned, 2 when the corpus does not cover
    # the question, so the CLI can be used in a shell pipeline or a smoke test.
    return 0 if result.has_evidence else 2


def _set_project_root(root: Path) -> None:
    """Point every path in this module at a different project root."""
    global PROJECT_ROOT, DATA_DIR, CHUNKS_PATH, CHUNK_MANIFEST_PATH
    global VECTOR_STORE_DIR, CHROMA_DIR, EMBEDDER_PATH, INDEX_REPORT_PATH

    PROJECT_ROOT = root
    DATA_DIR = PROJECT_ROOT / "data"
    CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
    CHUNK_MANIFEST_PATH = DATA_DIR / "chunk_manifest.json"
    VECTOR_STORE_DIR = DATA_DIR / "vector_store"
    CHROMA_DIR = VECTOR_STORE_DIR / "chroma"
    EMBEDDER_PATH = VECTOR_STORE_DIR / "embedder.joblib"
    INDEX_REPORT_PATH = VECTOR_STORE_DIR / "index_report.json"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # Output was piped into something that closed early (e.g. `| head`).
        raise SystemExit(0)
