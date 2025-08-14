# APIM QueryBot 개요 및 사용 안내

## 0. 무엇을 하나요?
APIM 서비스 관련 질문에 대해
- 문서 기반 RAG 결과와
- 실제 콘솔(UI) 탐색 기반 결과를
하나의 스트림에서 단계적으로 제공하는 에이전트입니다.

최종적으로는 실제 콘솔 화면 문서 기반 결과/접속 탐색 결과를 각각 표로 제공합니다.

---

## 1. 핵심 설계 포인트
- Prompt Engineering: 역할부여, CoT(비공개), Few-shot을 활용한 일관된 프롬프트 템플릿화
- Multi-Agent with LangGraph: 노드 단위로 역할 분리(문서 검색, 네비게이션, 인터랙션, 표 요약)
- RAG + Live UI: 문서(Vector DB)와 실제 콘솔 DOM 관찰을 결합한 하이브리드 답변
- Streaming UX: 단계별 진행 상태/결과를 실시간 전송 및 표시
- 친화적 오류 처리: 콘솔 접속 불가 등 예외 시 사용자 안내 메시지 출력

---

## 2. 현재 아키텍처(노드 흐름)
LangGraph 기반으로 다음 순서로 동작합니다.

1) rag: 문서(Vector DB) 검색
2) table_rag: 문서 기반 요약/표 생성(APIM Document 기반 결과)
3) ui_intro: "UI 접속 전 사용자 안내 프롬프팅"
4) navigation: 콘솔 세션 생성/로그인/시작 URL 확정
5) interactive: 콘솔에서 DOM 관찰 → 의사결정(JSON) → 행동(click/goto) 루프, 최종 DOM/URL/방문경로 기록
6) table_ui: 실제 탐색 결과를 단계별 요약/경로 표로 생성(실제 UI 단계별 설명)

Multi Agent Langraph 순서: rag → table_rag → ui_intro → navigation → interactive → table_ui → END

---

## 3. 스트리밍 표시 정책(프론트)
Streamlit(`app/main.py`)은 서버 스트림을 타입별로 구분해 표시합니다.
- 📚 APIM Document 기반 결과: table_rag
- 🧭 콘솔 진입 안내: ui_intro
- 🧭 네비게이션 진행: navigation
- 🔄 콘솔 탐색 중...: 진행 상태(progress)
- ✅ 인터랙션(최종): interactive 본문(필요 시) + table_ui 결과
- 🧭 실제 UI 단계별 설명: table_ui(최종 표)

참고: rag/table 원본문은 진행 메시지로 축약 표시하고, 최종은 interactive 이후의 table_ui가 중심이 됩니다.

---

## 4. 에이전트 구성
- RAGAgent (`server/workflow/agents/rag_agent.py`)
  - 한글 질문 → LLM으로 검색질의 변환 → Vector DB(FAISS) 검색 → 상위 청크 반환
- TableAgent (`server/workflow/agents/table_agent.py`)
  - 두 모드 지원
    - RAG 모드: 📚 APIM Document 기반 요약/표
    - UI 모드: 🧭 실제 UI 단계별 요약/경로 표(visit_trace + final DOM 기반)
- NavigationAgent (`server/workflow/agents/navigation_agent.py`)
  - 콘솔 포털 선택/접속, 로그인 세션 생성(auth_state.json 저장), 시작 URL 확정
- InteractiveAgent (`server/workflow/agents/interact_agent.py`)
  - DOM 관찰 → 결정(JSON) → 행동(click/goto) ReAct 루프
  - 각 이동 전후로 DOM 요약과 방문경로 기록(visit_trace)
  - 정책/Policy 리스트를 DOM에서 추출 시도해 최종 결과에 반영
  - 접속 불가/타임아웃/40x 등 예외 시 친절한 안내 메시지 반환

---

## 5. 벡터 DB 및 자료 전처리
- 위치: `server/retrieval/`
- 인덱스: FAISS(`apim_faiss_index.bin`), 메타(`apim_vector_data.pkl`)
- 초기화: 서버 시작 시 `server/main.py`의 lifespan 훅에서 `retrieval/apim_docs`를 자동 인덱싱
- 조회: `retrieval/vector_db.py`의 `search_texts(query, k)` 헬퍼를 통해 어디서든 간편 검색

---

## 6. 폴더 구조(요약)
```
cloud_bot/
├── app/
│   ├── main.py                      # Streamlit UI(스트리밍 표시/라벨)
│   ├── components/
│   │   └── sidebar.py
│   └── __init__.py
├── server/
│   ├── main.py                      # FastAPI 진입점(벡터DB 초기화, TOKENIZERS_PARALLELISM=false)
│   ├── routers/
│   │   └── workflow.py              # /api/v1/workflow/stream 스트리밍 엔드포인트
│   ├── workflow/
│   │   ├── graph.py                 # rag→table_rag→ui_intro→navigation→interactive→table_ui
│   │   ├── agents/
│   │   │   ├── rag_agent.py
│   │   │   ├── navigation_agent.py
│   │   │   ├── interact_agent.py
│   │   │   └── table_agent.py
│   │   └── __init__.py
│   ├── retrieval/
│   │   ├── apim_docs/               # APIM 문서(HTML/PDF)
│   │   ├── vector_db.py
│   │   ├── apim_vector_data.pkl
│   │   ├── apim_faiss_index.bin
│   │   └── __init__.py
│   └── utils/
│       ├── config.py                # LLM/Embeddings 설정
│       └── prompts.py               # 프롬프트 템플릿(역할/CoT/Few-shot)
├── requirements.txt
└── README.md
```

---

## 7. 동작 요약(엔드투엔드)
1) 서버 시작 시: APIM 문서 자동 인덱싱(필요하면 재인덱싱)
2) 사용자가 질문 입력 → Streamlit이 서버 스트림 구독
3) 서버 그래프 실행:
   - rag → table_rag(문서 기반 표)
   - ui_intro(콘솔 진입 안내)
   - navigation(로그인/시작 URL)
   - interactive(ReAct 탐색, visit_trace/DOM 추출)
   - table_ui(실제 UI 단계별 요약/경로 표)
4) Streamlit: 이벤트 타입별 라벨로 실시간 표시

---

## 8. 실행 방법
- 서버
  ```bash
  cd server
  python main.py
  ```
- 프론트
  ```bash
  cd app
  streamlit run main.py
  ```
- 환경 변수
  - `.env`에 LLM/Embeddings 관련 키를 설정
  - 서버는 자동으로 `TOKENIZERS_PARALLELISM=false`를 설정해 토크나이저 경고를 억제
  - Playwright 브라우저 설치(최초 1회, 같은 파이썬 환경에서 실행)
    ```bash
    python -m playwright install chromium
    # (리눅스) 시스템 의존성 필요 시
    python -m playwright install-deps chromium
    ```

---

## 9. 오류 처리(중요)
- 콘솔 접속 타임아웃/40x/네트워크 이슈 발생 시:
  - 다음 메시지를 사용자에게 안내합니다.
  - "apim 콘솔 페이지 접속이 어려워 접속 기반 정보제공이 어렵습니다. 잠시후 다시 시도해주세요"
- 프론트는 진행 상태를 유지하며, 가능하면 문서 기반 결과(table_rag)를 먼저 제공해 사용자 대기 시간을 줄입니다.

---

## 10. 특징 요약
- 문서 기반과 실제 UI 탐색 기반의 이원화 결과 제공
- 단계별 진행/DOM 관찰/클릭 경로를 최종 표로 깔끔하게 제공
- 정책/Policy 항목 DOM 추출 시도(가능한 경우 최종 결과에 직접 반영)
- 프롬프트 템플릿화로 일관 응답 품질 확보

---
