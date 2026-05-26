# 폴더별 과거 변경 패턴을 ChromaDB에 저장·검색하는 RAG 저장소
import logging
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

_EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"  # 한국어 지원 경량 모델


class RAGStore:
    def __init__(self, db_path: str):
        Path(db_path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=db_path)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=_EMBED_MODEL
        )
        self._col = self._client.get_or_create_collection(
            name="folder_diffs",
            embedding_function=ef,
        )

    def store(self, date: str, folder: str, diff_stat: str) -> None:
        """오늘의 diff stat을 폴더별로 저장."""
        self._col.upsert(
            ids=[f"{date}_{folder}"],
            documents=[diff_stat],
            metadatas=[{"folder": folder, "date": date}],
        )
        logger.info(f"RAG 저장: {folder} ({date})")

    def retrieve(self, folder: str, current_diff: str, n: int = 2) -> list[str]:
        """현재 diff와 유사한 과거 변경 패턴을 반환."""
        try:
            results = self._col.query(
                query_texts=[current_diff],
                n_results=n,
                where={"folder": folder},
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            return [
                f"[{m['date']}]\n{d[:600]}"
                for d, m in zip(docs, metas)
            ]
        except Exception:
            # 저장된 데이터가 없거나 n보다 적을 때 graceful 처리
            return []
