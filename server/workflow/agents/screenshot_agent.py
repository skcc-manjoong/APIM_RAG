import asyncio
import base64
from pathlib import Path
from playwright.async_api import async_playwright
import traceback
import os
from datetime import datetime
import shutil

class ScreenshotAgent:
    def __init__(self, llm=None):
        self.llm = llm
        self.role = "screenshot_agent"
        self.screenshots_dir = Path("screenshots")
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    async def run(self, state: dict = None, url: str = None) -> dict:
        """웹페이지 스크린샷 캡처"""
        try:
            # URL 결정: interactive_result -> navigation_result -> 기본값 순서
            target_url = url
            if state and "interactive_result" in state:
                target_url = state["interactive_result"].get("final_url", url)
            elif state and "navigation_result" in state:
                target_url = state["navigation_result"].get("target_url", url)
            
            if not target_url:
                target_url = "https://developers.skapim.com/"  # 기본값
            
            print(f"[screenshot_agent] 스크린샷 캡처 시작: {target_url}")
            
            async with async_playwright() as p:
                # 브라우저 실행 (디버깅 정보 포함)
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
                            print(f"[screenshot_agent] 저장된 세션 사용: {storage_state_path}")
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
                
                # Interactive Agent에서 로그인이 성공했는지 확인
                login_needed = True
                if state and "interactive_result" in state:
                    navigation_completed = state["interactive_result"].get("navigation_completed", False)
                    if navigation_completed:
                        print(f"[screenshot_agent] Interactive Agent에서 탐색이 완료된 상태입니다.")
                        login_needed = False
                elif state and "navigation_result" in state:
                    # Navigation Agent에서 로그인이 처리되었을 가능성
                    print(f"[screenshot_agent] Navigation Agent에서 로그인이 처리된 것으로 가정합니다.")
                    login_needed = False
                
                # 페이지 이동
                await page.goto(target_url)
                await page.wait_for_load_state('networkidle')
                
                # 로그인 페이지로 리다이렉트된 경우에만 간단한 로그인 시도
                if login_needed and ("signin" in page.url.lower() or "login" in page.url.lower()):
                    print(f"[screenshot_agent] 로그인 페이지 감지, 간단한 로그인 시도...")
                    try:
                        # 간단한 로그인 시도 (Navigation/Interactive에서 실패한 경우 대비)
                        email_input = page.locator("input.form-control:not([type='password']), input[type='email'], input[name='email']")
                        
                        if await email_input.count() > 0:
                            await email_input.first.fill("admin@admin.com")
                            
                            password_input = page.locator("input[type='password']")
                            if await password_input.count() > 0:
                                await password_input.first.fill("admin!23$")
                                
                                # 로그인 버튼 클릭
                                login_button = page.locator("button[type='submit'], input[type='submit'], button:has-text('로그인'), button:has-text('Login')")
                                if await login_button.count() > 0:
                                    await login_button.first.click()
                                    await page.wait_for_load_state('networkidle')
                                    print(f"[screenshot_agent] 간단 로그인 완료")
                    except Exception as e:
                        print(f"[screenshot_agent] 로그인 건너뜀: {e}")
                
                # 페이지 이동 확인 및 스크린샷 캡처
                print(f"[screenshot_agent] 최종 페이지 이동: {target_url}")
                await page.goto(target_url)
                await page.wait_for_load_state('networkidle')
                
                # 스크린샷 저장
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = self.screenshots_dir / f"screenshot_{timestamp}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"[screenshot_agent] 스크린샷 저장 완료: {screenshot_path}")
                
                # 컨텍스트/브라우저 정리
                try:
                    if context:
                        await context.close()
                    elif browser:
                        await browser.close()
                except:
                    pass
                
                # Base64 인코딩
                with open(screenshot_path, 'rb') as img_file:
                    img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                
                # 응답 메시지 생성 (Base64 데이터 제외)
                response_msg = (
                    f"📸 웹페이지 스크린샷을 캡처했습니다: {target_url}\n"
                    f"파일: screenshots/{screenshot_path.name}"
                )
                
                if state:
                    state["screenshot_result"] = {
                        "url": target_url,
                        "image_path": str(screenshot_path),
                        "image_base64": img_base64,
                        "filename": screenshot_path.name
                    }
                    state["messages"].append({"role": self.role, "content": response_msg})
                    
                    # 앱 디렉토리에도 복사
                    try:
                        app_screenshot_dir = Path("../app/screenshots")
                        app_screenshot_dir.mkdir(parents=True, exist_ok=True)
                        app_screenshot_path = app_screenshot_dir / screenshot_path.name
                        shutil.copy2(screenshot_path, app_screenshot_path)
                    except Exception as e:
                        print(f"[WARNING] 앱 디렉토리로 복사 실패: {e}")
                    
                    return {**state, "response": response_msg}
                else:
                    return {"response": response_msg}
                    
        except Exception as e:
            error_msg = f"❌ 스크린샷 캡처 오류: {str(e)}"
            print(f"[screenshot_agent] 오류: {e}")
            traceback.print_exc()
            
            if state:
                state["messages"].append({"role": self.role, "content": error_msg})
                return {**state, "response": error_msg}
            else:
                return {"response": error_msg}
    
    async def _login_if_needed(self, page, target_url: str):
        """console.skapim.com에 로그인이 필요한 경우 로그인 수행"""
        try:
            print(f"[screenshot_agent] 로그인 시도 후 페이지 이동: {target_url}")
            
            # 먼저 로그인 페이지로 이동
            base_url = "https://console.skapim.com"
            await page.goto(base_url)
            await page.wait_for_load_state('networkidle')
            
            # 로그인 폼 찾기 및 입력
            try:
                # 이메일 입력
                email_selector = 'input[type="email"], input[name="email"], input[name="username"], #email, #username'
                await page.fill(email_selector, "admin@admin.com")
                
                # 비밀번호 입력
                password_selector = 'input[type="password"], input[name="password"], #password'
                await page.fill(password_selector, "admin!23$")
                
                # 로그인 버튼 클릭
                login_button_selector = 'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("로그인")'
                await page.click(login_button_selector)
                
                # 로그인 완료 대기
                await page.wait_for_load_state('networkidle')
                print(f"[screenshot_agent] 로그인 완료")
                
            except Exception as login_error:
                print(f"[screenshot_agent] 로그인 건너뜀 (이미 로그인된 상태일 수 있음): {login_error}")
            
            # 목적지 페이지로 이동
            if target_url != base_url:
                await page.goto(target_url)
                await page.wait_for_load_state('networkidle')
                
        except Exception as e:
            print(f"[screenshot_agent] 로그인 및 페이지 이동 오류: {e}")
            # 실패해도 일반적인 페이지 접근 시도
            await page.goto(target_url)
            await page.wait_for_load_state('networkidle')
    
    async def capture_screenshot(self, url: str) -> Path:
        """
        Playwright를 사용해 웹페이지 스크린샷을 캡처합니다.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        screenshot_path = self.screenshots_dir / filename
        
        async with async_playwright() as p:
            # 브라우저 시작 (headless 모드)
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # 뷰포트 크기 설정
            await page.set_viewport_size({"width": 1920, "height": 1080})
            
            # 페이지 이동
            await page.goto(url, wait_until="networkidle")
            
            # 약간의 대기 시간 (페이지 로딩 완료 확인)
            await page.wait_for_timeout(2000)
            
            # 스크린샷 캡처
            await page.screenshot(path=str(screenshot_path), full_page=True)
            
            # 브라우저 종료
            await browser.close()
        
        return screenshot_path
    
    def get_screenshot_as_base64(self, screenshot_path: Path) -> str:
        """
        스크린샷 파일을 base64로 인코딩해서 반환합니다.
        """
        with open(screenshot_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8') 