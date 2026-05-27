# 스케줄러 진입점 — 평일 17:50 git sync, 18:00 Telegram 알림 자동 실행
import argparse
import gc
import logging
import os
import sys
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import load_settings
from graph.summary_graph import run_summary_pipeline
from models.causal_lm import CausalLMModel
from services.diff_collector import DiffCollector
from services.git_sync import GitSyncService
from services.llm_analyzer import LLMAnalyzer
from services.rag_store import RAGStore
from services.report_writer import ReportWriter
from services.telegram_notifier import TelegramNotifier

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/alarm.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def _seconds_until_midnight() -> int:
    now = datetime.now()
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((midnight - now).total_seconds()))


def build_sync_service(settings):
    return GitSyncService(
        root_path=settings.sync_root_path,
        remote_url=settings.remote_url_with_token,
        ssl_verify=settings.gitlab_ssl_verify,
    )


def run_notify(settings):
    """LLM을 로딩하고, 분석 후 메모리에서 해제. 이후 커밋 여부를 사용자에게 확인."""
    import torch

    logger.info("LLM 로딩 중...")
    model = CausalLMModel(
        model_id=settings.llm.model_id,
        hf_token=settings.hf_token,
        device=settings.llm.device,
        do_sample=False,
        language_blocking_enabled=settings.llm.language_blocking_enabled,
    )
    collector = DiffCollector()
    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    analyzer = LLMAnalyzer(model)
    rag_store = RAGStore(settings.rag_db_path)
    report_writer = ReportWriter(settings.sync_root_path, settings.project_descriptions)

    try:
        run_summary_pipeline(settings.sync_root_path, collector, analyzer, notifier, rag_store, report_writer)
    finally:
        del analyzer
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("LLM 메모리 해제 완료.")

    # 커밋 여부 확인 (자정까지 대기, 무응답이면 자동 커밋)
    confirmed = notifier.ask_commit_confirmation(timeout_seconds=_seconds_until_midnight())
    if confirmed:
        logger.info("=== 사용자 확인 → git sync 시작 ===")
        result = build_sync_service(settings).sync()
        status = "성공" if result.success else f"실패: {result.error}"
        logger.info(f"git sync 완료 — {status}")
        for c in result.commits:
            logger.info(f"  [{c['folder']}] {c['file_count']}개 파일 — {c['message']}")
    else:
        logger.info("=== 커밋 건너뜀 (사용자 거부) ===")


def make_sync_job(settings):
    git_sync = build_sync_service(settings)

    def sync_job():
        logger.info("=== git sync 시작 ===")
        result = git_sync.sync()
        status = "성공" if result.success else f"실패: {result.error}"
        logger.info(f"git sync 완료 — {status}")
        for c in result.commits:
            logger.info(f"  [{c['folder']}] {c['file_count']}개 파일 — {c['message']}")

    return sync_job


def make_notify_job(settings):
    def notify_job():
        logger.info("=== 일일 요약 알림 시작 ===")
        run_notify(settings)
        logger.info("=== 일일 요약 알림 완료 ===")

    return notify_job


def main():
    parser = argparse.ArgumentParser(description="alarm-project 스케줄러")
    parser.add_argument(
        "--run-now",
        choices=["sync", "notify"],
        help="즉시 실행 (테스트용). 생략하면 데몬 모드로 스케줄러 시작.",
    )
    args = parser.parse_args()

    settings = load_settings()

    if args.run_now == "sync":
        make_sync_job(settings)()
        return
    if args.run_now == "notify":
        make_notify_job(settings)()
        return

    # ── 데몬 모드 ──────────────────────────────────────────────
    # python main.py 만 실행하면 스케줄러가 백그라운드에서 계속 동작
    scheduler = BlockingScheduler(timezone=settings.timezone)
    scheduler.add_job(make_notify_job(settings), CronTrigger.from_crontab(settings.notify_cron))

    logger.info("스케줄러 시작.")
    logger.info(f"  알림 발송 : {settings.notify_cron}  (LLM 분석 → Telegram 요약 → 커밋 여부 확인)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("스케줄러 종료.")


if __name__ == "__main__":
    main()

    '''
    # 즉시 테스트
    python main.py --run-now sync      # git sync만 실행
    python main.py --run-now notify    # Telegram 알림 실행
    
    # 백그라운드 데몬 (평일 17:50 sync, 18:00 notify 자동)
    nohup python main.py > logs/alarm.log 2>&1 &

    # 데몬 종료
    kill $(pgrep -f "python main.py")
    '''
