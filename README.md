# APIM_QUERYBOT 폴더 구조 및 역할 안내

## 0. Agent 개요

APIM 서비스 문서를 자연어로 쉽게 조회하고 관리할 수 있는 지능형 Agent를 구현했습니다.

LangGraph를 활용한 RAG기반의 아키텍처를 통해,
사용자의 자연어 질의를 정확하게 이해하고 APIM 서비스 문서에서 필요한 정보를 검색하여,
실시간으로 관련 정보를 제공합니다.

특히 HTML 및 PDF 문서 처리를 통해 Notion 기반 문서도 지원하며,
Agent가 수행한 내역을 표 형태로 요약해 사용자에게 명확한 정보를 전달합니다.

사용자는 직접검색뿐만 아니라 FAQ 버튼을 통해서 자주 사용하는 질문을 쉽게 선택하여 조회할 수 있습니다.

전개도를 통해서 대략적인 아키텍처를 확인할수있고,
랭그래프를 통해서 내부적인 flow를 확인할수있습니다.
<!-- 
- 전개도
![전개도](전개도.png)

- 랭그래프
![랭그래프](apim_query_graph.png) -->

---

## 1. 전체 폴더 구조 (2025.01.23 기준)

```
cloud_bot/
├── app/
│   ├── components/
│   │   ├── sidebar.py
│   │   └── __init__.py
│   ├── main.py
│   └── __init__.py
├── server/
│   ├── retrieval/
│   │   ├── apim_docs/
│   │   │   └── (HTML/PDF 문서들)
│   │   ├── vector_db.py
│   │   ├── apim_vector_data.pkl
│   │   ├── apim_faiss_index.bin
│   │   └── __init__.py
│   ├── routers/
│   │   ├── workflow.py
│   │   └── __init__.py
│   ├── workflow/
│   │   ├── agents/
│   │   │   ├── rag_agent.py
│   │   │   ├── table_agent.py
│   │   │   └── __init__.py
│   │   ├── graph.py
│   │   └── __init__.py
│   ├── utils/
│   │   ├── config.py
│   │   └── __init__.py
│   ├── main.py
│   └── __init__.py
├── requirements.txt
└── README_CLOUD_QUERYBOT.md
```

---

## 2. 주요 기술스택

- **Streamlit**: 프론트엔드 UI 및 사용자 인터랙션
- **FastAPI**: 백엔드 API 서버
- **LangChain, LangGraph**: LLM 기반 에이전트 워크플로우 및 그래프 관리
- **FAISS**: 벡터 인덱스 검색 엔진
- **SentenceTransformers**: 텍스트 임베딩 생성
- **BeautifulSoup**: HTML 문서 파싱
- **pypdf**: PDF 문서 파싱
- **OpenAI API**: LLM 모델 (Azure OpenAI 지원)

---

## 3. 폴더/파일별 역할

### [app/]
- **main.py**: Streamlit 기반 메인 UI, APIM 서비스 문서 조회 요청/결과 표시, API 연동, 세션 관리 등 전체 프론트엔드 로직의 중심.
  - 실시간 스트리밍 응답 처리 및 표시
  - 타입별(rag, table) 응답 구분 및 레이블링
  - 세션 상태 관리 및 에러 처리
- **components/sidebar.py**: 사이드바 UI, 질문 입력 폼, APIM 관련 FAQ 등 렌더링.

### [server/]
- **main.py**: FastAPI 서버 진입점, 라우터 등록, 벡터 DB 초기화.
- **routers/workflow.py**: APIM 서비스 문서 조회 API
  - 스트리밍 응답 생성 및 전송
  - 각 에이전트의 응답을 실시간으로 클라이언트에 전달
- **retrieval/vector_db.py**: APIM 문서의 HTML/PDF 파싱, 벡터 임베딩 생성, FAISS 인덱스 관리.
- **retrieval/apim_docs/**: APIM 서비스 관련 HTML/PDF 문서 저장소.
- **workflow/graph.py**: LangGraph 기반 APIM 문서 조회 워크플로우 정의, 각 Agent 노드 연결.
- **workflow/agents/rag_agent.py**: 자연어 질문을 영어 키워드로 변환하고 벡터 DB에서 관련 문서 검색.
- **workflow/agents/table_agent.py**: RAG 결과를 표로 가공하고, 결과 요약 및 근거 생성.
- **utils/config.py**: LLM 설정 및 API 키 관리.

---

## 4. 동작 흐름 요약 (2025.01 기준)

1. **서버 시작 시**: HTML/PDF 문서를 자동으로 벡터 DB에 인덱싱 (startup lifespan)
2. **사용자**가 Streamlit UI에서 APIM 서비스 관련 질문 입력
3. **app/main.py**가 FastAPI 서버의 `/api/v1/workflow/stream` 엔드포인트로 스트리밍 요청
4. **server/routers/workflow.py**가 질문을 받아 LangGraph 워크플로우(`workflow/graph.py`) 실행
5. **workflow/graph.py**에서 각 Agent를 노드로 연결해 순차 실행:
    - **rag_agent**: 한글 질문을 영어 키워드로 변환하고 벡터 DB에서 관련 문서 검색
    - **table_agent**: RAG 결과를 표로 가공하고 요약 및 근거 생성
6. 각 Agent의 결과를 실시간으로 스트리밍하여 사용자에게 전달:
    - 문서 검색 결과
    - 결과 분석 및 표 형태 요약
    - 사용된 문서 청크들의 근거 제시
7. 프론트엔드에서 각 타입별 응답을 구분하여 실시간으로 표시

---

## 5. 서버 기동 방법

1. **필수 패키지 설치**
    ```bash
    pip install -r requirements.txt
    ```

2. **환경 변수 설정**
    ```bash
    # .env 파일 생성 후 OpenAI API 키 설정
    OPENAI_API_KEY=your_api_key_here
    ```

3. **APIM 문서 준비**
    ```bash
    # server/retrieval/apim_docs/ 디렉토리에 HTML/PDF 파일 배치
    ```

4. **서버 실행**
    ```bash
    # FastAPI 서버
    cd server
    python main.py

    # Streamlit 프론트엔드 (새 터미널)
    cd app
    streamlit run main.py
    ```

---

## 6. 벡터 DB 관리

- **자동 인덱싱**: 서버 시작 시 `apim_docs/` 디렉토리의 문서들을 자동으로 벡터화
- **HTML 우선**: HTML과 PDF가 모두 있으면 HTML을 우선 처리
- **재인덱싱**: 문서 파일이 변경되면 자동으로 재인덱싱
- **청크 크기**: 2500자 청크, 300자 오버랩으로 최적화
- **저장 위치**: 
  - `apim_vector_data.pkl`: 문서 메타데이터
  - `apim_faiss_index.bin`: FAISS 벡터 인덱스

---

## 7. 주요 기능 및 특징

- 실시간 스트리밍 응답 처리 및 표시
- HTML/PDF 문서 자동 파싱 및 벡터화
- 한글 질문을 영어 키워드로 변환하여 정확한 검색 지원
- RAG를 통한 정확한 APIM 문서 검색
- 표 형태의 결과 요약 및 근거 제시
- Notion HTML export 지원 (하위 디렉토리 포함)
- 에러 처리 및 상태 관리
- APIM 관련 맞춤형 FAQ 제공

---

## 8. 향후 개선 방향

- 이미지 캡처 노드 추가 (스크린샷 기능)
- 다양한 문서 형식 지원 확장 (Word, Markdown 등)
- RAG 정확도 개선 (청크 크기 최적화, 하이브리드 검색)
- 실시간 스트리밍 UI/UX 개선
- 멀티모달 지원 (이미지 + 텍스트)
- 대화 기록 저장 및 관리

---

이 문서는 APIM 서비스 조회봇의 현재 구현 상태와 주요 기능을 설명합니다. 프로젝트의 구조, 동작 방식, 기술 스택을 이해하는데 도움이 될 것입니다. 