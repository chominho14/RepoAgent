# 환경변수 및 config.yaml을 로드하는 Settings dataclass
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass
class LLMConfig:
    model_id: str = "Qwen/Qwen2.5-7B-Instruct"
    device: str = "auto"
    max_new_tokens: int = 512
    language_blocking_enabled: bool = True


@dataclass
class Settings:
    # HuggingFace
    hf_token: str = field(default_factory=lambda: os.getenv("HF_TOKEN", ""))

    # GitLab
    gitlab_token: str = field(default_factory=lambda: os.getenv("GITLAB_TOKEN", ""))
    gitlab_url: str = ""
    gitlab_repo_url: str = ""   # https://<host>/ctilab/ot-anomaly-detection-model.git
    gitlab_ssl_verify: bool = False

    # 동기화 대상
    sync_root_path: str = "/data/mino/ot"

    # Telegram
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

    # LLM
    llm: LLMConfig = field(default_factory=LLMConfig)

    # RAG
    rag_db_path: str = "/data/mino/test/alarm_project/rag_db"

    # 프로젝트 설명 (변경 없을 때 report에 표시)
    project_descriptions: dict = field(default_factory=dict)

    # 스케줄
    notify_cron: str = "50 17 * * 1-5"
    sync_cron: str = "51 17 * * 1-5"
    timezone: str = "Asia/Seoul"

    def __post_init__(self):
        if not self.gitlab_token:
            raise ValueError("GITLAB_TOKEN이 설정되지 않았습니다.")
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        if not self.telegram_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID가 설정되지 않았습니다.")

    @property
    def remote_url_with_token(self) -> str:
        """토큰이 포함된 HTTPS remote URL."""
        base = self.gitlab_repo_url.replace("https://", "")
        return f"https://oauth2:{self.gitlab_token}@{base}"


def load_settings() -> Settings:
    config_path = ROOT_DIR / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    gitlab = raw.get("gitlab", {})
    llm_section = raw.get("llm", {})
    sync_section = raw.get("sync", {})
    notify_section = raw.get("notify", {})

    llm_cfg = LLMConfig(
        model_id=llm_section.get("model_id", "Qwen/Qwen2.5-7B-Instruct"),
        device=llm_section.get("device", "auto"),
        max_new_tokens=llm_section.get("max_new_tokens", 512),
        language_blocking_enabled=llm_section.get("language_blocking_enabled", True),
    )

    return Settings(
        gitlab_url=gitlab.get("url", ""),
        gitlab_repo_url=gitlab.get("repo_url", ""),
        gitlab_ssl_verify=gitlab.get("ssl_verify", False),
        sync_root_path=sync_section.get("root_path", "/data/mino/ot"),
        sync_cron=sync_section.get("cron", "50 17 * * 1-5"),
        notify_cron=notify_section.get("cron", "0 18 * * 1-5"),
        llm=llm_cfg,
        project_descriptions=raw.get("project_descriptions", {}),
    )
