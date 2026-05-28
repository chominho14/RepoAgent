# Qwen2.5-Coder로 폴더별 raw diff를 코드 관점에서 분석하는 서비스
import logging
from typing import Callable

from models.causal_lm import CausalLMModel, free_gpu_memory
from prompts.code_analysis import build_code_analysis_messages
from services.diff_collector import FolderDiff

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    def __init__(self, model_loader: Callable[[], CausalLMModel]):
        # 모델을 미리 로드하지 않고, analyze() 시점에 로드 후 해제 (순차 로딩)
        self._load_model = model_loader

    def analyze(self, diffs: list[FolderDiff]) -> dict[str, str]:
        """변경된 폴더별 코드 분석 결과를 반환한다. folder_name → 분석 텍스트."""
        targets = [d for d in diffs if d.has_changes and d.raw_diff]
        if not targets:
            return {}

        logger.info("Coder 모델 로딩 중...")
        model = self._load_model()
        try:
            analyses: dict[str, str] = {}
            for d in targets:
                messages = build_code_analysis_messages(d.folder_name, d.raw_diff)
                try:
                    analyses[d.folder_name] = model.generate(messages, max_new_tokens=512)
                    logger.info(f"[{d.folder_name}] 코드 분석 완료")
                except Exception as e:
                    logger.error(f"[{d.folder_name}] 코드 분석 실패: {e}")
            return analyses
        finally:
            del model
            free_gpu_memory()
            logger.info("Coder 모델 해제 완료.")
