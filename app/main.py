import os
import json
import requests
import streamlit as st
from dotenv import load_dotenv
from components.sidebar import render_sidebar
import time

# chat_history가 없으면 빈 리스트로 초기화
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# 페이지 설정은 Streamlit에서 가장 먼저 호출되어야 합니다.
st.set_page_config(
    page_title="APIM 서비스 질의응답", 
    page_icon="🔧",
    layout="wide"  # 화면을 넓게 사용
)

# 사용자 정의 CSS로 채팅 말풍선 스타일 추가
st.markdown(
    """
    <style>
    .bubble {
        padding: 12px 18px;
        border-radius: 18px;
        margin: 8px 0;
        max-width: 90%;
        font-size: 1.05em;
        line-height: 1.4;
    }
    .bubble.user {
        background-color: #E3F2FD;
        margin-left: 10%;
        margin-right: 0;
        text-align: right;
        border: 1px solid #BBDEFB;
    }
    .bubble.assistant {
        background-color: #F3E5F5;
        margin-right: 10%;
        margin-left: 0;
        text-align: left;
        border: 1px solid #E1BEE7;
    }
    .stButton button {
        width: 100%;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True
)

# 말풍선에 사용할 아바타 정의
AVATARS = {
    "user": "👤",
    "assistant": "🔧",
    "system": "📋",
    "error": "🚨",
}
# API 설정
load_dotenv()
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001/api/v1/workflow")


def stream_text(text):
    for word in text.split():
        yield word + " "
        time.sleep(0.1)

# 스트리밍 응답 처리 함수
def process_streaming_response(response, question):
    """스트리밍 응답을 실시간으로 처리하고 UI에 표시합니다."""
    response_received = False
    
    # 현재까지의 모든 응답을 저장할 리스트
    current_responses = []
    
    # 현재 타입의 응답을 저장할 변수
    current_response = {
        "role": "assistant",
        "content": "",
        "chunk_type": None
    }
    
    # 실시간 업데이트를 위한 placeholder 생성
    message_placeholder = st.empty()
    
    def update_display():
        # 모든 응답을 순서대로 표시
        full_response = ""
        for resp in current_responses + ([current_response] if current_response["content"].strip() else []):
            agent_label = ""
            if resp["chunk_type"] == "rag":
                agent_label = "<small style='color:#666;'>📚 문서 검색 완료</small><br>"
            elif resp["chunk_type"] == "table":
                agent_label = "<small style='color:#666;'>📊 결과 분석 완료</small><br>"
            elif resp["chunk_type"] == "response":
                agent_label = "<small style='color:#666;'>✅ 응답 생성 완료</small><br>"
            full_response += f"{agent_label}{resp['content']}<br><br>"
        
        message_placeholder.markdown(full_response, unsafe_allow_html=True)
    
    for chunk in response.iter_lines():
        if not chunk:
            continue
        
        line = chunk.decode("utf-8")
        if not line.startswith("data: "):
            continue
        
        data_str = line[6:]  # "data: " 부분 제거
        
        try:
            event_data = json.loads(data_str)
            
            # 종료 신호 확인
            if event_data.get("type") == "end":
                # 마지막 응답이 있다면 추가
                if current_response["content"].strip() and current_response["chunk_type"]:
                    current_responses.append(current_response.copy())
                    update_display()
                break
            
            # 응답 처리 로깅
            print(f"[DEBUG] 수신한 이벤트 데이터: {event_data}")
            
            # 새로운 타입의 응답이 시작될 때 이전 응답 저장
            new_chunk_type = None
            new_chunk_text = None
            
            if "rag" in event_data and "response" in event_data["rag"]:
                new_chunk_type = "rag"
                new_chunk_text = event_data["rag"]["response"]
            elif "table" in event_data and "response" in event_data["table"]:
                new_chunk_type = "table"
                new_chunk_text = event_data["table"]["response"]
            elif "response" in event_data:
                new_chunk_type = "response"
                new_chunk_text = event_data["response"]
            
            if new_chunk_text:
                response_received = True
                
                # 타입이 변경되었거나 처음 응답을 받는 경우
                if current_response["chunk_type"] != new_chunk_type:
                    # 이전 응답이 있으면 저장
                    if current_response["content"].strip() and current_response["chunk_type"]:
                        current_responses.append(current_response.copy())
                    
                    # 새로운 응답 초기화
                    current_response = {
                        "role": "assistant",
                        "content": new_chunk_text,
                        "chunk_type": new_chunk_type
                    }
                else:
                    # 같은 타입이면 내용만 추가
                    current_response["content"] += new_chunk_text
                
                # 실시간으로 모든 응답 표시
                update_display()
            
        except json.JSONDecodeError as e:
            error_msg = f"JSON 파싱 오류: {e}"
            print(f"[ERROR] JSON 파싱 오류: {e}, 원본 데이터: {data_str}")
    
    # 모든 응답을 chat_history에 추가
    for response in current_responses:
        st.session_state.chat_history.append(response)
    
    # 응답을 하나도 받지 못한 경우 오류 메시지 추가
    if not response_received:
        error_msg = "APIM 서비스로부터 응답을 받지 못했습니다."
        st.session_state.chat_history.append({
            "role": "error",
            "content": error_msg
        })
        print(f"[ERROR] {error_msg}")
        return False
    
    return True

# 질문 처리 함수
def process_question(question):
    if not question:
        return
    
    print(f"[DEBUG] 질문 처리 시작: '{question}'")
    print(f"[DEBUG] API 엔드포인트: {API_BASE_URL}/stream")
    
    try:
        # 스트리밍 API 호출
        with st.spinner("APIM 서비스 문서를 검색하는 중입니다..."):
            print(f"[DEBUG] API 요청 시작: {question}")
            response = requests.post(
                f"{API_BASE_URL}/stream",
                json={"question": question},
                stream=True,
                headers={"Content-Type": "application/json"},
                timeout=60  # 타임아웃 설정
            )
            
            print(f"[DEBUG] API 응답 상태 코드: {response.status_code}")
            
            if response.status_code == 200:
                # 스트리밍 응답을 chunk별로 처리하여 UI에 바로 반영
                process_streaming_response(response, question)
                print(f"[DEBUG] 스트리밍 응답 처리 완료")
            else:
                error_msg = f"API 오류: {response.status_code} - {response.text}"
                print(f"[ERROR] {error_msg}")
                st.session_state.chat_history.append({
                    "role": "error",
                    "content": error_msg
                })
    except requests.RequestException as e:
        error_msg = f"API 요청 오류: {str(e)}"
        print(f"[ERROR] {error_msg}")
        st.session_state.chat_history.append({
            "role": "error",
            "content": error_msg
        })
    finally:
        # 진행 완료 상태 설정 (finally 블록에서 처리하여 예외 발생해도 상태 변경 보장)
        print(f"[DEBUG] 질문 처리 완료, 상태 초기화")
        st.session_state.is_processing = False
        st.session_state.sidebar_status_message = ""
        
        # 질문 처리 완료 플래그 설정
        st.session_state.question_processed = True
        
        # 강제 상태 초기화 플래그 설정
        st.session_state.force_state_reset = True
    
    return True  # 처리 완료 플래그

# 메인 레이아웃 구성
def main():
    # 초기 설정
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    
    # 상태 초기화 함수 정의
    def reset_processing_state():
        st.session_state.is_processing = False
        st.session_state.sidebar_status_message = ""
        st.session_state.sidebar_ask_clicked = False
        st.session_state.faq_clicked = False
    
    # 상태 초기화 타이밍 확인
    if st.session_state.get("force_state_reset", False):
        st.session_state.force_state_reset = False
        reset_processing_state()
    
    # 상단 고정: 타이틀 및 설명
    st.markdown("""
        <div style='position:sticky;top:0;z-index:100;background:white;padding-bottom:0.5rem;'>
            <h1 style='margin-bottom:0.2em;'>🔧 APIM 서비스 관리봇</h1>
        </div>
    """, unsafe_allow_html=True)
    
    # 사이드바 렌더링 (질문 입력 및 FAQ)
    render_sidebar()

    # 채팅 영역을 위한 컨테이너 생성 (고정된 구조)
    chat_container = st.container()
    
    # 사이드바에서 버튼 클릭 상태 감지
    question = st.session_state.get("sidebar_question", "")
    ask_clicked = st.session_state.get("sidebar_ask_clicked", False)
    
    # FAQ 클릭 처리
    faq_clicked = st.session_state.get("faq_clicked", False)
    faq_question = st.session_state.get("faq_question", "")
    
    # 채팅 내역 표시
    with chat_container:
        # 각 메시지를 순서대로 표시
        for idx, msg in enumerate(st.session_state.chat_history):
            role = msg.get('role', 'system')
            content = msg.get('content', '')
            avatar = AVATARS.get(role, '💬')
            chunk_type = msg.get('chunk_type', '')
            
            if role == 'user':
                st.markdown(
                    f"<div style='background:#E3F2FD;padding:12px 18px;border-radius:12px;margin:8px 0;max-width:90%;margin-left:10%;margin-right:0;text-align:right;border:1px solid #BBDEFB;'><b>{avatar} 관리자</b><br>{content}</div>",
                    unsafe_allow_html=True
                )
            else:
                # 에이전트 타입에 따라 레이블 추가 (선택사항)
                agent_label = ""
                if chunk_type == "rag":
                    agent_label = "<small style='color:#666;'>📚 문서 검색 완료</small><br>"
                elif chunk_type == "table":
                    agent_label = "<small style='color:#666;'>📊 결과 분석 완료</small><br>"
                elif chunk_type == "response":
                    agent_label = "<small style='color:#666;'>✅ 응답 생성 완료</small><br>"
                    
                # 마크다운 내용 출력 (레이블 + 내용)
                st.markdown(f"{agent_label}{content}", unsafe_allow_html=True)
                
                # 스크린샷인 경우 이미지도 표시
                if chunk_type == "screenshot":
                    st.markdown(f"{agent_label}{content}", unsafe_allow_html=True)
                    
                    # 스크린샷 표시 시도
                    image_displayed = False
                    
                    # 방법 1: Base64 데이터 사용 (스트리밍 응답에서)
                    if "data:image/png;base64," in content:
                        try:
                            # Base64 부분 추출
                            base64_start = content.find("data:image/png;base64,") + len("data:image/png;base64,")
                            base64_data = content[base64_start:].split()[0]  # 공백 전까지
                            
                            if len(base64_data) > 100:  # 유효한 길이인지 확인
                                import base64
                                import io
                                from PIL import Image
                                
                                # Base64 디코딩
                                image_data = base64.b64decode(base64_data)
                                image = Image.open(io.BytesIO(image_data))
                                
                                st.image(image, caption="📸 캡처된 스크린샷", use_container_width=True)
                                image_displayed = True
                                st.success("✅ Base64로 이미지 표시 성공!")
                        except Exception as e:
                            st.error(f"Base64 이미지 처리 실패: {str(e)}")
                    
                    # 방법 2: 파일명에서 이미지 찾기 (Base64 실패시)
                    if not image_displayed and "screenshot_" in content:
                        import re
                        filename_match = re.search(r'screenshot_\d+_\d+\.png', content)
                        if filename_match:
                            filename = filename_match.group()
                            abs_path = f"/Users/manjoongkim/Documents/GitHub/cloud_bot/screenshots/{filename}"
                            
                            if os.path.exists(abs_path):
                                st.image(abs_path, caption="📸 캡처된 스크린샷", use_container_width=True)
                                image_displayed = True
                                st.success(f"✅ 파일로 이미지 표시 성공: {filename}")
                    
                    # 방법 3: 최신 스크린샷 파일 찾기 (위 방법들 실패시)
                    if not image_displayed:
                        try:
                            import glob
                            screenshot_dir = "/Users/manjoongkim/Documents/GitHub/cloud_bot/screenshots"
                            if os.path.exists(screenshot_dir):
                                # 가장 최근 스크린샷 파일 찾기
                                pattern = os.path.join(screenshot_dir, "screenshot_*.png")
                                files = glob.glob(pattern)
                                if files:
                                    latest_file = max(files, key=os.path.getctime)
                                    st.image(latest_file, caption="📸 캡처된 스크린샷", use_container_width=True)
                                    image_displayed = True
                                    st.success(f"✅ 최신 파일로 이미지 표시 성공: {os.path.basename(latest_file)}")
                        except Exception as e:
                            st.error(f"최신 파일 검색 실패: {str(e)}")
                    
                    if not image_displayed:
                        st.warning("⚠️ 스크린샷을 표시할 수 없습니다.")
        
        # 처리 중일 때 스피너 표시
        if st.session_state.get("is_processing", False):
            with st.spinner("APIM 서비스 문서를 검색하는 중입니다..."):
                st.empty()  # 스피너가 보이도록 빈 공간 추가
    
    # 질문 처리 (처리 중이 아닐 때만)
    if not st.session_state.get("is_processing", False):
        # 사이드바에서 질문하기 버튼 클릭
        if ask_clicked and question.strip():
            # 채팅 기록에 사용자 질문 추가
            st.session_state.chat_history.append({
                "role": "user",
                "content": question
            })
            # 처리 중 상태로 설정
            st.session_state.is_processing = True
            st.session_state.sidebar_status_message = "APIM 문서를 검색 중입니다..."
            # 화면 갱신 (사용자 질문을 표시하기 위해)
            st.rerun()
            
        # FAQ 버튼 클릭
        elif faq_clicked and faq_question.strip():
            # 채팅 기록에 사용자 질문 추가
            st.session_state.chat_history.append({
                "role": "user",
                "content": faq_question
            })
            # 처리 중 상태로 설정
            st.session_state.is_processing = True
            st.session_state.sidebar_status_message = "APIM 문서를 검색 중입니다..."
            # 화면 갱신 (사용자 질문을 표시하기 위해)
            st.rerun()
    # 처리 중일 때 - 처리를 시작하거나 처리 완료 후 상태 초기화
    else:
        # 처리 시작 (사용자 질문이 표시된 후)
        current_question = ""
        
        # 마지막 사용자 질문 찾기
        for msg in reversed(st.session_state.chat_history):
            if msg.get("role") == "user":
                current_question = msg.get("content", "")
                break
        
        if current_question:
            # 질문 처리 함수 호출
            process_question(current_question)
            
            # 일반 질문 버튼 클릭 시 플래그 초기화
            if st.session_state.get("sidebar_ask_clicked", False):
                st.session_state.sidebar_ask_clicked = False
            
            # FAQ 버튼 클릭 시 플래그 초기화
            if st.session_state.get("faq_clicked", False):
                st.session_state.faq_clicked = False
                st.session_state.faq_question = ""
            
            # 강제 상태 초기화
            st.session_state.force_state_reset = True
            # 화면 갱신 (응답 표시)
            st.rerun()

# 메인 함수 실행
if __name__ == "__main__":
    main()
