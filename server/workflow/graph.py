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

# RAGAgent 노드
async def rag_node(state: ApimQueryState) -> ApimQueryState:
    llm = await get_llm()
    rag_agent = RAGAgent(llm)
    result = await rag_agent.run(state=state)
    print(f"[rag_node] rag_agent 결과: {result.get('response')}")
    return result

# TableAgent 노드 공용
async def table_node(state: ApimQueryState) -> ApimQueryState:
    llm = await get_llm()
    table_agent = TableAgent(llm)
    result = await table_agent.run(state=state)
    print(f"[table_node] table_agent 결과: {result.get('response')}")
    return result

# UI 진입 안내 노드
async def ui_intro_node(state: ApimQueryState) -> ApimQueryState:
    msg = "이제 직접 콘솔에 들어가서 확인해 보겠습니다. 잠시만 기다려주세요..."
    state.setdefault("messages", []).append({"role": "system", "content": msg})
    print(f"[ui_intro_node] {msg}")
    return {**state, "response": msg}

# NavigationAgent 노드
async def navigation_node(state: ApimQueryState) -> ApimQueryState:
    navigation_agent = NavigationAgent()
    user_question = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "user"), "")
    rag_str = ""
    if state.get("rag_result"):
        rag = state["rag_result"]
        if isinstance(rag, list):
            rag_str = "\n".join([ (r.get("document",{}).get("search_text",""))[:200] for r in rag[:3] ])
    result = await navigation_agent.run(state=state, user_question=user_question, rag_result=rag_str)
    print(f"[navigation_node] navigation_agent 결과: {result.get('response')}")
    return result

# InteractiveAgent 노드
async def interactive_node(state: ApimQueryState) -> ApimQueryState:
    interactive_agent = InteractiveAgent()
    user_question = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "user"), "")
    target_url = None
    if state.get("navigation_result"):
        target_url = state["navigation_result"].get("target_url")
    result = await interactive_agent.run(state=state, user_question=user_question, target_url=target_url)
    print(f"[interactive_node] interactive_agent 결과: {result.get('response')}")
    return result

# LangGraph 워크플로우 정의
def create_apim_query_graph():
    print("[create_apim_query_graph] 워크플로우 생성 시작")
    workflow = StateGraph(ApimQueryState)
    workflow.add_node("rag", rag_node)
    workflow.add_node("table_rag", table_node)
    workflow.add_node("ui_intro", ui_intro_node)
    workflow.add_node("navigation", navigation_node)
    workflow.add_node("interactive", interactive_node)
    workflow.add_node("table_ui", table_node)
    workflow.add_edge("rag", "table_rag")
    workflow.add_edge("table_rag", "ui_intro")
    workflow.add_edge("ui_intro", "navigation")
    workflow.add_edge("navigation", "interactive")
    workflow.add_edge("interactive", "table_ui")
    workflow.add_edge("table_ui", END)
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
