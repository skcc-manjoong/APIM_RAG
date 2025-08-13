import traceback
import json
from retrieval.vector_db import VectorDB, get_global_vector_db
import re
from time import sleep
from pathlib import Path
from utils.prompts import build_rag_query_messages, rag_prompt_meta
class RAGAgent:
    def __init__(self, llm):
        self.llm = llm
        self.role = "ragagent"
        # 전역 VectorDB 사용 (startup에서 초기화됨)
        self.vector_db = get_global_vector_db() or VectorDB()

    async def run(self, state: dict = None, question: str = None) -> dict:
        # state 객체가 있으면 그것을 사용, 없으면 question만 사용
        if state:
            question = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "user"), question or "")
        if not question:
            return {"error": "No question provided"}

        try:
            # 1. LLM에게 검색 키워드(한 문장)로 변환 요청 (APIM 관리자 역할)
            messages = build_rag_query_messages(question)
            # 로그: 프롬프트 메타(짧음)
            if state is not None:
                state.setdefault("messages", []).append({"role": self.role, "content": rag_prompt_meta()})
            llm_response = await self.llm.ainvoke(messages)
            content = getattr(llm_response, "content", str(llm_response)).strip()
            try:
                parsed = json.loads(content)
                english_query = parsed.get("english_query") or content
            except Exception:
                english_query = content

            # 2. 벡터DB에 영어 쿼리로 검색
            search_results = self.vector_db.search(english_query, k=5)

            # 3. state에 결과 저장 + 간단한 개요 메시지 남기기
            cnt = len(search_results) if search_results else 0
            overview = f"• Few-shot(3개) 적용\n• RAG {cnt}개 조회"

            if state:
                state["rag_result"] = search_results
                # 화면에는 간결 요약만 노출
                state["messages"].append({"role": self.role, "content": overview})
                state["response"] = overview
                return state
            else:
                return {"rag_result": search_results, "vector_query": english_query}

        except Exception as e:
            error_msg = f"RAG 검색 실패: {str(e)}"
            print(f"[ERROR][RAGAgent] {error_msg}")
            traceback.print_exc()
            if state:
                state["messages"].append({"role": "error", "content": error_msg})
                return {**state, "rag_result": None, "response": error_msg}
            else:
                return {"rag_result": None, "error": str(e)} 