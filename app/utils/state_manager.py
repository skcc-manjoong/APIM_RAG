import streamlit as st

def init_session_state():
    """세션 상태를 초기화합니다."""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    
    if "sidebar_question" not in st.session_state:
        st.session_state.sidebar_question = ""
    
    if "sidebar_ask_clicked" not in st.session_state:
        st.session_state.sidebar_ask_clicked = False

def reset_chat_history():
    """채팅 기록을 초기화합니다."""
    st.session_state.chat_history = []

def add_message(role, content):
    """채팅 기록에 메시지를 추가합니다."""
    st.session_state.chat_history.append({
        "role": role,
        "content": content
    })

def set_processing_state(is_processing):
    """처리 상태를 설정합니다."""
    st.session_state.is_processing = is_processing
