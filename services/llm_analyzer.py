# Qwen2.5 모델을 사용해 폴더별 변경사항을 한국어로 요약하는 서비스
import logging
from typing import Callable

from models.causal_lm import CausalLMModel, free_gpu_memory
from prompts.daily_summary import build_summary_messages
from services.diff_collector import FolderDiff

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    def __init__(self, model_loader: Callable[[], CausalLMModel]):
        # 모델을 미리 로드하지 않고, summarize() 시점에 로드 후 해제 (순차 로딩)
        self._load_model = model_loader

    def summarize(
        self,
        diffs: list[FolderDiff],
        past_contexts: dict[str, str],
        code_analyses: dict[str, str],
    ) -> str:
        changed = [d for d in diffs if d.has_changes]
        if not changed:
            return ""
        messages = build_summary_messages(changed, past_contexts, code_analyses)

        logger.info("요약 모델 로딩 중...")
        model = self._load_model()
        try:
            return model.generate(messages, max_new_tokens=1024)
        except Exception as e:
            logger.error(f"LLM 요약 실패: {e}")
            raise
        finally:
            del model
            free_gpu_memory()
            logger.info("요약 모델 해제 완료.")
