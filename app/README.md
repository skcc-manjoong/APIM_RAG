# 클라우드 리소스 질의 봇

스트림릿(Streamlit)으로 구현된 클라우드 리소스 질의 UI와 FastAPI 서버를 통한 백엔드 통신 애플리케이션입니다.

## 기능

- 사용자가 자연어로 클라우드 리소스에 대한 질문 입력
- 왼쪽 사이드바에 질문 입력 및 자주 묻는 질문 표시
- 오른쪽 메인 영역에 채팅 형태로 결과 표시
- FastAPI 서버와 통신하여 질문에 대한 답변 제공
- 질문 처리 중 버튼 비활성화 기능

## 폴더 구조

```
app/
├── components/         # UI 컴포넌트
│   ├── sidebar.py      # 사이드바 컴포넌트
│   └── history.py      # 채팅 기록 관리
├── data/               # 데이터 저장 디렉토리
│   └── history/        # 채팅 기록 저장
├── utils/              # 유틸리티 함수
│   └── state_manager.py # 상태 관리
├── main.py             # 스트림릿 메인 앱
├── server.py           # FastAPI 서버
└── .env                # 환경 변수
```

## 실행 방법

### 1. 스트림릿 앱 실행

```bash
cd /path/to/app
streamlit run main.py
```

### 2. FastAPI 서버 실행

```bash
cd /path/to/app
uvicorn server:app --reload --port 8000
```

## 환경 변수 설정

`.env` 파일에 다음 환경 변수를 설정하세요:

```
API_BASE_URL=http://localhost:8000/api
```

## 개발 정보

- Python 3.8+
- Streamlit
- FastAPI
- Requests
