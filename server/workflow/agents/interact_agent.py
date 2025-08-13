import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
import traceback
from datetime import datetime
from bs4 import BeautifulSoup
from retrieval.vector_db import search_texts
from utils.prompts import build_final_answer_messages
from utils.config import get_llm_azopai
import re
from urllib.parse import urljoin

class InteractiveAgent:
    def __init__(self, llm=None):
        self.llm = llm or get_llm_azopai()
        self.role = "interactive_agent"
        self.base_url = "https://console.skapim.com"
        self.max_steps = 5  # 최대 탐색 단계
        
    async def run(self, state: dict = None, user_question: str = "", target_url: str = None) -> dict:
        try:
            print(f"[interactive_agent] 시작: 질문='{user_question}', URL='{target_url}'")
            if state and "navigation_result" in state:
                target_url = state["navigation_result"].get("target_url", target_url)
            if not target_url:
                target_url = f"{self.base_url}/gateway"

            async with async_playwright() as p:
                # Navigation에서 저장한 세션 상태 파일을 사용
                browser = await p.chromium.launch(headless=True)
                context = None
                if state and state.get("navigation_result"):
                    storage_state = state["navigation_result"].get("auth_state_path")
                    if storage_state:
                        storage_state_path = Path(storage_state)
                        if not storage_state_path.is_absolute():
                            server_root = Path(__file__).resolve().parents[2]
                            storage_state_path = (server_root / storage_state_path).resolve()
                        if storage_state_path.exists():
                            context = await browser.new_context(storage_state=str(storage_state_path))
                        else:
                            context = await browser.new_context()
                    else:
                        context = await browser.new_context()
                else:
                    context = await browser.new_context()
                page = await context.new_page()

                # 시작 URL 이동
                await page.goto(target_url)
                await page.wait_for_load_state('networkidle')

                # ReAct 루프: DOM 관찰 → 결정 → 실행
                current_url = page.url
                for step in range(self.max_steps):
                    print(f"[interactive_agent] ReAct step {step+1}/{self.max_steps}")

                    # Observation 1: DOM 요약
                    dom_text = await self._summarize_dom(page)
                    # Observation 2: RAG 스니펫
                    rag_snippets = search_texts(f"{user_question}\n{current_url}", k=5)

                    # Think: 다음 행동 결정
                    decision = await self._decide_next_action(user_question, current_url, dom_text, rag_snippets)
                    print(f"[interactive_agent] 결정: {decision}")

                    action = (decision.get("action") or "stop").lower()
                    target = (decision.get("target") or {})

                    if action == "goto":
                        url = target.get("value") or target.get("url") or ""
                        if not url:
                            break
                        # 비정상 URL은 클릭 폴백
                        if url.startswith("javascript:") or url.startswith("#"):
                            acted = await self._click_by(page, {"by": target.get("by") or "href", "value": url})
                            await page.wait_for_load_state('networkidle')
                            current_url = page.url if acted else current_url
                            continue
                        # 상대경로 → 절대 URL 보정
                        if not re.match(r'^https?://', url):
                            url = urljoin(current_url or self.base_url, url)
                        await page.goto(url)
                        await page.wait_for_load_state('networkidle')
                        current_url = page.url
                        continue

                    if action == "click":
                        acted = await self._click_by(page, target)
                        await page.wait_for_load_state('networkidle')
                        current_url = page.url if acted else current_url
                        continue

                    if action == "answer":
                        # 최종 답변 생성
                        messages = build_final_answer_messages(user_question, dom_text, rag_snippets)
                        final = await self.llm.ainvoke(messages)
                        final_text = getattr(final, "content", str(final)).strip()
                        response_msg = final_text
                        if state:
                            state.setdefault("messages", []).append({"role": self.role, "content": response_msg})
                            return {**state, "response": response_msg}
                        else:
                            return {"response": response_msg}

                    if action == "stop":
                        break

                # 루프 종료: answer에 도달 못하면 현재 근거로라도 답 생성
                dom_text = await self._summarize_dom(page)
                rag_snippets = search_texts(f"{user_question}\n{current_url}", k=5)
                messages = build_final_answer_messages(user_question, dom_text, rag_snippets)
                final = await self.llm.ainvoke(messages)
                final_text = getattr(final, "content", str(final)).strip()
                if state:
                    state.setdefault("messages", []).append({"role": self.role, "content": final_text})
                    return {**state, "response": final_text}
                else:
                    return {"response": final_text}

        except Exception as e:
            error_msg = f"❌ Interactive agent 오류: {str(e)}"
            print(f"[interactive_agent] 오류: {e}")
            traceback.print_exc()
            if state:
                state.setdefault("messages", []).append({"role": self.role, "content": error_msg})
                return {**state, "response": error_msg}
            else:
                return {"response": error_msg}

    async def _summarize_dom(self, page) -> str:
        """페이지 DOM을 요약(스크립트/스타일 제거, 헤딩/링크/버튼/문단 중심)"""
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        pieces = []
        title = soup.title.get_text(strip=True) if soup.title else ""
        if title:
            pieces.append(f"# {title}")
        # 헤딩 우선
        for hn in ["h1", "h2", "h3"]:
            for h in soup.find_all(hn):
                txt = h.get_text(" ", strip=True)
                if txt:
                    pieces.append(f"## {txt}")
        # 버튼/링크 텍스트
        for a in soup.find_all(["a", "button"]):
            txt = a.get_text(" ", strip=True)
            if not txt:
                continue
            href = a.get("href") or ""
            if href and len(href) > 120:
                href = href[:120] + "..."
            pieces.append(f"- {txt} {href}")
        # 일반 문단(상한)
        for p in soup.find_all(["p", "li"]):
            txt = p.get_text(" ", strip=True)
            if txt:
                pieces.append(txt)
            if len("\n".join(pieces)) > 2500:
                break
        dom_text = "\n".join(pieces)[:3000]
        return dom_text

    async def _decide_next_action(self, question: str, current_url: str, dom_text: str, rag_snippets: str) -> dict:
        """LLM으로 다음 Action 결정(JSON only)"""
        llm = self.llm
        system = (
            "너는 APIM 콘솔 내비게이터다. 다음 액션을 JSON으로만 반환해.\n"
            "스키마: {\"action\":\"goto|click|stop|answer\", \"target\":{\"by\":\"url|text|href|id\", \"value\":\"...\"}, \"reason\":\"...\", \"confidence\":0.0}\n"
            "절대 코드블록, 설명, 접두/접미 문구 없이 JSON 객체만 출력할 것"
        )
        prompt = f"""
사용자 질문: {question}
현재 URL: {current_url}

[DOM 요약]
{dom_text}

[RAG 스니펫]
{rag_snippets}

규칙:
- 불확실하면 stop 또는 answer 중 선택(근거로 충분하면 answer)
- click은 target.by/value를 정확히 지정
- goto는 절대/상대 URL 모두 허용
JSON만 출력.
"""
        try:
            resp = await llm.ainvoke(system + "\n\n" + prompt)
            text = getattr(resp, "content", resp)
        except Exception:
            resp_sync = llm.invoke(system + "\n\n" + prompt)
            text = getattr(resp_sync, "content", resp_sync)
        # 견고한 JSON 추출 로직
        try:
            s = (text or "").strip()
            m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", s)
            if m:
                s = m.group(1)
            else:
                start = s.find("{")
                end = s.rfind("}")
                if start != -1 and end != -1 and end > start:
                    s = s[start:end+1]
            data = json.loads(s)
            return data
        except Exception:
            print(f"[interactive_agent] decision parse failed; raw text: {(text or '')[:500]}")
            return {"action":"stop","reason":"parse_fail","confidence":0.0}

    async def _click_by(self, page, target: dict) -> bool:
        by = (target.get("by") or "").lower()
        value = target.get("value") or ""
        try:
            if by == "text" and value:
                await page.wait_for_selector(f"text={value}", timeout=10000)
                await page.click(f"text={value}")
                return True
            if by == "href" and value:
                try:
                    await page.wait_for_selector(f"a[href='{value}']", timeout=7000)
                    await page.click(f"a[href='{value}']")
                    return True
                except Exception:
                    await page.wait_for_selector(f"a[href*='{value}']", timeout=7000)
                    await page.click(f"a[href*='{value}']")
                    return True
            if by == "id" and value:
                await page.wait_for_selector(f"#{value}", timeout=10000)
                await page.click(f"#{value}")
                return True
        except Exception as e:
            print(f"[interactive_agent] _click_by 실패: {e}")
            return False
        return False 