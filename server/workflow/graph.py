from langgraph.graph import StateGraph, END
from typing import Any, List, Dict
from utils.config import get_llm_azopai
import asyncio
from workflow.agents.table_agent import TableAgent
from workflow.agents.rag_agent import RAGAgent
from workflow.agents.screenshot_agent import ScreenshotAgent
import logging
import json

# 1. 상태 정의 (messages: List[Dict] with role, content)
class ApimQueryState(dict):
    messages: List[Dict]    # [{"role": "user|agent|system", "content": ...}, ...]
    response: str = None    # 각 agent 단계별 내역 및 최종 응답 리스트
    rag_result: dict = None  # ragagent가 찾은 관련 문서들
    screenshot_result: dict = None  # screenshot_agent가 캡처한 이미지 정보

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

# 4. ScreenshotAgent 노드 (웹페이지 스크린샷 캡처)
async def screenshot_node(state: ApimQueryState) -> ApimQueryState:
    screenshot_agent = ScreenshotAgent()
    result = await screenshot_agent.run(state=state, url="https://developers.skapim.com/")
    print(f"[screenshot_node] screenshot_agent 결과: {result.get('response')}")
    return result

# 5. LangGraph 워크플로우 정의
def create_apim_query_graph():
    print("[create_apim_query_graph] 워크플로우 생성 시작")
    workflow = StateGraph(ApimQueryState)
    workflow.add_node("rag", rag_node)
    workflow.add_node("table", table_node)
    workflow.add_node("screenshot", screenshot_node)
    workflow.add_edge("rag", "table")
    workflow.add_edge("table", "screenshot")
    workflow.add_edge("screenshot", END)
    workflow.set_entry_point("rag")
    print("[create_apim_query_graph] 워크플로우 생성 완료")
    return workflow.compile()

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    graph = create_apim_query_graph()

    # 2. 그래프 이미지(mermaid png) 생성 및 open
    graph_image = graph.get_graph().draw_mermaid_png()
    output_path = "apim_query_graph.png"
    with open(output_path, "wb") as f:
        f.write(graph_image)

    import subprocess
    subprocess.run(["open", output_path])
