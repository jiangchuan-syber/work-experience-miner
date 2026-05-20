# -*- coding: utf-8 -*-
"""向量索引：Sentence-Transformers + Chroma 持久化。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from rag.chunking import DocChunk, ROOT, load_rag_chunks

PERSIST_DIR = ROOT / ".chroma_job_kb"
COLLECTION = "job_kb_v2"
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _get_encoder(model_name: str):  # type: ignore[no-untyped-def]
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def encode_normalized(model, texts: list[str]):  # type: ignore[no-untyped-def]
    import numpy as np

    embs = model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 8,
    )
    if hasattr(embs, "tolist"):
        return embs.tolist()
    return np.asarray(embs).tolist()


class JobKBIndex:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(PERSIST_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._bind_collection()

    def _bind_collection(self, *, create_if_missing: bool = True) -> None:
        """始终从持久化客户端按名称绑定集合，避免 delete/recreate 后句柄失效。"""
        if create_if_missing:
            self._col = self._client.get_or_create_collection(
                name=COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        else:
            self._col = self._client.get_collection(COLLECTION)

    def _rebind_after_error(self) -> None:
        try:
            self._col = self._client.get_collection(COLLECTION)
        except Exception:  # noqa: BLE001
            self._col = self._client.get_or_create_collection(
                name=COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )

    @property
    def model(self):  # type: ignore[no-untyped-def]
        if self._model is None:
            self._model = _get_encoder(self.model_name)
        return self._model

    def count(self) -> int:
        try:
            return int(self._col.count())
        except Exception:  # noqa: BLE001
            self._rebind_after_error()
            return int(self._col.count())

    def rebuild(self, chunks: list[DocChunk] | None = None) -> int:
        if chunks is None:
            chunks = load_rag_chunks()
        try:
            self._client.delete_collection(COLLECTION)
        except Exception:  # noqa: BLE001
            pass
        self._bind_collection(create_if_missing=True)
        if not chunks:
            return 0
        ids = [c.chunk_id for c in chunks]
        texts = [c.text for c in chunks]
        metadatas: list[dict[str, str]] = [
            {"source": c.source, "title": c.title} for c in chunks
        ]
        embs = encode_normalized(self.model, texts)
        self._col.add(ids=ids, documents=texts, metadatas=metadatas, embeddings=embs)
        return len(chunks)

    def search_one(self, query: str, top_k: int = 8) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        qv = encode_normalized(self.model, [q])[0]
        try:
            res = self._col.query(
                query_embeddings=[qv],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:  # noqa: BLE001
            self._rebind_after_error()
            res = self._col.query(
                query_embeddings=[qv],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        out: list[dict[str, Any]] = []
        ids_list = res.get("ids") or [[]]
        docs_list = res.get("documents") or [[]]
        meta_list = res.get("metadatas") or [[]]
        dist_list = res.get("distances") or [[]]
        for cid, doc, meta, dist in zip(
            ids_list[0],
            docs_list[0],
            meta_list[0],
            dist_list[0],
        ):
            out.append(
                {
                    "id": cid,
                    "document": doc or "",
                    "metadata": meta or {},
                    "distance": float(dist) if dist is not None else None,
                }
            )
        return out


def get_default_index(model_name: str = DEFAULT_MODEL) -> JobKBIndex:
    return JobKBIndex(model_name=model_name)
