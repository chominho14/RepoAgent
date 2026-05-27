# alarm-project

서버에서 진행 중인 연구 프로젝트를 GitLab에 자동 동기화하고, 매일 지정한 시간에 당일 변경사항을 LLM으로 분석해 Telegram으로 전송하는 자동화 에이전트입니다.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)
![HuggingFace](https://img.shields.io/badge/HuggingFace-Transformers-FFD21E?logo=huggingface&logoColor=black)
![LangGraph](https://img.shields.io/badge/LangGraph-Pipeline-1C3C3C?logo=langchain&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-FF6B35)
![GitLab](https://img.shields.io/badge/GitLab-Auto%20Sync-FC6D26?logo=gitlab&logoColor=white)

## 주요 기능

- **자동 git sync** — 지정한 폴더를 GitLab에 자동 커밋·푸시 (민감 파일 자동 gitignore 처리)
- **LLM 일일 요약** — 당일 변경된 파일을 폴더별로 분석해 2문장 요약 생성
- **RAG 컨텍스트** — ChromaDB에 과거 변경 이력을 저장해 다음 날 분석에 활용
- **Telegram 알림** — 요약 결과를 Bot으로 전송, 커밋 여부를 대화로 확인
- **일일 리포트** — 변경 사항과 수정 없는 프로젝트 목록을 `날짜_report.txt`로 저장

## 버전 히스토리

| 버전 | 날짜 | 변경 내용 |
|---|---|---|
| v0.1 | 2026-05-27 | 폴더별 분리 커밋 — LLM 요약을 폴더 단위로 파싱해 커밋 메시지로 재사용; 리포트 저장 위치를 `reports/` 서브디렉토리로 변경 |
| v0.0 | 2026-05-26 | 최초 릴리즈 — git sync, LLM 일일 요약, RAG, Telegram 알림, 커밋 확인 기능 |

## 시스템 구조

```
매일 지정 시간
  │
  ├─ LLM 분석 (Qwen2.5-7B 온디맨드 로딩)
  ├─ RAG 검색 (ChromaDB)
  ├─ Telegram 요약 전송
  ├─ 리포트 파일 저장 (날짜_report.txt)
  ├─ "커밋을 진행할까요?" 질문
  │
  ├─ "응"  → GitLab push 즉시 실행
  ├─ "아니" → 커밋 건너뜀
  └─ 무응답 (자정까지) → 자동 커밋
```

## 요구사항

- Python 3.11
- CUDA GPU (Qwen2.5-7B 기준 약 14GB VRAM)
- GitLab 계정 및 Personal Access Token
- Telegram Bot Token ([BotFather](https://t.me/BotFather)에서 생성)
- HuggingFace Token (gated 모델 사용 시)

## 설치 및 설정

### 1. 환경 설정

```bash
# conda 환경 생성 (권장)
conda create -n alarm python=3.11 -y
conda activate alarm

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 4가지 값을 입력합니다.

```env
HF_TOKEN=hf_...              # HuggingFace API 토큰
GITLAB_TOKEN=glpat-...       # GitLab Personal Access Token
TELEGRAM_BOT_TOKEN=...       # Telegram Bot 토큰 (BotFather에서 발급)
TELEGRAM_CHAT_ID=...         # 본인 Telegram Chat ID
```

> **Telegram Chat ID 확인 방법** — Bot에게 메시지를 보낸 후 `https://api.telegram.org/bot<TOKEN>/getUpdates` 에 접속하면 `chat.id` 값을 확인할 수 있습니다.

### 3. config.yaml 설정

```yaml
gitlab:
  url: "https://your-gitlab-host"
  repo_url: "https://your-gitlab-host/group/repo-name.git"
  ssl_verify: false    # 사설 인증서 사용 시 false

sync:
  root_path: "/path/to/your/projects"    # 모니터링할 폴더 경로

notify:
  cron: "0 17 * * 1-5"    # 알림 시간 (평일 17:00)

project_descriptions:
  my-project: "프로젝트 한 줄 설명"    # 변경 없을 때 리포트에 표시

llm:
  model_id: "Qwen/Qwen2.5-7B-Instruct"    # 사용할 HuggingFace 모델
  device: "auto"
  max_new_tokens: 512
  language_blocking_enabled: true
```

## 실행

```bash
# 즉시 테스트 — git sync만 실행
python main.py --run-now sync

# 즉시 테스트 — LLM 분석 + Telegram 알림 실행
python main.py --run-now notify

# 데몬 모드 (스케줄에 따라 자동 실행)
nohup python main.py > logs/alarm.log 2>&1 &

# 실행 확인
pgrep -a -f "python main.py"

# 로그 실시간 확인
tail -f logs/alarm.log

# 데몬 종료
kill $(pgrep -f "python main.py")
```

## Docker 실행

```bash
docker-compose up -d
docker-compose logs -f
```


## 기술 스택

| 분류 | 기술 |
|---|---|
| 파이프라인 오케스트레이션 | LangGraph (StateGraph) |
| LLM 추론 | HuggingFace Transformers (AutoModelForCausalLM) |
| RAG | ChromaDB + sentence-transformers |
| 스케줄러 | APScheduler (BlockingScheduler) |
| Telegram | python-telegram-bot v21+ |
| Git 자동화 | GitPython |
| 설정 관리 | python-dotenv + PyYAML |

## 주의사항

- LLM은 알림 실행 시에만 로드되고 완료 후 즉시 해제됩니다 (GPU 메모리 절약).
- 민감 파일(`.env`, `*.key`, `*.pem` 등)이 감지되면 자동으로 `.gitignore`에 추가하고 Telegram으로 알림을 보냅니다.
- `ssl_verify: false`는 사설 SSL 인증서를 사용하는 내부 GitLab 서버용입니다. 공식 인증서라면 `true`로 변경하세요.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
