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
from urllib.parse import urljoin, urlparse

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

                visit_trace = []  # 각 스텝별 관찰/행동 로그
                current_url = page.url

                # 최초 접속 직후 DOM 관찰을 강제 기록
                initial_dom = await self._summarize_dom(page)
                visit_trace.append({
                    "step": 0,
                    "url": current_url,
                    "path": urlparse(current_url).path,
                    "observation": initial_dom[:800]
                })

                # ReAct 루프: DOM 관찰 → 결정 → 실행
                for step in range(self.max_steps):
                    print(f"[interactive_agent] ReAct step {step+1}/{self.max_steps}")

                    # Observation 1: DOM 요약
                    dom_text = await self._summarize_dom(page)
                    # Observation 2: RAG 스니펫
                    rag_snippets = search_texts(f"{user_question}\n{current_url}", k=5)

                    # Think: 다음 행동 결정 (첫 스텝에서는 answer 금지 권고)
                    decision = await self._decide_next_action(user_question, current_url, dom_text, rag_snippets, step)
                    print(f"[interactive_agent] 결정: {decision}")

                    action = (decision.get("action") or "stop").lower()
                    target = (decision.get("target") or {})

                    # 방문 로그에 관찰/결정 기록
                    visit_trace.append({
                        "step": step + 1,
                        "url": current_url,
                        "path": urlparse(current_url).path,
                        "decision": decision,
                        "observation": dom_text[:800]
                    })
                    # 진행중 메시지(프론트에서 progress로 표시)
                    if state is not None:
                        state.setdefault("messages", []).append({
                            "role": self.role,
                            "content": f"해당 페이지에서 탐색 중... (step {step+1}) URL: {current_url}",
                            "chunk_type": "progress"
                        })

                    if action == "goto":
                        url = target.get("value") or target.get("url") or ""
                        # by='text'인 goto는 링크/버튼 클릭으로 처리
                        if (target.get("by") or "").lower() == "text":
                            acted = await self._click_by(page, {"by": "text", "value": url})
                            await page.wait_for_load_state('networkidle')
                            current_url = page.url if acted else current_url
                            post_dom = await self._summarize_dom(page)
                            visit_trace.append({
                                "step": f"{step+1}.post",
                                "url": current_url,
                                "path": urlparse(current_url).path,
                                "observation": post_dom[:800],
                                "action_result": f"goto-as-click:{url}"
                            })
                            continue
                        if not url:
                            break
                        # 비정상 URL은 클릭 폴백
                        if url.startswith("javascript:") or url.startswith("#"):
                            acted = await self._click_by(page, {"by": target.get("by") or "href", "value": url})
                            await page.wait_for_load_state('networkidle')
                            current_url = page.url if acted else current_url
                            # 이동 후 즉시 DOM 재관찰 기록
                            post_dom = await self._summarize_dom(page)
                            visit_trace.append({
                                "step": f"{step+1}.post",
                                "url": current_url,
                                "path": urlparse(current_url).path,
                                "observation": post_dom[:800],
                                "action_result": "click-fallback"
                            })
                            continue
                        # 상대경로 → 절대 URL 보정
                        if not re.match(r'^https?://', url):
                            url = urljoin(current_url or self.base_url, url)
                        await page.goto(url)
                        await page.wait_for_load_state('networkidle')
                        current_url = page.url
                        # 이동 후 즉시 DOM 재관찰 기록
                        post_dom = await self._summarize_dom(page)
                        visit_trace.append({
                            "step": f"{step+1}.post",
                            "url": current_url,
                            "path": urlparse(current_url).path,
                            "observation": post_dom[:800]
                        })
                        continue

                    if action == "click":
                        # 로그인 완료 상태면 'Login' 클릭 회피
                        try:
                            if state and state.get("navigation_result", {}).get("login_completed") and (target.get("by") or "").lower() == "text" and (target.get("value") or "").strip().lower() == "login":
                                print("[interactive_agent] 로그인 완료 상태: 'Login' 클릭 무시")
                                continue
                        except Exception:
                            pass
                        acted = await self._click_by(page, target)
                        await page.wait_for_load_state('networkidle')
                        current_url = page.url if acted else current_url
                        # 클릭 후 즉시 DOM 재관찰 기록
                        post_dom = await self._summarize_dom(page)
                        visit_trace.append({
                            "step": f"{step+1}.post",
                            "url": current_url,
                            "path": urlparse(current_url).path,
                            "observation": post_dom[:800],
                            "action_result": f"clicked:{target}"
                        })
                        continue

                    if action == "answer":
                        # 최종 답변 생성: 반드시 방문 경로/링크/클릭 요소 포함
                        trace_block = self._format_trace_block(visit_trace)
                        final_dom = await self._summarize_dom(page)
                        # 정책 페이지 감지 시 정책 항목을 DOM에서 추가 추출
                        policy_items = await self._extract_policies(page)
                        rag_snips = search_texts(f"{user_question}\n{current_url}", k=5)
                        if policy_items:
                            final_dom = f"[정책 항목]\n- " + "\n- ".join(policy_items[:20]) + "\n\n" + final_dom
                        messages = self._build_answer_with_trace(user_question, final_dom, rag_snips, trace_block)
                        final = await self.llm.ainvoke(messages)
                        final_text = getattr(final, "content", str(final)).strip()
                        response_msg = final_text
                        if state:
                            state.setdefault("interactive_result", {})["visit_trace"] = visit_trace
                            state.setdefault("interactive_result", {})["final_dom"] = final_dom
                            state.setdefault("interactive_result", {})["final_url"] = current_url
                            state.setdefault("messages", []).append({"role": self.role, "content": response_msg})
                            return {**state, "response": response_msg}
                        else:
                            return {"response": response_msg}

                    if action == "stop":
                        break

                # 루프 종료: answer에 도달 못하면 현재 근거+방문 경로로라도 답 생성
                final_dom = await self._summarize_dom(page)
                policy_items = await self._extract_policies(page)
                rag_snips = search_texts(f"{user_question}\n{current_url}", k=5)
                trace_block = self._format_trace_block(visit_trace)
                if policy_items:
                    final_dom = f"[정책 항목]\n- " + "\n- ".join(policy_items[:20]) + "\n\n" + final_dom
                messages = self._build_answer_with_trace(user_question, final_dom, rag_snips, trace_block)
                final = await self.llm.ainvoke(messages)
                final_text = getattr(final, "content", str(final)).strip()
                if state:
                    state.setdefault("interactive_result", {})["visit_trace"] = visit_trace
                    state.setdefault("interactive_result", {})["final_dom"] = final_dom
                    state.setdefault("interactive_result", {})["final_url"] = current_url
                    state.setdefault("messages", []).append({"role": self.role, "content": final_text})
                    return {**state, "response": final_text}
                else:
                    return {"response": final_text}

        except Exception as e:
            error_msg = f"❌ Interactive agent 오류: {str(e)}"
            print(f"[interactive_agent] 오류: {e}")
            traceback.print_exc()
            friendly = "apim 콘솔 페이지 접속이 어려워 접속 기반 정보제공이 어렵습니다. 잠시후 다시 시도해주세요"
            if state:
                state.setdefault("messages", []).append({"role": self.role, "content": friendly})
                return {**state, "response": friendly}
            else:
                return {"response": friendly}

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

    async def _decide_next_action(self, question: str, current_url: str, dom_text: str, rag_snippets: str, step_index: int) -> dict:
        """LLM으로 다음 Action 결정(JSON only)"""
        llm = self.llm
        system = (
            "너는 APIM 콘솔 내비게이터다. 다음 액션을 JSON으로만 반환해.\n"
            "스키마: {\"action\":\"goto|click|stop|answer\", \"target\":{\"by\":\"url|text|href|id\", \"value\":\"...\"}, \"reason\":\"...\", \"confidence\":0.0}\n"
            "절대 코드블록, 설명, 접두/접미 문구 없이 JSON 객체만 출력할 것\n"
            "규칙: 첫 스텝(step_index==0)에서는 answer를 선택하지 말 것. 관련 화면으로 이동을 우선.\n"
            "규칙: 이미 인증된 상태라면 'Login'을 클릭하지 말 것. goto가 text 대상이면 클릭으로 처리."
        )
        prompt = f"""
사용자 질문: {question}
현재 URL: {current_url}
현재 스텝: {step_index}

[DOM 요약]
{dom_text}

[RAG 스니펫]
{rag_snippets}

규칙:
- 불확실하면 stop 또는 answer 중 선택(근거로 충분하면 answer). 단, step 0에서는 answer 금지
- click은 target.by/value를 정확히 지정(text|href|id)
- goto는 절대/상대 URL 모두 허용(상대는 현재 URL 기준)
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

    def _format_trace_block(self, visit_trace: list[dict]) -> str:
        lines = ["[방문 경로/행동 로그]"]
        for item in visit_trace:
            step = item.get("step")
            url = item.get("url", "")
            path = item.get("path", "")
            decision = item.get("decision")
            action_result = item.get("action_result")
            if decision:
                lines.append(f"- step {step}: url={url} path={path} decision={json.dumps(decision, ensure_ascii=False)}")
            else:
                lines.append(f"- step {step}: url={url} path={path}")
            if action_result:
                lines.append(f"  action_result: {action_result}")
        return "\n".join(lines)

    def _build_answer_with_trace(self, question: str, dom_text: str, rag_snippets: list[dict], trace_block: str) -> list[dict]:
        # RAG 스니펫을 간단 문자열로 축약
        rag_texts = []
        for r in rag_snippets or []:
            doc = r.get("document", {})
            st = (doc.get("search_text") or "")[:200]
            rag_texts.append(st)
        rag_text = "\n---\n".join(rag_texts)
        system = (
            "너는 APIM 전문가이자 내비게이션 도우미다.\n"
            "최종 출력에는 반드시 다음을 포함하라:\n"
            "1) 한국어 설명(구체적으로: 어떤 화면의 어떤 링크/버튼을 클릭해야 하는지)\n"
            "2) 마크다운 표(헤더 포함, 최대 10행)\n"
            "3) 근거 섹션: 방문한 접속 링크/경로(path) 목록 + 사용한 문서 스니펫 요약\n"
            "각 단계에서의 관찰 결과를 반영하라.\n"
            "가능하면 상단에 요약(테이블 요약이 존재한다면 그 내용과 통합) 후, 구체적 단계와 근거를 제시하라."
        )
        # 테이블 요약이 state에 있을 수 있으므로, 호출 측에서 결합할 수 있게 사용자 프롬프트에 힌트 제공
        user = f"""
[사용자 질문]
{question}

[최종 DOM 요약]
{dom_text}

{trace_block}

[RAG 스니펫 요약]
{rag_text}

위 정보를 근거로, 단계별로 구체적인 조작(예: "link: ... 클릭" 형태)을 포함해 답하라. 근거 섹션에는 방문한 URL과 path를 반드시 포함하라.
가능하다면 앞서 요약된 표(있다면)와 결합하여 더 풍부한 최종 답변을 만들어라.
"""
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    async def _extract_policies(self, page) -> list[str]:
        try:
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            texts = []
            # 후보 1: 정책 리스트 예상 영역의 항목들
            for sel in [
                "[class*='policy'] li",
                "[class*='policy'] .ant-list-item",
                "[class*='policy'] .ant-collapse-item .ant-collapse-header",
                "[class*='Policies'] li",
                "[class*='Policies'] .ant-list-item",
                "[class*='Policies'] .ant-collapse-item .ant-collapse-header",
            ]:
                for node in soup.select(sel):
                    t = node.get_text(" ", strip=True)
                    if t and len(t) > 1:
                        texts.append(t)
            # 후보 2: 상세 페이지에서 '정책' 관련 버튼/레이블
            for node in soup.find_all(["a", "button", "span"], string=True):
                txt = node.get_text(" ", strip=True)
                if any(k in txt for k in ["Policy", "정책", "JWT", "Rate Limiting", "Key", "OIDC", "SAML", "CORS"]):
                    texts.append(txt)
            # 정제
            cleaned = []
            seen = set()
            for t in texts:
                t = t.strip()
                if t and t not in seen and len(t) < 200:
                    seen.add(t)
                    cleaned.append(t)
            return cleaned
        except Exception as e:
            print(f"[interactive_agent] _extract_policies 실패: {e}")
            return [] 