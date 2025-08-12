from langgraph.graph import StateGraph, END
from typing import Any, List, Dict
from utils.config import get_llm_azopai
import asyncio
from workflow.agents.table_agent import TableAgent
from workflow.agents.rag_agent import RAGAgent
from workflow.agents.screenshot_agent import ScreenshotAgent
from workflow.agents.navigation_agent import NavigationAgent
from workflow.agents.interactive_agent import InteractiveAgent
import logging
import json

# 1. 상태 정의 (messages: List[Dict] with role, content)
class ApimQueryState(dict):
    messages: List[Dict]    # [{"role": "user|agent|system", "content": ...}, ...]
    response: str = None    # 각 agent 단계별 내역 및 최종 응답 리스트
    rag_result: dict = None  # ragagent가 찾은 관련 문서들
    screenshot_result: dict = None  # screenshot_agent가 캡처한 이미지 정보
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

# 4. NavigationAgent 노드 (적절한 페이지 찾기)
async def navigation_node(state: ApimQueryState) -> ApimQueryState:
    navigation_agent = NavigationAgent()
    
    # 사용자 질문과 RAG 결과 추출
    user_question = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "user"), "")
    rag_result_str = ""
    
    # rag_result가 리스트인지 딕셔너리인지 확인
    if state.get("rag_result"):
        rag_result = state["rag_result"]
        if isinstance(rag_result, list):
            # 리스트인 경우: 각 항목의 content 추출
            rag_result_str = "\n".join([
                chunk.get("content", "") if isinstance(chunk, dict) else str(chunk) 
                for chunk in rag_result[:3]  # 상위 3개만
            ])
        elif isinstance(rag_result, dict):
            # 딕셔너리인 경우: chunks 키에서 추출
            rag_chunks = rag_result.get("chunks", [])
            rag_result_str = "\n".join([chunk.get("content", "") for chunk in rag_chunks[:3]])
    
    result = await navigation_agent.run(state=state, user_question=user_question, rag_result=rag_result_str)
    print(f"[navigation_node] navigation_agent 결과: {result.get('response')}")
    return result

# 5. InteractiveAgent 노드 (자동 클릭 및 페이지 탐색)
async def interactive_node(state: ApimQueryState) -> ApimQueryState:
    interactive_agent = InteractiveAgent()
    
    # 사용자 질문 추출
    user_question = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "user"), "")
    
    # Navigation 결과에서 URL 가져오기
    target_url = None
    if state.get("navigation_result"):
        target_url = state["navigation_result"].get("target_url")
    
    result = await interactive_agent.run(state=state, user_question=user_question, target_url=target_url)
    print(f"[interactive_node] interactive_agent 결과: {result.get('response')}")
    return result

# 6. ScreenshotAgent 노드 (웹페이지 스크린샷 캡처) - 수정됨
async def screenshot_node(state: ApimQueryState) -> ApimQueryState:
    screenshot_agent = ScreenshotAgent()
    # navigation_result에서 URL을 가져오거나 기본값 사용
    result = await screenshot_agent.run(state=state, url=None)  # URL은 내부에서 결정
    print(f"[screenshot_node] screenshot_agent 결과: {result.get('response')}")
    return result

# 6. LangGraph 워크플로우 정의 (수정됨)
def create_apim_query_graph():
    # LangGraph 워크플로우 생성
    workflow = StateGraph(ApimQueryState)
    
    # 노드 추가
    workflow.add_node("rag", rag_node)
    workflow.add_node("table", table_node)
    workflow.add_node("navigation", navigation_node)  # 새로 추가
    workflow.add_node("interactive", interactive_node) # 새로 추가
    workflow.add_node("screenshot", screenshot_node)
    
    # 엣지 연결: RAG -> Table -> Navigation -> Screenshot -> END
    workflow.add_edge("rag", "table")
    workflow.add_edge("table", "navigation")  # 새로 추가
    workflow.add_edge("navigation", "interactive") # 새로 추가
    workflow.add_edge("interactive", "screenshot")  # 수정됨
    workflow.add_edge("screenshot", END)
    
    workflow.set_entry_point("rag")
    
    # 컴파일
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
