import asyncio
import base64
from pathlib import Path
from playwright.async_api import async_playwright
import traceback
import os
from datetime import datetime
import json
import re
from bs4 import BeautifulSoup

class NavigationAgent:
	def __init__(self, llm=None):
		self.llm = llm
		self.role = "navigation_agent"
		# 3개 포털 정의
		self.portals = {
			"developers": "https://developers.skapim.com/",      # 개발자 포털
			"console": "https://console.skapim.com/",            # 관리자 포털  
			"tenant": "https://tenant.skapim.com/"               # 사용자 관리 포털
		}
		self.login_email = "admin@admin.com"
		self.login_password = "admin!23$"
		
	async def run(self, state: dict = None, user_question: str = "", rag_result: str = "") -> dict:
		"""사용자 질문을 분석하여 적절한 포털을 선택하고 로그인 후 redirectUrl 전달"""
		try:
			print(f"[navigation_agent] 시작: 질문='{user_question}'")
			# 1단계: 질문 분석하여 적절한 포털 선택
			think = await self.think_portal_and_path(user_question)
			selected_portal = think.get("portal", "console")
			start_path = think.get("path", "/gateway")
			print(f"[navigation_agent] 선택된 포털: {selected_portal}, path: {start_path}")
			async with async_playwright() as p:
				browser = await p.chromium.launch(headless=True)
				page = await browser.new_page()
				# 2단계: 선택된 포털로 이동
				target_portal_url = self.portals[selected_portal].rstrip('/') + start_path
				print(f"[navigation_agent] 포털 이동: {target_portal_url}")
				await page.goto(target_portal_url)
				await page.wait_for_load_state('networkidle')
				# 3단계: 로그인 페이지로 리다이렉트 확인
				current_url = page.url
				print(f"[navigation_agent] 현재 URL: {current_url}")
				# 4단계: 로그인 수행
				login_success = await self._login_to_console(page)
				if not login_success:
					error_msg = "❌ 로그인 실패"
					await browser.close()
					if state:
						state["messages"].append({"role": self.role, "content": error_msg})
						return {**state, "response": error_msg}
					else:
						return {"response": error_msg}
				# 5단계: 로그인 후 최종 URL 확인 (redirectUrl)
				final_url = page.url
				print(f"[navigation_agent] 로그인 후 최종 URL: {final_url}")
				# 로그인 세션 저장 (Playwright storage state)
				try:
					server_root = Path(__file__).resolve().parents[2]
					auth_dir = server_root / "playwright_auth"
					auth_dir.mkdir(parents=True, exist_ok=True)
					auth_path = auth_dir / "auth_state.json"
					await page.context.storage_state(path=str(auth_path))
					print(f"[navigation_agent] 로그인 세션 저장: {auth_path}")
				except Exception as e:
					print(f"[navigation_agent] 세션 저장 실패: {e}")
				await browser.close()
				response_msg = f"🔍 {selected_portal} 포털을 선택하고 로그인을 완료했습니다: {final_url}"
				if state:
					state["navigation_result"] = {
						"selected_portal": selected_portal,
						"portal_url": target_portal_url,
						"target_url": final_url,
						"login_completed": True,
						"auth_state_path": str(auth_path) if 'auth_path' in locals() else None,
						"user_question": user_question,
					}
					state["messages"].append({"role": self.role, "content": response_msg})
					return {**state, "response": response_msg}
				else:
					return {"response": response_msg}
		except Exception as e:
			error_msg = f"❌ Navigation agent 오류: {str(e)}"
			print(f"[navigation_agent] 오류: {e}")
			traceback.print_exc()
			if state:
				state["messages"].append({"role": self.role, "content": error_msg})
				return {**state, "response": error_msg}
			else:
				return {"response": error_msg}
		
	def _select_portal(self, user_question: str, rag_result: str) -> str:
		"""사용자 질문을 분석하여 적절한 포털 선택"""
		question_lower = user_question.lower()
		
		# 키워드 기반 포털 선택
		portal_keywords = {
			"console": [
				# 관리자/콘솔 관련
				"관리", "admin", "console", "콘솔", "설정", "정책", "policy", 
				"gateway", "게이트웨이", "api관리", "api 관리", "replica", "레플리카",
				"관리자", "administrator", "config", "configuration", "매니지먼트",
				# API 관리 관련
				"api정책", "api 정책수정", "정책수정", "api설정", "api 설정"
			],
			"developers": [
				# 개발자 관련
				"개발자", "developer", "dev", "문서", "docs", "documentation", 
				"가이드", "guide", "api문서", "api 문서", "사용법", "튜토리얼",
				"포털", "portal", "개발", "development"
			],
			"tenant": [
				# 사용자/테넌트 관리 관련
				"사용자", "user", "tenant", "테넌트", "계정", "account", 
				"멤버", "member", "권한", "permission", "role", "역할",
				"사용자관리", "사용자 관리", "계정관리", "계정 관리"
			]
		}
		
		# 각 포털별 점수 계산
		portal_scores = {}
		for portal, keywords in portal_keywords.items():
			score = 0
			for keyword in keywords:
				if keyword in question_lower:
					score += len(keyword)  # 긴 키워드일수록 높은 점수
			portal_scores[portal] = score
		
		# RAG 결과도 고려
		if rag_result:
			rag_lower = rag_result.lower()
			for portal, keywords in portal_keywords.items():
				for keyword in keywords:
					if keyword in rag_lower:
						portal_scores[portal] += len(keyword) * 0.5  # RAG는 절반 가중치
		
		# 가장 높은 점수의 포털 선택
		best_portal = max(portal_scores, key=portal_scores.get)
		best_score = portal_scores[best_portal]
		
		print(f"[navigation_agent] 포털 점수: {portal_scores}")
		
		# 점수가 0이면 기본값은 console (관리자 포털)
		if best_score == 0:
			print(f"[navigation_agent] 키워드 매칭 없음, 기본값 console 선택")
			return "console"
		
		print(f"[navigation_agent] 최고 점수 포털: {best_portal} (점수: {best_score})")
		return best_portal
	
	async def _login_to_console(self, page):
		"""포털 로그인 수행"""
		try:
			print(f"[navigation_agent] === 로그인 시도 시작 ===")
			print(f"[navigation_agent] 현재 URL: {page.url}")
			
			# 페이지 로드 완료 대기
			await page.wait_for_load_state('networkidle', timeout=60000)
			await page.wait_for_timeout(3000)
			
			# 이미 로그인된 상태인지 확인 (로그인 페이지가 아닌 경우)
			current_url = page.url
			if "signin" not in current_url.lower() and "login" not in current_url.lower():
				# redirectUrl이 있는지 확인
				if "redirectUrl=" in current_url:
					print(f"[navigation_agent] redirectUrl이 포함된 페이지에 있음, 이미 로그인된 상태로 보임")
					return True
				elif any(portal in current_url for portal in ["console.skapim.com", "developers.skapim.com", "tenant.skapim.com"]):
					print(f"[navigation_agent] 포털 페이지에 있음, 이미 로그인된 상태로 보임")
					return True
			
			# 로그인 페이지에 있는 경우 로그인 수행
			print(f"[navigation_agent] 로그인 페이지에서 로그인 수행")
			
			# 아이디 입력 필드 찾기 (class="form-control")
			email_selectors = [
				"input.form-control:not([type='password'])",  # form-control 클래스이면서 password가 아닌 것
				"input.form-control[type='email']",  # form-control + email type
				"input.form-control[type='text']",   # form-control + text type  
				"input.form-control:first-of-type",  # form-control 중 첫 번째
				"input[class='form-control']:not([type='password'])",  # 정확한 클래스 매칭
				"input[type='email']",
				"input[name='email']", 
				"input[name='username']"
			]
			
			email_input = None
			for selector in email_selectors:
				try:
					locator = page.locator(selector)
					count = await locator.count()
					if count > 0:
						for i in range(count):
							element = locator.nth(i)
							is_visible = await element.is_visible()
							if is_visible:
								email_input = element
								print(f"[navigation_agent] ✅ 아이디 입력 필드 발견: {selector}")
								break
							if email_input:
								break
				except Exception as e:
					continue
			
			if not email_input:
				print(f"[navigation_agent] ❌ 아이디 입력 필드를 찾을 수 없음")
				return False
			
			# 아이디 입력
			await email_input.click()
			await page.wait_for_timeout(500)
			await email_input.select_text()
			await page.keyboard.press('Delete')
			await page.wait_for_timeout(500)
			await email_input.type(self.login_email, delay=50)
			await page.wait_for_timeout(1000)
			print(f"[navigation_agent] ✅ 아이디 입력 완료")
			
			# 비밀번호 입력 필드 찾기 (type="password")
			password_selectors = [
				"input[type='password']",  # type이 password인 것
				"input.form-control[type='password']",  # form-control + password
				"input[class='form-control'][type='password']",  # 정확한 클래스 + type 매칭
				"input[name='password']"
			]
			
			password_input = None
			for selector in password_selectors:
				try:
					locator = page.locator(selector)
					count = await locator.count()
					if count > 0:
						for i in range(count):
							element = locator.nth(i)
							is_visible = await element.is_visible()
							if is_visible:
								password_input = element
								print(f"[navigation_agent] ✅ 비밀번호 입력 필드 발견: {selector}")
								break
							if password_input:
								break
				except Exception as e:
					continue
			
			if not password_input:
				print(f"[navigation_agent] ❌ 비밀번호 입력 필드를 찾을 수 없음")
				return False
			
			# 비밀번호 입력
			await password_input.click()
			await page.wait_for_timeout(500)
			await password_input.select_text()
			await page.keyboard.press('Delete')
			await page.wait_for_timeout(500)
			await password_input.type(self.login_password, delay=50)
			await page.wait_for_timeout(1000)
			print(f"[navigation_agent] ✅ 비밀번호 입력 완료")
			
			# 로그인 버튼 찾기 (type="submit")
			login_button_selectors = [
				"button[type='submit']",  # type이 submit인 버튼
				"input[type='submit']",   # type이 submit인 input
				"[type='submit']",        # 모든 submit 타입
				"button[type='submit'].btn.btn-primary",
				"button:has-text('로그인')",
				"button:has-text('Login')",
				"form button"
			]
			
			login_success = False
			for selector in login_button_selectors:
				try:
					locator = page.locator(selector)
					count = await locator.count()
					if count > 0:
						for i in range(count):
							try:
								element = locator.nth(i)
								is_visible = await element.is_visible()
								if is_visible:
									print(f"[navigation_agent] 🔘 로그인 버튼 클릭 시도: {selector}")
									
									current_url = page.url
									await element.click()
									
									# 페이지 변경 대기
									try:
										await page.wait_for_load_state('networkidle', timeout=20000)
										await page.wait_for_timeout(3000)
									except Exception as wait_error:
										print(f"[navigation_agent] 페이지 로딩 대기 중 오류: {wait_error}")
									
									new_url = page.url
									print(f"[navigation_agent] 클릭 후 URL: {new_url}")
									
									# 로그인 성공 확인 (URL 변경 및 로그인 페이지 벗어남)
									if (new_url != current_url and 
										"signin" not in new_url.lower() and 
										"login" not in new_url.lower()):
										print(f"[navigation_agent] 🎉 로그인 성공! redirectUrl: {new_url}")
										login_success = True
										break
										
							except Exception as click_error:
								print(f"[navigation_agent] 버튼 클릭 실패: {click_error}")
								continue
						
						if login_success:
							break
							
				except Exception as e:
					continue
			
			if login_success:
				print(f"[navigation_agent] === 로그인 완전 성공! ===")
				return True
			else:
				print(f"[navigation_agent] === 로그인 실패 ===")
				return False
				
		except Exception as e:
			print(f"[navigation_agent] 로그인 시도 중 오류: {e}")
			import traceback
			traceback.print_exc()
			return False 
	
	async def think_portal_and_path(self, question: str) -> dict:
		"""RAG+LLM을 활용해 포털(console|developers|tenant)과 초기 path를 결정"""
		from retrieval.vector_db import search_texts
		from utils.config import get_llm_azopai
		llm = get_llm_azopai()
		docs = search_texts(question, k=5)
		system = (
			"너는 APIM 포털 네비게이터야. 사용자 질문과 문서 스니펫을 보고, 아래 JSON만 반환해.\n"
			"필드: portal(console|developers|tenant), path(예:/gateway,/api,/policy), reason"
		)
		prompt = f"""
	사용자 질문:
	{question}
	
	문서 스니펫:
	{docs}
	
	JSON만 출력:
	JSON만 출력:
	{{"portal":"console","path":"/gateway","reason":"..."}}
	"""
		# 비동기 우선, 실패 시 동기 호출로 폴백
		try:
			resp = await llm.ainvoke(system + "\n\n" + prompt)
			text = getattr(resp, "content", resp)
		except Exception:
			resp_sync = llm.invoke(system + "\n\n" + prompt)
			text = getattr(resp_sync, "content", resp_sync)
		try:
			data = json.loads(text)
			portal = data.get("portal") or "console"
			path = data.get("path") or "/gateway"
			reason = data.get("reason") or ""
		except Exception:
			portal, path, reason = "console", "/gateway", "fallback"
		return {"portal": portal, "path": path, "reason": reason} 