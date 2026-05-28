# LLM에 전달할 일일 변경사항 요약 프롬프트 — 폴더별 2문장 + 과거 RAG 컨텍스트
from datetime import date

from services.diff_collector import FolderDiff

SYSTEM_PROMPT = """\
당신은 소프트웨어 개발 현황을 매일 정리해주는 AI 어시스턴트입니다.

[필수 출력 규칙]
1. 변경된 폴더마다 아래 형식으로만 출력하세요. 인사말·추가 설명은 절대 붙이지 마세요.
   🔹 {폴더명}
     {2문장. 첫 문장은 오늘 무엇이 바뀌었는지, 둘째 문장은 과거 패턴과 비교하거나 변경의 의미를 설명.}
2. 과거 변경 패턴이 제공된 경우 반드시 참고해 연속성 있는 분석을 작성하세요.
3. 반드시 한국어로만 작성하세요.
4. 중국어 한자, 일본어, 러시아어 문자는 절대 출력하지 마세요.\
"""


def build_summary_messages(
    diffs: list[FolderDiff],
    past_contexts: dict[str, str],
    code_analyses: dict[str, str],
) -> list[dict]:
    today = date.today().strftime("%Y-%m-%d")
    lines = [f"오늘({today}) 변경된 폴더들을 폴더별로 2문장씩 요약해주세요.\n"]

    for d in diffs:
        lines.append(f"## {d.folder_name}")
        if d.folder_name in past_contexts:
            lines.append("[과거 유사 변경 패턴 (참고용)]")
            lines.append(past_contexts[d.folder_name])
        # 코드 분석 결과(Coder 모델)가 있으면 우선 사용, 없으면 변경 통계로 대체
        if d.folder_name in code_analyses:
            lines.append("[코드 변경 분석]")
            lines.append(code_analyses[d.folder_name])
        else:
            lines.append("[변경 통계]")
            lines.append(d.stat_summary)
        lines.append("")

    return [
        {"role": "user", "content": f"{SYSTEM_PROMPT}\n\n" + "\n".join(lines)},
    ]
