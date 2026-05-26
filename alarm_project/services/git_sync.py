# /data/mino/ot 전체를 단일 GitLab repo로 동기화하는 서비스
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from services.secret_scanner import scan_sensitive_files

_SECRETS_LOG = Path(__file__).parent.parent / "logs" / "gitignored_today.json"

logger = logging.getLogger(__name__)

_PYTHON_ML_GITIGNORE = """\
# Python
__pycache__/
*.py[cod]
*.so
.env
.venv/
venv/
*.egg-info/
.pytest_cache/
.ipynb_checkpoints/

# ML 모델 가중치 및 체크포인트
*.pt
*.pth
*.ckpt
*.safetensors
*.h5
*.pkl
*.bin
checkpoints/
pretrained/
saved_models/
weights/

# 데이터셋 및 결과 (대용량)
data/
dataset/
datasets/
results/
outputs/
experiments/
wandb/

# 압축 파일
*.zip
*.tar.gz
*.tar
*.gz
"""


@dataclass
class SyncResult:
    success: bool
    committed: bool
    error: str = ""
    gitignored_files: list[dict] = field(default_factory=list)


class GitSyncService:
    def __init__(self, root_path: str, remote_url: str, ssl_verify: bool = False):
        self._root = Path(root_path)
        self._remote_url = remote_url  # oauth2 토큰 포함된 URL
        self._env = {
            "GIT_SSL_NO_VERIFY": "true" if not ssl_verify else "false",
            "GIT_AUTHOR_NAME": "alarm-bot",
            "GIT_AUTHOR_EMAIL": "alarm@ctilab",
            "GIT_COMMITTER_NAME": "alarm-bot",
            "GIT_COMMITTER_EMAIL": "alarm@ctilab",
        }

    def sync(self) -> SyncResult:
        try:
            self._flatten_nested_git_dirs()
            self._init_if_needed()
            self._ensure_gitignore()
            gitignored = self._scan_and_protect()
            self._ensure_remote()
            committed = self._stage_and_commit()
            self._push()
            return SyncResult(True, committed, gitignored_files=gitignored)
        except Exception as e:
            logger.error(f"git sync 실패: {e}")
            return SyncResult(False, False, str(e))

    def _flatten_nested_git_dirs(self) -> None:
        """하위 폴더의 .git을 제거해 단일 repo로 통합."""
        for git_dir in self._root.rglob(".git"):
            if git_dir.parent == self._root:
                continue  # 루트 자신의 .git은 건드리지 않음
            shutil.rmtree(git_dir)
            logger.info(f"중첩 .git 제거: {git_dir}")

    def _init_if_needed(self) -> None:
        lock_file = self._root / ".git" / "index.lock"
        if lock_file.exists():
            lock_file.unlink()
            logger.warning(f"이전 실행의 락 파일 제거: {lock_file}")
        if not (self._root / ".git").exists():
            self._run(["git", "init", "-b", "main"])
            logger.info(f"git init: {self._root}")

    def _scan_and_protect(self) -> list[dict]:
        """민감 파일 탐지 → .gitignore 추가 → 이미 tracked 파일 제거 → 로그 기록."""
        found = scan_sensitive_files(self._root)
        if not found:
            return []

        gitignore = self._root / ".gitignore"
        existing = gitignore.read_text(encoding="utf-8")
        new_entries = [f.path for f in found if f.path not in existing]
        if new_entries:
            with gitignore.open("a", encoding="utf-8") as fp:
                fp.write("\n# alarm-bot 자동 감지 민감 파일\n")
                for entry in new_entries:
                    fp.write(f"{entry}\n")

        for f in found:
            try:
                tracked = self._run(["git", "ls-files", f.path], capture=True)
                if tracked.strip():
                    self._run(["git", "rm", "--cached", f.path])
                    logger.warning(f"민감 파일 tracking 해제: {f.path} ({f.reason})")
            except Exception as e:
                logger.error(f"git rm --cached 실패 [{f.path}]: {e}")

        entries = [{"file": f.path, "folder": f.folder, "reason": f.reason} for f in found]
        _SECRETS_LOG.parent.mkdir(exist_ok=True)
        _SECRETS_LOG.write_text(
            json.dumps({"date": str(date.today()), "entries": entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.warning(f"민감 파일 {len(found)}개 .gitignore로 이동: {[f.path for f in found]}")
        return entries

    def _ensure_gitignore(self) -> None:
        # 항상 덮어씀 — 사용자가 직접 편집한 경우는 config.yaml로 관리
        target = self._root / ".gitignore"
        target.write_text(_PYTHON_ML_GITIGNORE, encoding="utf-8")

    def _ensure_remote(self) -> None:
        result = self._run(["git", "remote"], capture=True)
        if "origin" not in result:
            self._run(["git", "remote", "add", "origin", self._remote_url])
        else:
            self._run(["git", "remote", "set-url", "origin", self._remote_url])

    def _stage_and_commit(self) -> bool:
        self._run(["git", "add", "-A"], timeout=1800)  # 대용량 폴더 대응 30분
        status = self._run(["git", "status", "--porcelain"], capture=True)
        if not status.strip():
            logger.info("변경사항 없음, 커밋 스킵")
            return False
        msg = self._build_commit_message()
        self._run(["git", "commit", "-m", msg])
        return True

    def _build_commit_message(self) -> str:
        """스테이지된 파일을 폴더별로 집계해 커밋 메시지 생성."""
        files = self._run(["git", "diff", "--cached", "--name-only"], capture=True)
        folders: dict[str, int] = {}
        for f in files.splitlines():
            top = f.split("/")[0] if "/" in f else "."
            folders[top] = folders.get(top, 0) + 1
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not folders:
            return f"auto: {date_str}"
        folder_lines = "\n".join(f"  {k}: {v}개 파일" for k, v in sorted(folders.items()))
        return f"auto: {date_str}\n\n{folder_lines}"

    def _push(self) -> None:
        # 최초 1회: remote에 초기 파일이 있을 경우 pull 후 push
        try:
            self._run(["git", "push", "-u", "origin", "main"])
        except RuntimeError:
            self._run(["git", "pull", "origin", "main",
                       "--allow-unrelated-histories", "--rebase"])
            self._run(["git", "push", "-u", "origin", "main"])

    def _run(self, cmd: list[str], capture: bool = False, timeout: int = 120) -> str:
        import os
        env = {**os.environ, **self._env}
        result = subprocess.run(
            cmd, cwd=self._root, capture_output=capture,
            text=True, env=env, timeout=timeout,
        )
        if result.returncode != 0 and not capture:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout if capture else ""
