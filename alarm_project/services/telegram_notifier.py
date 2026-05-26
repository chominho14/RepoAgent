# Telegram Bot을 통해 메시지를 전송하는 서비스
import asyncio
import logging
import time

from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        # Bot 인스턴스를 저장하지 않고 토큰만 보관 —
        # asyncio.run()마다 새 이벤트 루프가 생성되므로 Bot도 그 안에서 새로 만들어야 한다
        self._token = bot_token
        self._chat_id = chat_id

    def send(self, text: str) -> None:
        asyncio.run(self._send_async(text))

    def send_error(self, error_summary: str) -> None:
        self.send(f"⚠️ 오류 발생\n\n{error_summary}")

    def ask_commit_confirmation(self, timeout_seconds: int = 600) -> bool:
        """'커밋을 진행할까요?' 질문 후 응답을 기다려 True/False 반환."""
        return asyncio.run(self._ask_confirmation_async(timeout_seconds))

    async def _send_async(self, text: str) -> None:
        async with Bot(token=self._token) as bot:
            chunks = _split_message(text, limit=4000)
            try:
                for chunk in chunks:
                    await bot.send_message(
                        chat_id=self._chat_id,
                        text=chunk,
                        parse_mode="Markdown",
                    )
            except TelegramError as e:
                logger.error(f"Telegram 전송 실패: {e}")
                raise

    async def _ask_confirmation_async(self, timeout_seconds: int) -> bool:
        async with Bot(token=self._token) as bot:
            await bot.send_message(
                chat_id=self._chat_id,
                text="커밋을 진행할까요? (응/아니)",
            )

            # 현재까지의 업데이트를 소진해 이전 메시지가 응답으로 처리되지 않도록 한다
            prev = await bot.get_updates(timeout=0, limit=100)
            offset = (prev[-1].update_id + 1) if prev else 0

            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                poll_timeout = min(30, int(remaining))
                if poll_timeout <= 0:
                    break
                try:
                    updates = await bot.get_updates(
                        offset=offset, timeout=poll_timeout, allowed_updates=["message"]
                    )
                except Exception as e:
                    logger.warning(f"get_updates 실패: {e}")
                    continue

                for update in updates:
                    offset = update.update_id + 1
                    if not update.message:
                        continue
                    if str(update.message.chat_id) != str(self._chat_id):
                        continue
                    text = (update.message.text or "").strip()
                    if text in ("응", "예", "ㅇ", "yes", "y"):
                        return True
                    if text in ("아니", "아니오", "ㄴ", "no", "n"):
                        await bot.send_message(
                            chat_id=self._chat_id, text="커밋을 건너뜁니다."
                        )
                        return False

            await bot.send_message(
                chat_id=self._chat_id,
                text="⏰ 응답이 없어 자동으로 커밋을 진행합니다.",
            )
            return True


def _split_message(text: str, limit: int = 4000) -> list[str]:
    """줄 단위로 메시지를 분할해 마크다운 블록이 중간에 잘리지 않도록 한다."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0
    in_code_block = False

    for line in text.splitlines(keepends=True):
        if line.startswith("```"):
            in_code_block = not in_code_block

        if current_lines and current_len + len(line) > limit:
            chunk = "".join(current_lines)
            if in_code_block:
                chunk += "```\n"
            chunks.append(chunk)
            current_lines = []
            current_len = 0
            if in_code_block:
                current_lines.append("```\n")
                current_len = 4

        current_lines.append(line)
        current_len += len(line)

    if current_lines:
        chunks.append("".join(current_lines))

    return chunks
