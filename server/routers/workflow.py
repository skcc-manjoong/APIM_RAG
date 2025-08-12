from fastapi import APIRouter
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
import asyncio
import json
from workflow.graph import create_apim_query_graph, ApimQueryState
import logging
import os
from pathlib import Path

router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["workflow"],
    responses={404: {"description": "Not found"}},
)

class QueryRequest(BaseModel):
    question: str

async def apim_query_streamer(question):
    logging.info(f"[apim_query_streamer] 질문 수신: {question}")
    graph = create_apim_query_graph()
    initial_state: ApimQueryState = {
        "messages": [{"role": "user", "content": question}]
    }
    chunk_count = 0
    async for chunk in graph.astream(initial_state, stream_mode="updates"):
        if not chunk:
            continue
        chunk_count += 1
        logging.info(f"[apim_query_streamer] chunk {chunk_count}: {chunk}")
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.01)
    logging.info(f"[apim_query_streamer] 스트림 종료 (총 {chunk_count}개 chunk)")
    yield f"data: {json.dumps({'type': 'end'}, ensure_ascii=False)}\n\n"

@router.post("/stream")
async def stream_apim_query(request: QueryRequest):
    logging.info(f"[stream_apim_query] POST /stream 요청: {request}")
    return StreamingResponse(
        apim_query_streamer(request.question),
        media_type="text/event-stream",
    )

@router.get("/screenshot/{filename}")
async def get_screenshot(filename: str):
    """스크린샷 파일을 반환합니다."""
    screenshot_path = Path("screenshots") / filename
    if screenshot_path.exists() and screenshot_path.is_file():
        return FileResponse(
            path=str(screenshot_path),
            media_type="image/png",
            filename=filename
        )
    else:
        return {"error": "Screenshot not found"}
