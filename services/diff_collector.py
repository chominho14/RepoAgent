# /data/mino/ot 하위 폴더별 당일 git 변경사항을 수집하는 서비스
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
    stat_summary: str = ""   # git log --stat 원문
    file_count: int = 0


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
        env = {**os.environ, "GIT_SSL_NO_VERIFY": "true"}
        try:
            result = subprocess.run(
                ["git", "log", "--since=midnight", "--stat", "--oneline", "--", f"{folder}/"],
                cwd=root, capture_output=True, text=True, timeout=30, env=env,
            )
            output = result.stdout.strip()
            if not output:
                return FolderDiff(folder, False)

            # 변경된 파일 수 파악
            file_count = output.count("\n |") + output.count("\n  ")
            return FolderDiff(
                folder_name=folder,
                has_changes=True,
                stat_summary=output[:1500],
                file_count=file_count,
            )
        except Exception as e:
            logger.error(f"[{folder}] diff 수집 실패: {e}")
            return FolderDiff(folder, False)
