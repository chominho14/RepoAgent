# Qwen2.5 모델을 사용해 폴더별 변경사항을 한국어로 요약하는 서비스
import logging

from models.causal_lm import CausalLMModel
from prompts.daily_summary import build_summary_messages
from services.diff_collector import FolderDiff

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    def __init__(self, model: CausalLMModel):
        self._model = model

    def summarize(self, diffs: list[FolderDiff], past_contexts: dict[str, str]) -> str:
        changed = [d for d in diffs if d.has_changes]
        if not changed:
            return ""
        messages = build_summary_messages(changed, past_contexts)
        try:
            return self._model.generate(messages, max_new_tokens=1024)
        except Exception as e:
            logger.error(f"LLM 요약 실패: {e}")
            raise
