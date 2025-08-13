import traceback
import json
from retrieval.vector_db import VectorDB, get_global_vector_db
import re
from time import sleep
from pathlib import Path
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
            prompt = (
                "너는 APIM이라는 서비스의 관리자야. 아래 질문을 APIM 문서 검색에 적합한 대답을 해줘."
                f"\n질문: {question}"
            )
            llm_response = await self.llm.ainvoke(prompt)
            if hasattr(llm_response, "content"):
                content = llm_response.content.strip()
            else:
                content = str(llm_response).strip()

            # 따옴표로 감싸진 부분만 추출
            matches = re.findall(r'"([^"]+)"', content)
            english_query = matches[0] if matches else content

            # 2. 벡터DB에 영어 쿼리로 검색
            search_results = self.vector_db.search(english_query, k=5)

            # 3. state에 결과 저장 + 간단한 개요 메시지 남기기
            top_names = []
            for r in (search_results or [])[:3]:
                doc = r.get("document", {})
                top_names.append(doc.get("name", "chunk"))
            cnt = len(search_results) if search_results else 0
            overview = f"RAG를 통해 지식 저장소에서 {cnt}개의 청크를 조회했습니다."

            if state:
                state["rag_result"] = search_results
                state["messages"].append({"role": self.role, "content": f"[vector query] {english_query}"})
                state["messages"].append({"role": self.role, "content": overview})
                # 로그에서 보이도록 response도 설정
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