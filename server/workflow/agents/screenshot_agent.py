import asyncio
import base64
from pathlib import Path
from playwright.async_api import async_playwright
import traceback
import os
from datetime import datetime

class ScreenshotAgent:
    def __init__(self, llm=None):
        self.llm = llm
        self.role = "screenshot_agent"
        self.screenshots_dir = Path("screenshots")
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    async def run(self, state: dict = None, url: str = None) -> dict:
        """
        웹페이지를 캡처하고 base64로 인코딩된 이미지를 반환합니다.
        """
        if not url:
            url = "https://developers.skapim.com/"
        
        try:
            # 웹페이지 스크린샷 캡처
            screenshot_path = await self.capture_screenshot(url)
            
            # 이미지를 base64로 인코딩
            with open(screenshot_path, "rb") as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
            
            # 앱 디렉토리로도 복사 (프론트엔드에서 쉽게 접근하기 위해)
            try:
                import shutil
                app_screenshot_dir = Path("../app/screenshots")
                app_screenshot_dir.mkdir(parents=True, exist_ok=True)
                app_screenshot_path = app_screenshot_dir / screenshot_path.name
                shutil.copy2(screenshot_path, app_screenshot_path)
            except Exception as e:
                print(f"[WARNING] 앱 디렉토리로 복사 실패: {e}")
            
            # 응답 메시지 생성 (base64 데이터 포함)
            response_msg = f"웹페이지 스크린샷을 캡처했습니다: {url}\n\ndata:image/png;base64,{img_base64[:50]}..." # 처음 50자만 표시
            
            if state:
                state["screenshot_result"] = {
                    "url": url,
                    "image_path": str(screenshot_path),
                    "image_base64": img_base64,
                    "filename": screenshot_path.name
                }
                state["messages"].append({
                    "role": self.role, 
                    "content": response_msg
                })
                state["response"] = response_msg
                return state
            else:
                return {
                    "screenshot_result": {
                        "url": url,
                        "image_path": str(screenshot_path),
                        "image_base64": img_base64
                    }
                }
                
        except Exception as e:
            error_msg = f"스크린샷 캡처 실패: {str(e)}"
            print(f"[ERROR][ScreenshotAgent] {error_msg}")
            traceback.print_exc()
            
            if state:
                state["messages"].append({"role": "error", "content": error_msg})
                state["response"] = error_msg
                return state
            else:
                return {"error": str(e)}
    
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