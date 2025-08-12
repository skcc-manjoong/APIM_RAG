import streamlit as st

def render_sidebar():
    with st.sidebar:
        st.header("📝 질문 입력")
        st.write("APIM 서비스에 대해 궁금한 사항을 입력해주세요.")
        
        # 처리 중일 때 비활성화
        is_processing = st.session_state.get("is_processing", False)
        
        # 질문 처리 완료 플래그가 있으면 입력란 초기화
        if st.session_state.get("question_processed", False):
            st.session_state.question_processed = False
        
        # 질문 입력 필드
        question = st.text_input(
            "질문", value="", key="sidebar_question", 
            placeholder="APIM 관련 질문을 입력해주세요...",
            disabled=is_processing
        )
        
        # 상태 메시지 표시 영역
        status_placeholder = st.empty()
        if is_processing:
            status_placeholder.info("문서 검색 중입니다...")
        elif "sidebar_status_message" in st.session_state and st.session_state.sidebar_status_message:
            status_placeholder.info(st.session_state.sidebar_status_message)
        
        # 버튼 클릭 시 main의 process_question을 직접 호출
        if st.button("🔍 질문하기", key="sidebar_ask", disabled=is_processing) and question.strip():
            st.session_state.sidebar_ask_clicked = True
            # 상태 메시지 설정
            st.session_state.sidebar_status_message = "APIM 문서를 검색 중입니다..."
        
        # 자주 묻는 질문 섹션
        st.markdown("---")
        st.subheader("❓ 자주 묻는 질문")
        
        # 자주 묻는 질문 목록 (APIM 관련)
        faq_examples = [
            "API 인증 방법을 알려주세요",
            "게이트웨이 설정 방법은?",
            "사용자 권한 관리는 어떻게 하나요?"
        ]
        
        # 자주 묻는 질문 버튼 - 클릭 시 직접 질문 처리
        for idx, faq in enumerate(faq_examples):
            if st.button(f"💡 {faq}", key=f"faq_{idx}", disabled=is_processing):
                # 자주 묻는 질문 플래그 설정
                st.session_state.faq_question = faq
                st.session_state.faq_clicked = True
                # 화면 갱신
                st.rerun()
