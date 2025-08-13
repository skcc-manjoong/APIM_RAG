from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import asyncio
import json
from typing import Dict, Any, List, AsyncGenerator

# FastAPI 앱 생성
app = FastAPI(title="Cloud Bot API")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 배포 시에는 특정 도메인으로 제한하세요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 요청 모델
class QuestionRequest(BaseModel):
    question: str

# 응답 모델
class AnswerResponse(BaseModel):
    answer: str
    metadata: Dict[str, Any] = {}

# 일반 채팅 엔드포인트
@app.post("/api/chat", response_model=AnswerResponse)
async def chat(request: QuestionRequest):
    try:
        # 여기에 실제 질문 처리 로직을 구현합니다
        # 예: LLM 호출, 데이터베이스 쿼리 등
        
        # 임시 응답 (실제 구현에서는 이 부분을 대체하세요)
        question = request.question
        answer = f"당신의 질문 '{question}'에 대한 답변입니다. 이 부분은 실제 LLM이나 데이터 처리 로직으로 대체되어야 합니다."
        
        return AnswerResponse(
            answer=answer,
            metadata={"source": "demo", "confidence": 0.95}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 스트리밍 응답 생성 함수
async def generate_stream_response(question: str) -> AsyncGenerator[str, None]:
    """질문에 대한 응답을 스트리밍 방식으로 생성합니다."""
    # 실제 구현에서는 LLM이나 다른 서비스에서 스트리밍 응답을 받아 전달합니다
    
    # 임시 응답 (단어 단위로 스트리밍)
    response_parts = [
        "당신의 질문 '",
        question,
        "'에 대한 ",
        "답변을 ",
        "스트리밍 ",
        "방식으로 ",
        "제공합니다. ",
        "이 부분은 ",
        "실제 LLM이나 ",
        "데이터 처리 ",
        "로직으로 ",
        "대체되어야 ",
        "합니다."
    ]
    
    for part in response_parts:
        # 각 부분을 JSON 형식으로 전송
        yield f"data: {json.dumps({'assistant': {'response': part}})}\n\n"
        await asyncio.sleep(0.2)  # 스트리밍 효과를 위한 지연
    
    # 스트리밍 종료 신호
    yield f"data: {json.dumps({'type': 'end'})}\n\n"

# 스트리밍 채팅 엔드포인트
@app.post("/api/stream")
async def stream_chat(request: QuestionRequest):
    try:
        return StreamingResponse(
            generate_stream_response(request.question),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 서버 상태 확인 엔드포인트
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

# 직접 실행 시 서버 시작
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
