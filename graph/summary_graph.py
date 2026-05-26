# LangGraph 기반 일일 요약 파이프라인 (collect→rag_retrieve→analyze→format→send→rag_store)
import json
import logging
from datetime import date
from pathlib import Path

_SECRETS_LOG = Path(__file__).parent.parent / "logs" / "gitignored_today.json"

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from services.diff_collector import DiffCollector, FolderDiff
from services.llm_analyzer import LLMAnalyzer
from services.rag_store import RAGStore
from services.report_writer import ReportWriter
from services.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class SummaryState(TypedDict):
    root_path: str
    diffs: list[FolderDiff]
    past_contexts: dict[str, str]   # folder_name → 과거 유사 변경 패턴
    llm_summary: str
    formatted_message: str
    llm_ok: bool
    errors: list[str]
    gitignored_warnings: list[str]  # "파일경로 (이유)" 형태의 보호 파일 목록


def build_summary_graph(
    collector: DiffCollector,
    analyzer: LLMAnalyzer,
    notifier: TelegramNotifier,
    rag_store: RAGStore,
    report_writer: ReportWriter,
):
    def collect_diffs(state: SummaryState) -> SummaryState:
        diffs = collector.collect(state["root_path"])
        return {**state, "diffs": diffs, "gitignored_warnings": _load_gitignored_warnings()}

    def retrieve_rag_context(state: SummaryState) -> SummaryState:
        """변경된 각 폴더의 과거 유사 패턴을 ChromaDB에서 검색."""
        contexts: dict[str, str] = {}
        for diff in state["diffs"]:
            past = rag_store.retrieve(diff.folder_name, diff.stat_summary, n=2)
            if past:
                contexts[diff.folder_name] = "\n\n".join(past)
        if contexts:
            logger.info(f"RAG 컨텍스트 로드: {list(contexts.keys())}")
        return {**state, "past_contexts": contexts}

    def analyze_with_llm(state: SummaryState) -> SummaryState:
        if not any(d.has_changes for d in state["diffs"]):
            return {**state, "llm_summary": "", "llm_ok": True}
        try:
            summary = analyzer.summarize(state["diffs"], state["past_contexts"])
            return {**state, "llm_summary": summary, "llm_ok": True}
        except Exception as e:
            logger.error(f"LLM 분석 실패: {e}")
            return {**state, "llm_summary": "", "llm_ok": False,
                    "errors": state["errors"] + [f"LLM 오류: {e}"]}

    def format_message(state: SummaryState) -> SummaryState:
        today = date.today().strftime("%Y-%m-%d")
        lines = [f"*📋 오늘의 코드 변경 요약 ({today})*\n"]

        if state["llm_summary"]:
            lines.append(state["llm_summary"])
        elif any(d.has_changes for d in state["diffs"]):
            for d in state["diffs"]:
                if d.has_changes:
                    lines.append(f"🔹 *{d.folder_name}*")
                    lines.append(f"```\n{d.stat_summary[:400]}\n```")
        else:
            lines.append("오늘은 변경된 내용이 없습니다.")

        if state["gitignored_warnings"]:
            lines.append("\n🔒 *민감 파일 보호*")
            for w in state["gitignored_warnings"]:
                lines.append(f"  - `{w}` → .gitignore로 이동")

        if state["errors"]:
            lines.append("\n⚠️ *오류*")
            for err in state["errors"]:
                lines.append(f"  - {err}")

        return {**state, "formatted_message": "\n".join(lines)}

    def send_telegram(state: SummaryState) -> SummaryState:
        try:
            notifier.send(state["formatted_message"])
        except Exception as e:
            logger.error(f"Telegram 전송 실패: {e}")
        return state

    def store_rag_summaries(state: SummaryState) -> SummaryState:
        """오늘의 diff stat을 다음 날 RAG 컨텍스트로 쓸 수 있도록 저장."""
        today = date.today().strftime("%Y-%m-%d")
        for diff in state["diffs"]:
            if diff.has_changes and diff.stat_summary:
                rag_store.store(today, diff.folder_name, diff.stat_summary)
        return state

    def write_report(state: SummaryState) -> SummaryState:
        try:
            report_writer.write(state["diffs"], state["llm_summary"], state["gitignored_warnings"])
        except Exception as e:
            logger.error(f"리포트 저장 실패: {e}")
        return state

    graph = StateGraph(SummaryState)
    graph.add_node("collect_diffs", collect_diffs)
    graph.add_node("retrieve_rag_context", retrieve_rag_context)
    graph.add_node("analyze_with_llm", analyze_with_llm)
    graph.add_node("format_message", format_message)
    graph.add_node("send_telegram", send_telegram)
    graph.add_node("store_rag_summaries", store_rag_summaries)
    graph.add_node("write_report", write_report)

    graph.set_entry_point("collect_diffs")
    graph.add_edge("collect_diffs", "retrieve_rag_context")
    graph.add_edge("retrieve_rag_context", "analyze_with_llm")
    graph.add_edge("analyze_with_llm", "format_message")
    graph.add_edge("format_message", "send_telegram")
    graph.add_edge("send_telegram", "store_rag_summaries")
    graph.add_edge("store_rag_summaries", "write_report")
    graph.add_edge("write_report", END)

    return graph.compile()


def _load_gitignored_warnings() -> list[str]:
    try:
        data = json.loads(_SECRETS_LOG.read_text(encoding="utf-8"))
        if data.get("date") == str(date.today()):
            return [f"{e['file']} ({e['reason']})" for e in data.get("entries", [])]
    except Exception:
        pass
    return []


def run_summary_pipeline(
    root_path: str,
    collector: DiffCollector,
    analyzer: LLMAnalyzer,
    notifier: TelegramNotifier,
    rag_store: RAGStore,
    report_writer: ReportWriter,
) -> None:
    compiled = build_summary_graph(collector, analyzer, notifier, rag_store, report_writer)
    initial: SummaryState = {
        "root_path": root_path,
        "diffs": [],
        "past_contexts": {},
        "llm_summary": "",
        "formatted_message": "",
        "llm_ok": False,
        "errors": [],
        "gitignored_warnings": [],
    }
    compiled.invoke(initial)
