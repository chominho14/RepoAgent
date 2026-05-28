import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, LogitsProcessorList
from .base import BaseModel
from .language_control import (
    LanguageBlockerProcessor,
    contains_forbidden_script,
    sanitize_korean_output,
)


def _resolve_attn_implementation() -> str:
    """Flash Attention 2가 설치돼 있으면 사용, 아니면 SDPA(torch 내장)로 폴백."""
    try:
        import flash_attn  # noqa: F401
        return "flash_attention_2"
    except ImportError:
        return "sdpa"


def free_gpu_memory() -> None:
    """모델 해제 후 GPU 캐시를 비운다 (순차 로딩 시 메모리 회수)."""
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


class CausalLMModel(BaseModel):
    def __init__(
        self,
        model_id: str,
        hf_token: str,
        device: str = "auto",
        do_sample: bool = False,
        temperature: float = 0.2,
        top_p: float = 0.9,
        language_blocking_enabled: bool = True,
        sanitize_forbidden_output: bool = True,
    ):
        _token = hf_token or None  # 빈 문자열은 None으로 변환 (로컬 모델 대응)
        print(f"Loading tokenizer: {model_id}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, token=_token)

        attn_impl = _resolve_attn_implementation()
        print(f"Loading model: {model_id} (attn: {attn_impl})")
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            token=_token,
            device_map=device,
            dtype=torch.bfloat16,
            attn_implementation=attn_impl,
        )
        self.model.eval()
        self.do_sample = do_sample
        self.temperature = temperature
        self.top_p = top_p
        self.sanitize_forbidden_output = sanitize_forbidden_output

        # LogitsProcessor를 한 번만 생성 → device mask 재구축 오버헤드 제거
        if language_blocking_enabled:
            self._logits_processor = LogitsProcessorList([
                LanguageBlockerProcessor(self.tokenizer, self.model.config.vocab_size)
            ])
        else:
            self._logits_processor = None

        print("Model loaded successfully.")

    def generate(self, messages: list, max_new_tokens: int = 256) -> str:
        inputs = self._prepare_inputs(messages)
        generate_kwargs = self._build_generate_kwargs(max_new_tokens=max_new_tokens)
        with torch.inference_mode():
            outputs = self.model.generate(**inputs, **generate_kwargs)
        return self._decode_output(outputs, inputs)

    def _build_generate_kwargs(self, max_new_tokens: int) -> dict:
        kwargs: dict = {
            "max_new_tokens": max_new_tokens,
            "do_sample": self.do_sample,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if self.do_sample:
            kwargs["temperature"] = self.temperature
            kwargs["top_p"] = self.top_p
        if self._logits_processor is not None:
            kwargs["logits_processor"] = self._logits_processor
        return kwargs

    def _prepare_inputs(self, messages: list) -> dict:
        normalized = self._normalize_messages(messages)
        return self.tokenizer.apply_chat_template(
            normalized,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)

    def _normalize_messages(self, messages: list) -> list:
        """list 형식 content → CausalLM이 요구하는 plain string으로 변환."""
        result = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, list):
                content = " ".join(
                    item.get("text", "") for item in content if item.get("type") == "text"
                )
            result.append({"role": msg["role"], "content": content})
        return result

    def _decode_output(self, outputs, inputs) -> str:
        prompt_len = inputs["input_ids"].shape[-1]
        text = self.tokenizer.decode(
            outputs[0][prompt_len:],
            skip_special_tokens=True,
        )
        if self.sanitize_forbidden_output and contains_forbidden_script(text):
            return sanitize_korean_output(text)
        return text
