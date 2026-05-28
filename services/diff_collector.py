# 루트 경로 하위 폴더별 당일 git 변경사항을 수집하는 서비스
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FolderDiff:
    folder_name: str
    has_changes: bool
    stat_summary: str = ""   # git diff --stat 원문 + 신규 파일 목록
    file_count: int = 0
    raw_diff: str = ""       # git diff HEAD patch 원문 (코드 분석용, 8000자 제한)


_MAX_RAW_DIFF_CHARS = 8000  # 폴더당 raw diff 최대 길이 (프롬프트 폭주 방지)


class DiffCollector:
    def collect(self, root_path: str) -> list[FolderDiff]:
        root = Path(root_path)
        if not (root / ".git").exists():
            logger.warning(f"git repo 없음: {root_path}")
            return []

        subdirs = sorted(
            d.name for d in root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        results = []
        for folder in subdirs:
            diff = self._collect_folder(root, folder)
            results.append(diff)
        return results

    def _collect_folder(self, root: Path, folder: str) -> FolderDiff:
        # notify는 commit 이전에 실행되므로 git log가 아닌 working tree의 미커밋 변경을 본다.
        # core.quotepath=false: 한글 등 비ASCII 경로를 이스케이프 없이 UTF-8로 출력
        env = {**os.environ, "GIT_SSL_NO_VERIFY": "true"}
        try:
            # 1) 추적 파일의 변경 (staged + unstaged) — HEAD 대비 diff stat
            diff = subprocess.run(
                ["git", "-c", "core.quotepath=false", "diff", "HEAD", "--stat", "--", f"{folder}/"],
                cwd=root, capture_output=True, text=True, timeout=30, env=env,
            )
            stat = diff.stdout.strip()

            # 2) 미추적 신규 파일
            others = subprocess.run(
                ["git", "-c", "core.quotepath=false", "ls-files", "--others",
                 "--exclude-standard", "--", f"{folder}/"],
                cwd=root, capture_output=True, text=True, timeout=30, env=env,
            )
            new_files = [f for f in others.stdout.splitlines() if f.strip()]

            if not stat and not new_files:
                return FolderDiff(folder, False)

            parts = []
            if stat:
                parts.append(stat)
            if new_files:
                listed = "\n".join(f"  + {f}" for f in new_files[:20])
                parts.append(f"신규 파일 {len(new_files)}개:\n{listed}")
            summary = "\n".join(parts)

            # 3) 실제 변경 코드(patch) — 코드 분석 모델용, 8000자 제한
            #    추적 파일 변경 + 신규(미추적) 파일 내용을 모두 diff 형태로 수집
            patch = subprocess.run(
                ["git", "-c", "core.quotepath=false", "diff", "HEAD", "--", f"{folder}/"],
                cwd=root, capture_output=True, text=True, timeout=30, env=env,
            )
            raw_diff = self._build_raw_diff(root, env, patch.stdout.strip(), new_files)

            file_count = sum(1 for line in stat.splitlines() if "|" in line) + len(new_files)
            return FolderDiff(
                folder_name=folder,
                has_changes=True,
                stat_summary=summary[:1500],
                file_count=file_count,
                raw_diff=raw_diff,
            )
        except Exception as e:
            logger.error(f"[{folder}] diff 수집 실패: {e}")
            return FolderDiff(folder, False)

    def _build_raw_diff(self, root: Path, env: dict, tracked_patch: str, new_files: list[str]) -> str:
        """추적 파일 변경 patch + 신규 파일 내용을 8000자 한도 내에서 합친다."""
        chunks = []
        total = 0
        if tracked_patch:
            chunks.append(tracked_patch)
            total += len(tracked_patch)

        # 신규(미추적) 파일은 git diff --no-index로 전체 내용을 diff 형태로 가져옴 (read-only)
        for f in new_files:
            if total >= _MAX_RAW_DIFF_CHARS:
                break
            result = subprocess.run(
                ["git", "-c", "core.quotepath=false", "diff", "--no-index", "--", os.devnull, f],
                cwd=root, capture_output=True, text=True, timeout=30, env=env,
            )
            content = result.stdout.strip()
            if content:
                chunks.append(content)
                total += len(content)

        raw_diff = "\n".join(chunks)
        if len(raw_diff) > _MAX_RAW_DIFF_CHARS:
            raw_diff = raw_diff[:_MAX_RAW_DIFF_CHARS] + "\n... (이하 생략)"
        return raw_diff
