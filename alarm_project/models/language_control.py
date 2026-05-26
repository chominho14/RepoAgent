import re
from typing import Iterable

import torch
from transformers import LogitsProcessor, LogitsProcessorList


FORBIDDEN_SCRIPT_RANGES = (
    (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF), # CJK Unified Ideographs Extension B
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0x31F0, 0x31FF),   # Katakana Phonetic Extensions
    (0x0400, 0x04FF),   # Cyrillic
    (0x0500, 0x052F),   # Cyrillic Supplement
)

FORBIDDEN_TEXT_PATTERN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\u31f0-\u31ff\u0400-\u052f]"
)
_CPU_MASK_CACHE: dict[tuple[str, int], torch.Tensor] = {}


def contains_forbidden_script(text: str) -> bool:
    return bool(FORBIDDEN_TEXT_PATTERN.search(text))


def sanitize_korean_output(text: str) -> str:
    return FORBIDDEN_TEXT_PATTERN.sub("", text).strip()


def _contains_forbidden_char(token: str) -> bool:
    # 컴파일된 regex 재사용 — Python 루프보다 C 레벨에서 훨씬 빠름
    return bool(FORBIDDEN_TEXT_PATTERN.search(token))


def build_forbidden_token_mask(tokenizer, vocab_size: int, device: torch.device) -> torch.Tensor:
    tokenizer_key = getattr(tokenizer, "name_or_path", tokenizer.__class__.__name__)
    cache_key = (tokenizer_key, vocab_size)
    cpu_mask = _CPU_MASK_CACHE.get(cache_key)
    if cpu_mask is None:
        token_ids = torch.arange(vocab_size, dtype=torch.long)
        decoded_tokens = tokenizer.batch_decode(token_ids.unsqueeze(1), skip_special_tokens=False)
        cpu_mask = torch.tensor(
            [_contains_forbidden_char(token) for token in decoded_tokens],
            dtype=torch.bool,
        )
        _CPU_MASK_CACHE[cache_key] = cpu_mask
    return cpu_mask.to(device)


class LanguageBlockerProcessor(LogitsProcessor):
    """특정 문자권 토큰이 샘플링되지 않도록 로짓을 차단한다."""

    def __init__(self, tokenizer, vocab_size: int):
        self.tokenizer = tokenizer
        self.vocab_size = vocab_size
        self._mask_by_device: dict[str, torch.Tensor] = {}

    def _get_mask(self, scores: torch.Tensor) -> torch.Tensor:
        device_key = str(scores.device)
        mask = self._mask_by_device.get(device_key)
        if mask is None or mask.device != scores.device:
            mask = build_forbidden_token_mask(self.tokenizer, self.vocab_size, scores.device)
            self._mask_by_device[device_key] = mask
        return mask

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        mask = self._get_mask(scores)
        if scores.dim() == 1:
            scores[mask] = -float("inf")
        else:
            scores[:, mask] = -float("inf")
        return scores


def normalize_llamacpp_messages(messages: Iterable[dict]) -> list[dict]:
    result = []
    for msg in messages:
        content = msg["content"]
        if isinstance(content, list):
            content = " ".join(item.get("text", "") for item in content if item.get("type") == "text")
        result.append({"role": msg["role"], "content": content})
    return result
