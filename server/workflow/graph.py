from langgraph.graph import StateGraph, END
from typing import Any, List, Dict
from utils.config import get_llm_azopai
import asyncio
from workflow.agents.table_agent import TableAgent
from workflow.agents.rag_agent import RAGAgent
from workflow.agents.navigation_agent import NavigationAgent
from workflow.agents.interact_agent import InteractiveAgent
import logging
import json

# 1. 상태 정의 (messages: List[Dict] with role, content)
class ApimQueryState(dict):
    messages: List[Dict]    # [{"role": "user|agent|system", "content": ...}, ...]
    response: str = None    # 각 agent 단계별 내역 및 최종 응답 리스트
    rag_result: dict = None  # ragagent가 찾은 관련 문서들
    navigation_result: dict = None
    interactive_result: dict = None

# Agent 인스턴스 생성
async def get_llm():
    llm = get_llm_azopai()
    return llm

# 2. RAGAgent 노드 (질문 → 백터DB에서 관련 메서드 검색)
async def rag_node(state: ApimQueryState) -> ApimQueryState:
    llm = await get_llm()
    rag_agent = RAGAgent(llm)
    result = await rag_agent.run(state=state)
    print(f"[rag_node] rag_agent 결과: {result.get('response')}")
    return result

# 3. TableAgent 노드 (RAG 결과 → 표 요약)
async def table_node(state: ApimQueryState) -> ApimQueryState:
    llm = await get_llm()
    table_agent = TableAgent(llm)
    result = await table_agent.run(state=state)
    print(f"[table_node] table_agent 결과: {result.get('response')}")
    return result

# 4. NavigationAgent 노드 (로그인 및 시작 URL 결정/이동)
async def navigation_node(state: ApimQueryState) -> ApimQueryState:
    navigation_agent = NavigationAgent()
    user_question = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "user"), "")
    # rag_result는 선택적으로 전달(문자열로 축약)
    rag_str = ""
    if state.get("rag_result"):
        rag = state["rag_result"]
        if isinstance(rag, list):
            rag_str = "\n".join([ (r.get("document",{}).get("search_text",""))[:200] for r in rag[:3] ])
    result = await navigation_agent.run(state=state, user_question=user_question, rag_result=rag_str)
    print(f"[navigation_node] navigation_agent 결과: {result.get('response')}")
    return result

# 5. InteractiveAgent 노드 (ReAct 루프: DOM 관찰+RAG → 행동 → 최종 답)
async def interactive_node(state: ApimQueryState) -> ApimQueryState:
    interactive_agent = InteractiveAgent()
    user_question = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "user"), "")
    target_url = None
    if state.get("navigation_result"):
        target_url = state["navigation_result"].get("target_url")
    result = await interactive_agent.run(state=state, user_question=user_question, target_url=target_url)
    print(f"[interactive_node] interactive_agent 결과: {result.get('response')}")
    return result

# 6. LangGraph 워크플로우 정의
def create_apim_query_graph():
    print("[create_apim_query_graph] 워크플로우 생성 시작")
    workflow = StateGraph(ApimQueryState)
    workflow.add_node("rag", rag_node)
    workflow.add_node("table", table_node)
    workflow.add_node("navigation", navigation_node)
    workflow.add_node("interactive", interactive_node)
    workflow.add_edge("rag", "table")
    workflow.add_edge("table", "navigation")
    workflow.add_edge("navigation", "interactive")
    workflow.add_edge("interactive", END)
    workflow.set_entry_point("rag")
    print("[create_apim_query_graph] 워크플로우 생성 완료")
    return workflow.compile()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    graph = create_apim_query_graph()

    # 2. 그래프 이미지(mermaid png) 생성 및 open
    graph_image = graph.get_graph().draw_mermaid_png()
    output_path = "apim_query_graph.png"
    with open(output_path, "wb") as f:
        f.write(graph_image)

    import subprocess
    subprocess.run(["open", output_path])
