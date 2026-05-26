# 일일 변경 요약을 날짜_report.txt 파일로 기록하는 서비스
import logging
from datetime import date
from pathlib import Path

from services.diff_collector import FolderDiff

logger = logging.getLogger(__name__)


class ReportWriter:
    def __init__(self, root_path: str, project_descriptions: dict[str, str]):
        self._root = Path(root_path)
        self._descriptions = project_descriptions

    def write(self, diffs: list[FolderDiff], llm_summary: str, gitignored_warnings: list[str]) -> None:
        today = date.today().strftime("%Y-%m-%d")
        report_path = self._root / f"{today}_report.txt"
        lines = self._build(diffs, llm_summary, gitignored_warnings, today)
        report_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"리포트 저장: {report_path}")

    def _build(
        self,
        diffs: list[FolderDiff],
        llm_summary: str,
        gitignored_warnings: list[str],
        today: str,
    ) -> list[str]:
        lines = [f"[{today}] OT 프로젝트 일일 변경 요약", "=" * 50, ""]

        changed = [d for d in diffs if d.has_changes]
        unchanged = [d for d in diffs if not d.has_changes]

        if changed:
            lines.append("■ 변경된 프로젝트")
            lines.append("")
            if llm_summary:
                lines.append(llm_summary)
            else:
                for d in changed:
                    lines.append(f"▶ {d.folder_name}")
                    lines.append(d.stat_summary[:800])
                    lines.append("")
        else:
            lines.append("■ 오늘 변경된 프로젝트 없음")

        if unchanged:
            lines.append("")
            lines.append("■ 변경 없는 프로젝트")
            lines.append("")
            for d in unchanged:
                desc = self._descriptions.get(d.folder_name, "")
                if desc:
                    lines.append(f"- {d.folder_name}: 수정사항 없음")
                    lines.append(f"  {desc}")
                else:
                    lines.append(f"- {d.folder_name}: 수정사항 없음")

        if gitignored_warnings:
            lines.append("")
            lines.append("■ 민감 파일 보호")
            lines.append("")
            for w in gitignored_warnings:
                lines.append(f"- {w} → .gitignore로 이동")

        return lines
