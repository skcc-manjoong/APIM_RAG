import traceback
import pandas as pd
import json

class TableAgent:
    def __init__(self, llm):
        self.llm = llm
        self.role = "tableagent"
        
    async def run(self, state=None, cloud_result=None, user_request=None):
        # state 객체가 있으면 그것을 사용, 없으면 인자값만 사용
        if state:
            cloud_result = state.get("cloud_result")
            rag_result = state.get("rag_result") or []
            user_request = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "user"), "")
            if not cloud_result and not rag_result:
                error_msg = "클라우드 결과나 RAG 결과가 없습니다"
                state["messages"].append({"role": "error", "content": error_msg})
                return {**state, "response": f"요약 실패: {error_msg}"}
                
        # 1. 컨텍스트 구성: rag_result 상위 청크만 추출 + 근거 준비
        evidence_lines = []
        if not cloud_result:
            top_k = 5
            chunks = []
            for i, r in enumerate(rag_result[:top_k], 1):
                doc = r.get("document", {})
                name = doc.get("name", f"chunk_{i}")
                snippet = (doc.get("search_text", "") or "").strip().replace("\n", " ")[:200]
                sim = r.get("similarity")
                evidence_lines.append(f"- {name} (sim={sim:.2f}): {snippet}")
                chunks.append(doc.get("search_text", ""))
            context = "\n\n---\n\n".join(chunks)
        else:
            context = cloud_result

        # 2. LLM 요약 (컨텍스트 외 추론 금지 + 표 강제)
        evidence_block = "\n".join(evidence_lines)
        summary_prompt = f"""
역할: 너는 APIM 관리자다. 아래 컨텍스트만을 근거로 간결한 설명과 표(마크다운)를 생성하라.
규칙:
- 컨텍스트에 없는 사실은 쓰지 말 것(추론/상식 금지)
- 표는 헤더 포함, 최대 10행
- 답변 마지막에 '근거' 섹션으로 사용한 청크 리스트를 그대로 포함할 것

[사용자 요청]
{user_request}

[컨텍스트]
{context}

[근거]
{evidence_block}
"""
        try:
            summary_response = await self.llm.ainvoke([{"role": "user", "content": summary_prompt}])
            summary = summary_response.content
            
            # state 객체가 있으면 업데이트, 없으면 summary만 반환
            if state:
                final_response = f"요약한 결과입니다.\n\n{summary}"
                state["messages"].append({"role": self.role, "content": summary})
                return {**state, "response": final_response}
            else:
                return {"summary": summary}
                
        except Exception as e:
            error_msg = f"요약 실패: {str(e)}"
            traceback.print_exc()
            
            if state:
                state["messages"].append({"role": "error", "content": error_msg})
                return {**state, "response": error_msg}
            else:
                return {"summary": error_msg} 