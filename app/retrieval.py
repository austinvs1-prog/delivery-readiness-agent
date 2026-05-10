from pathlib import Path
from typing import Any
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.schemas import RetrievedChunk

DATA_PATH = Path("data/delivery_readiness_inspections.csv")
DOCS_PATH = Path("data/rag_docs")


class RetrievalIndex:
    def __init__(self) -> None:
        self.chunks: list[dict[str, Any]] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None
        self._build()

    def _build(self) -> None:
        df = pd.read_csv(DATA_PATH)
        for row in df.itertuples(index=False):
            if getattr(row, "_3") == "Final check clear":
                continue
            self.chunks.append(
                {
                    "chunk_id": getattr(row, "_0"),
                    "source_type": "inspection_note",
                    "text": getattr(row, "_3"),
                    "metadata": {
                        "inspection_id": getattr(row, "_0"),
                        "plant": getattr(row, "Plant"),
                        "pass_fail": getattr(row, "_2"),
                    },
                }
            )
        for path in DOCS_PATH.glob("*.md"):
            self.chunks.append(
                {
                    "chunk_id": path.stem,
                    "source_type": "policy_doc",
                    "text": path.read_text(),
                    "metadata": {"path": str(path)},
                }
            )

        texts = [chunk["text"] for chunk in self.chunks]
        # Character n-grams make short shorthand notes robust to wording variants such as leak/leakage.
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        self.matrix = self.vectorizer.fit_transform(texts)

    @staticmethod
    def expand_query(query: str) -> str:
        q = query.lower()
        additions: list[str] = []
        if "water leakage" in q or "water leak" in q:
            additions += ["water moisture damp rain test seep wet"]
        elif "leak" in q or "leakage" in q:
            additions += ["leak seep drip wetness moisture water oil"]
        if "body damage" in q or "damage" in q:
            additions += ["dent scuff scratch cracked paint"]
        if "electrical" in q:
            additions += ["wire harness connector lamp"]
        return f"{query} {' '.join(additions)}".strip()

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        assert self.vectorizer is not None
        q = self.vectorizer.transform([self.expand_query(query)])
        scores = cosine_similarity(q, self.matrix).flatten()
        ranked = scores.argsort()[::-1][:top_k]
        results: list[RetrievedChunk] = []
        for idx in ranked:
            chunk = self.chunks[int(idx)]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk["chunk_id"],
                    source_type=chunk["source_type"],
                    text=chunk["text"],
                    score=float(scores[int(idx)]),
                    metadata=chunk["metadata"],
                )
            )
        return results

    def semantic_inspection_ids(self, query: str) -> list[str]:
        q = query.lower()
        ids: list[str] = []
        for chunk in self.chunks:
            if chunk["source_type"] != "inspection_note":
                continue
            text = chunk["text"].lower()
            if "water leakage" in q or "water leak" in q:
                matched = any(x in text for x in ["water", "moisture", "rain test"])
            elif "leak" in q or "leakage" in q:
                matched = any(x in text for x in ["oil seep", "oil drip", "oil wetness", "oil leak", "water", "moisture", "rain test"])
            elif "body damage" in q:
                matched = any(x in text for x in ["dent", "scuff", "scratch", "cracked", "paint"])
            elif "electrical" in q:
                matched = any(x in text for x in ["wire", "harness", "connector", "lamp cuts"])
            else:
                matched = False
            if matched:
                ids.append(chunk["metadata"]["inspection_id"])
        return ids
