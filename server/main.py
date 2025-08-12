import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pathlib import Path
from retrieval.vector_db import init_global_vector_db

# from db.database import Base, engine  # DB 초기화 코드(주석처리)
# from routers import history  # debate 관련 라우터(주석처리)
from routers import workflow  # 클라우드 조회 워크플로우 라우터

# Base.metadata.create_all(bind=engine)  # DB 초기화(주석처리)

@asynccontextmanager
async def lifespan(app: FastAPI):
    root = Path(__file__).resolve().parents[0]
    retrieval_dir = root / 'retrieval'
    pdf_dir = retrieval_dir / 'apim_docs'
    vec_path = retrieval_dir / 'apim_vector_data.pkl'
    idx_path = retrieval_dir / 'apim_faiss_index.bin'
    init_global_vector_db(str(pdf_dir), str(vec_path), str(idx_path))
    yield

# FastAPI 인스턴스 생성
app = FastAPI(
    title="APIM QueryBot API",
    description="APIM 서비스 조회봇 API",
    version="0.1.0",
    lifespan=lifespan,
)

# app.include_router(history.router)  # debate 관련 라우터(주석처리)
app.include_router(workflow.router)  # 클라우드 조회 워크플로우 라우터

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)