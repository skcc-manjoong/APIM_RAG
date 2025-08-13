import traceback
import pandas as pd
import json
from utils.prompts import build_table_summary_messages, table_prompt_meta

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

        # 2. LLM 요약 (역할/규칙/형식 템플릿)
        evidence_block = "\n".join(evidence_lines)
        messages = build_table_summary_messages(user_request, context, evidence_block)
        try:
            # 로그: 프롬프트 메타(짧음) - 화면 표시 제거
            # (state 메시지에는 남기지 않음)
            summary_response = await self.llm.ainvoke(messages)
            summary = summary_response.content
            
            if state:
                header = "• Few-shot(3개) 적용\n• 분석 요약/표 생성"
                final_response = f"{header}\n\n{summary}"
                state["messages"].append({"role": self.role, "content": final_response})
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