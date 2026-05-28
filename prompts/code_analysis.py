# Coder 모델에 전달할 폴더별 코드 변경 분석 프롬프트
CODE_ANALYSIS_SYSTEM = """\
당신은 코드 변경(git diff)을 분석하는 시니어 개발자입니다.
주어진 diff를 읽고 아래 형식으로만 한국어로 간결하게 분석하세요.

[출력 형식]
- 변경 내용: 무엇이 바뀌었는지 코드 관점에서 1~2문장.
- 의미/영향: 이 변경이 무엇을 의도하며 어떤 영향·위험이 있는지 1문장.

규칙.
1. 함수명·변수명·클래스명 등 코드 식별자는 영어 그대로 쓰되, 설명 문장은 한국어로 작성하세요.
2. 인사말·사족 없이 위 두 항목만 출력하세요.
3. 중국어 한자, 일본어, 러시아어 문자는 절대 출력하지 마세요.\
"""


def build_code_analysis_messages(folder_name: str, raw_diff: str) -> list[dict]:
    user = (
        f"다음은 '{folder_name}' 폴더의 git diff입니다.\n\n"
        f"```diff\n{raw_diff}\n```\n\n"
        "위 변경을 분석해주세요."
    )
    return [{"role": "user", "content": f"{CODE_ANALYSIS_SYSTEM}\n\n{user}"}]
