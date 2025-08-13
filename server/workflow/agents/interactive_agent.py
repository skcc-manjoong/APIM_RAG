import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
import traceback
from datetime import datetime

class InteractiveAgent:
    def __init__(self, llm=None):
        self.llm = llm
        self.role = "interactive_agent"
        self.base_url = "https://console.skapim.com"
        self.max_steps = 5  # 최대 탐색 단계
        
    async def run(self, state: dict = None, user_question: str = "", target_url: str = None) -> dict:
        """사용자 질문에 따라 페이지를 탐색하고 적절한 버튼/링크를 클릭 (로그인은 Navigation Agent에서 처리됨)"""
        try:
            print(f"[interactive_agent] 시작: 질문='{user_question}', URL='{target_url}'")
            
            # Navigation Agent에서 제공한 URL 사용
            if state and "navigation_result" in state:
                target_url = state["navigation_result"].get("target_url", target_url)
            
            if not target_url:
                target_url = f"{self.base_url}/gateway"
            
            print(f"[interactive_agent] Navigation Agent에서 로그인이 완료된 상태로 가정하고 진행합니다.")
            
            async with async_playwright() as p:
                # Navigation에서 저장한 세션 상태 파일을 사용
                storage_state = None
                context = None
                browser = None
                if state and state.get("navigation_result"):
                    storage_state = state["navigation_result"].get("auth_state_path")
                    if storage_state:
                        storage_state_path = Path(storage_state)
                        if not storage_state_path.is_absolute():
                            server_root = Path(__file__).resolve().parents[2]
                            storage_state_path = (server_root / storage_state_path).resolve()
                        if storage_state_path.exists():
                            print(f"[interactive_agent] 저장된 세션 사용: {storage_state_path}")
                            browser = await p.chromium.launch(headless=True)
                            context = await browser.new_context(storage_state=str(storage_state_path))
                            page = await context.new_page()
                        else:
                            browser = await p.chromium.launch(headless=True)
                            page = await browser.new_page()
                    else:
                        browser = await p.chromium.launch(headless=True)
                        page = await browser.new_page()
                else:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                
                # 목표 페이지로 바로 이동 (로그인은 Navigation Agent에서 처리됨)
                print(f"[interactive_agent] 목표 페이지로 이동: {target_url}")
                await page.goto(target_url)
                await page.wait_for_load_state('networkidle')
                
                # 페이지 상태 확인
                current_url = page.url
                print(f"[interactive_agent] 현재 페이지 URL: {current_url}")
                
                # 로그인 페이지로 리다이렉트된 경우 확인
                if "signin" in current_url.lower() or "login" in current_url.lower():
                    print(f"[interactive_agent] ⚠️ 로그인 페이지로 리다이렉트됨. Navigation Agent에서 로그인이 제대로 되지 않은 것 같습니다.")
                    error_msg = "❌ 로그인이 필요한 페이지입니다. Navigation Agent에서 로그인을 먼저 처리해주세요."
                    # 컨텍스트/브라우저 정리
                    try:
                        await page.context.close()
                    except:
                        try:
                            await browser.close()
                        except:
                            pass
                    
                    if state:
                        state["messages"].append({"role": self.role, "content": error_msg})
                        return {**state, "response": error_msg}
                    else:
                        return {"response": error_msg}
                
                # 로그인된 상태에서 다중 스텝 탐색 시작
                print(f"[interactive_agent] 🚀 로그인된 상태에서 페이지 탐색을 시작합니다.")
                final_url = await self._multi_step_navigation(page, user_question)
                
                # 컨텍스트/브라우저 정리
                try:
                    await page.context.close()
                except:
                    try:
                        await browser.close()
                    except:
                        pass
                
                response_msg = f"🤖 로그인된 상태에서 질문에 맞는 페이지를 자동 탐색했습니다: {final_url}"
                
                if state:
                    state["interactive_result"] = {
                        "original_url": target_url,
                        "final_url": final_url,
                        "user_question": user_question,
                        "navigation_completed": True
                    }
                    state["messages"].append({"role": self.role, "content": response_msg})
                    return {**state, "response": response_msg}
                else:
                    return {"response": response_msg}
                    
        except Exception as e:
            error_msg = f"❌ Interactive agent 오류: {str(e)}"
            print(f"[interactive_agent] 오류: {e}")
            import traceback
            traceback.print_exc()
            
            if state:
                state["messages"].append({"role": self.role, "content": error_msg})
                return {**state, "response": error_msg}
            else:
                return {"response": error_msg}
    
    async def think_next_action(self, question: str, current_url: str, elements: list[dict]) -> dict:
        """RAG+LLM을 사용해 다음 액션 결정"""
        from retrieval.vector_db import search_texts
        from utils.config import get_llm_azopai
        llm = get_llm_azopai()
        docs = search_texts(f"{question}\n{current_url}", k=5)
        # 요소를 간결 요약
        lines = []
        for el in elements[:30]:
            t = (el.get('text') or '')[:60].replace('\n',' ')
            href = el.get('href') or ''
            eid = el.get('id') or ''
            cls = (el.get('className') or '')[:40]
            lines.append(f"- text='{t}' href='{href[:80]}' id='{eid}' class='{cls}'")
        elements_txt = "\n".join(lines)
        system = (
            "너는 APIM 콘솔 내비게이터야. 다음 액션을 JSON으로만 반환해.\n"
            "스키마: {\"action\":\"goto|click|stop\", \"target\":{\"by\":\"url|text|href|id\", \"value\":\"...\"}, \"reason\":\"...\", \"confidence\":0.0}"
        )
        prompt = f"""
사용자 질문: {question}
현재 URL: {current_url}
문서 스니펫:
{docs}

DOM 요소 요약:
{elements_txt}

규칙:
- 불확실하면 action=stop.
- click 선택 시 by/text/href/id 중 하나만 고르고 value를 정확히 설정.
- goto는 절대/상대 URL 모두 허용.
JSON만 출력.
"""
        # 비동기 우선, 실패 시 동기 호출 폴백
        try:
            resp = await llm.ainvoke(system + "\n\n" + prompt)
            text = getattr(resp, "content", resp)
        except Exception:
            resp_sync = llm.invoke(system + "\n\n" + prompt)
            text = getattr(resp_sync, "content", resp_sync)
        try:
            data = json.loads(text)
            return data
        except Exception:
            return {"action":"stop","reason":"parse_fail","confidence":0.0}

    async def _multi_step_navigation(self, page, user_question):
        """다중 스텝 페이지 탐색 (LLM Think + Act). 각 단계 스크린샷 누적 저장"""
        current_url = page.url
        screenshots: list[str] = []
        for step in range(self.max_steps):
            print(f"[interactive_agent] 탐색 단계 {step + 1}/{self.max_steps}")
            clickable_elements = await self._collect_clickable_elements(page)
            if not clickable_elements:
                print(f"[interactive_agent] 클릭 가능한 요소가 없음")
                break
            decision = await self.think_next_action(user_question, current_url, clickable_elements)
            action = (decision.get("action") or "stop").lower()
            target = decision.get("target") or {}
            print(f"[interactive_agent] Think 결정: {decision}")
            acted = False
            if action == "goto":
                url = target.get("value") or target.get("url") or ""
                try:
                    await page.goto(url)
                    await page.wait_for_load_state('networkidle')
                    acted = True
                except Exception as e:
                    print(f"[interactive_agent] goto 실패: {e}")
            elif action == "click":
                acted = await self._click_element(page, {
                    "text": target.get("value") if target.get("by") == "text" else "",
                    "href": target.get("value") if target.get("by") == "href" else "",
                    "id": target.get("value") if target.get("by") == "id" else ""
                })
                await page.wait_for_load_state('networkidle')
            elif action == "stop":
                print("[interactive_agent] stop 결정")
                break
            else:
                print("[interactive_agent] 알 수 없는 액션, 중단")
                break
            new_url = page.url
            if acted and new_url != current_url:
                print(f"[interactive_agent] 페이지 이동: {new_url}")
                current_url = new_url
            # 단계별 스크린샷 저장
            try:
                from datetime import datetime
                from pathlib import Path
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                shots_dir = Path("screenshots")
                shots_dir.mkdir(parents=True, exist_ok=True)
                fname = shots_dir / f"step_{step+1}_{ts}.png"
                await page.screenshot(path=str(fname), full_page=True)
                screenshots.append(str(fname))
            except Exception as e:
                print(f"[interactive_agent] 단계 스크린샷 실패: {e}")
            # 목표 판단
            if await self._is_target_reached(page, user_question):
                print("[interactive_agent] 목표 페이지 도달!")
                break
        # state에 누적 저장을 위해 반환 경로 주입
        if hasattr(self, "_state_ref") and isinstance(self._state_ref, dict):
            self._state_ref.setdefault("interactive_path_shots", []).extend(screenshots)
        return current_url
    
    async def _collect_clickable_elements(self, page):
        """페이지의 클릭 가능한 요소들 수집"""
        try:
            # JavaScript로 클릭 가능한 요소들 수집
            elements_data = await page.evaluate("""
                () => {
                    const elements = [];
                    const selectors = [
                        'a[href]',
                        'button',
                        'input[type="submit"]',
                        'input[type="button"]',
                        '[onclick]',
                        '[role="button"]',
                        '.btn',
                        '.button'
                    ];
                    
                    selectors.forEach(selector => {
                        document.querySelectorAll(selector).forEach((el, index) => {
                            if (el.offsetParent !== null) { // 보이는 요소만
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    elements.push({
                                        index: elements.length,
                                        tag: el.tagName.toLowerCase(),
                                        text: el.textContent.trim(),
                                        href: el.href || '',
                                        id: el.id || '',
                                        className: el.className || '',
                                        ariaLabel: el.getAttribute('aria-label') || '',
                                        title: el.title || '',
                                        selector: selector
                                    });
                                }
                            }
                        });
                    });
                    
                    return elements.slice(0, 20); // 상위 20개만
                }
            """)
            
            return elements_data
            
        except Exception as e:
            print(f"[interactive_agent] 요소 수집 오류: {e}")
            return []
    
    async def _ask_llm_for_selection(self, elements, user_question, current_url):
        """LLM에게 어떤 요소를 클릭할지 물어보기"""
        try:
            if not self.llm:
                # LLM이 없으면 간단한 키워드 매칭
                return self._simple_keyword_matching(elements, user_question)
            
            # 요소 리스트를 텍스트로 변환
            elements_text = "\n".join([
                f"{i+1}. {el['tag'].upper()} - 텍스트: '{el['text'][:50]}' "
                f"(ID: {el['id']}, Class: {el['className'][:30]}, href: {el['href'][:50]})"
                for i, el in enumerate(elements)
            ])
            
            prompt = f"""
현재 페이지: {current_url}
사용자 질문: "{user_question}"

아래는 현재 페이지의 클릭 가능한 요소들입니다:
{elements_text}

사용자 질문에 가장 적합한 요소를 선택해주세요. 
답변은 반드시 숫자만 답해주세요 (예: 3).
적절한 요소가 없으면 0을 답해주세요.
"""
            
            # 여기서는 간단한 키워드 매칭으로 대체 (실제로는 LLM 호출)
            return self._simple_keyword_matching(elements, user_question)
            
        except Exception as e:
            print(f"[interactive_agent] LLM 선택 오류: {e}")
            return None
    
    def _simple_keyword_matching(self, elements, user_question):
        """간단한 키워드 매칭 (LLM 대체용) - 개선된 버전"""
        question_lower = user_question.lower()
        # 가중치가 높은 정책 관련 키워드 추가
        keywords = {
            'policy_strong': ['정책', 'policy', 'policies', '정책 수정', '정책설정', 'policy settings'],
            'api': ['api', 'api관리', 'api 관리', 'api정책', 'api 정책'],
            'gateway': ['게이트웨이', 'gateway'],
            'replica': ['replica', '레플리카', '복제', '확장', 'scale'],
            'settings': ['설정', 'settings', 'config', '구성'],
            'management': ['관리', 'management', '매니지먼트', 'manage'],
        }
        
        best_score = -1
        best_element = None
        
        print(f"[interactive_agent] 키워드 매칭 시작, 질문: '{user_question}'")
        print(f"[interactive_agent] 찾은 요소 수: {len(elements)}")
        
        for i, element in enumerate(elements):
            text_lower = (element.get('text') or '').lower()
            attrs_lower = f"{element.get('id','')} {element.get('className','')} {element.get('href','')}".lower()
            score = 0
            matched_keywords = []
            
            # 정책 키워드 가중치 우선 적용
            for word in keywords['policy_strong']:
                if word in question_lower and (word in text_lower or word in attrs_lower):
                    score += 20
                    matched_keywords.append(word)
            
            # 일반 키워드
            for group in ['api','gateway','replica','settings','management']:
                for word in keywords[group]:
                    if word in question_lower and (word in text_lower or word in attrs_lower):
                        score += 6
                        matched_keywords.append(word)
            
            # 빈 텍스트 패널티
            if not element.get('text'):
                score -= 3
            
            if score > 0:
                print(f"[interactive_agent] 요소 {i+1}: '{element.get('text','')[:30]}' 점수={score}, 매칭={matched_keywords}")
            
            # 더 높은 점수 또는 동일 점수 시 텍스트가 있는 요소 우선
            if score > best_score or (score == best_score and best_element and element.get('text') and not best_element.get('text')):
                best_score = score
                best_element = element
        
        if best_element and best_score > 0:
            print(f"[interactive_agent] 최고 점수 요소 선택: '{best_element.get('text','')[:50]}' (점수: {best_score})")
            return best_element
        print(f"[interactive_agent] 적절한 요소를 찾지 못함")
        return None

    async def _click_element(self, page, element):
        """선택된 요소 클릭 - 안정성 개선"""
        try:
            text = (element.get('text') or '').strip()
            href = element.get('href') or ''
            elem_id = element.get('id') or ''
            
            # 1) 텍스트 사용 (정확/포함 매칭 순서)
            if text:
                try:
                    await page.wait_for_selector(f"text={text}", timeout=10000)
                    await page.click(f"text={text}")
                    print(f"[interactive_agent] 텍스트로 클릭: {text}")
                    return True
                except Exception:
                    # role 기반 시도
                    try:
                        await page.get_by_role("link", name=text, exact=False).click(timeout=10000)
                        print(f"[interactive_agent] role=link로 클릭: {text}")
                        return True
                    except Exception:
                        pass
            
            # 2) href 정확/부분 매칭
            if href:
                try:
                    await page.wait_for_selector(f"a[href='{href}']", timeout=10000)
                    await page.click(f"a[href='{href}']")
                    print(f"[interactive_agent] href로 클릭: {href}")
                    return True
                except Exception:
                    try:
                        await page.wait_for_selector(f"a[href*='{href}']", timeout=10000)
                        await page.click(f"a[href*='{href}']")
                        print(f"[interactive_agent] href 부분매칭으로 클릭: {href}")
                        return True
                    except Exception:
                        pass
            
            # 3) id 기반
            if elem_id:
                try:
                    await page.wait_for_selector(f"#{elem_id}", timeout=10000)
                    await page.click(f"#{elem_id}")
                    print(f"[interactive_agent] id로 클릭: {elem_id}")
                    return True
                except Exception:
                    pass
            
            return False
        except Exception as e:
            print(f"[interactive_agent] 클릭 실패: {e}")
            return False
    
    async def _is_target_reached(self, page, user_question):
        """목표 페이지에 도달했는지 확인"""
        try:
            page_content = await page.content()
            question_keywords = user_question.lower().split()
            
            # 페이지 내용에 질문 키워드가 많이 포함되어 있으면 목표 도달로 판단
            matches = sum(1 for keyword in question_keywords if keyword in page_content.lower())
            return matches >= len(question_keywords) * 0.5
            
        except Exception as e:
            print(f"[interactive_agent] 목표 도달 확인 오류: {e}")
            return False 