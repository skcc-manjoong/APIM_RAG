# 프롬프트 템플릿 유틸
# 역할 부여 + Chain-of-Thought(내부) + Few-shot 예시 포함

from typing import List, Dict


def build_rag_query_messages(question: str) -> List[Dict]:
    """한국어 사용자 질문을 RAG 검색에 적합한 영어 키워드 문장으로 변환하도록 유도하는 메시지 구성.
    - 역할 부여
    - Chain-of-Thought는 내부적으로만 수행(출력 금지)
    - Few-shot 예시 포함
    - 최종 출력은 JSON {"english_query":"..."} 형태
    """
    system = (
        "너는 APIM 문서 검색을 보조하는 전문 분석가다.\n"
        "규칙:\n"
        "- 질문을 이해하고 내부적으로 생각한 뒤, RAG 검색에 적합한 영어 키워드 문장 한 줄을 만들 것\n"
        "- 생각 과정은 출력하지 말 것(최종 답변만 출력)\n"
        "- 반드시 JSON으로만 출력: {\"english_query\": \"...\"}\n"
    )
    # Few-shot: 한국어 → 영어 키워드 변환 예시 3개
    examples = [
        {"role": "user", "content": "게이트웨이 타임아웃 설정 방법 알려줘"},
        {"role": "assistant", "content": '{"english_query":"APIM gateway timeout configuration guide"}'},
        {"role": "user", "content": "API Rate Limit은 어디서 바꿔?"},
        {"role": "assistant", "content": '{"english_query":"APIM rate limiting policy change steps"}'},
        {"role": "user", "content": "JWT 인증 정책 설정하는 화면이 어디야?"},
        {"role": "assistant", "content": '{"english_query":"APIM JWT authentication policy configuration location"}'}
    ]
    user = (
        "아래 질문을 분석해 영어 키워드 문장으로 변환하라.\n"
        f"[질문]\n{question}\n"
        "반드시 JSON만 출력: {\"english_query\": \"...\"}"
    )
    messages: List[Dict] = [{"role": "system", "content": system}] + examples + [
        {"role": "user", "content": user}
    ]
    return messages


def build_table_summary_messages(user_request: str, context: str, evidence_block: str) -> List[Dict]:
    """RAG 컨텍스트로 답변 요약/표 생성. 역할/규칙/CoT(내부), 출력 형식 고정.
    - 최종 출력은 한국어 설명(자세히) + 마크다운 표 + 근거 섹션
    """
    system = (
        "너는 APIM 관리자이자 기술 문서 요약가다.\n"
        "규칙:\n"
        "- 먼저 내부적으로 근거를 바탕으로 생각하고, 최종 출력에 생각은 포함하지 말 것\n"
        "- 컨텍스트에 없는 사실은 추론/창작하지 말 것\n"
        "- 최종 출력 형식:\n"
        "  1) 한국어 설명(자세히, 단계별/항목별 상세 설명. 가능하면 목록 사용. 특정 레이블 문구는 쓰지 말 것)\n"
        "  2) 마크다운 표(헤더 포함, 최대 10행)\n"
        "  3) 근거 섹션(사용한 청크 리스트를 그대로 나열)\n"
        "- 주의: '간결한 한국어 설명 문단:' 같은 레이블이나 머리말을 출력하지 말 것\n"
    )
    user = f"""
[사용자 요청]
{user_request}

[컨텍스트]
{context}

[근거]
{evidence_block}

위 규칙과 형식에 따라 자세히 서술하라. 레이블 문구는 출력하지 말고, 본문부터 시작하라.
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# 로그용 메타 정보 헬퍼

def rag_prompt_meta() -> str:
    return (
        "[prompt] RAG 질의 변환: 역할부여+CoT(출력비공개)+Few-shot(3개) 적용, 출력 JSON {english_query}"
    )


def table_prompt_meta() -> str:
    return (
        "[prompt] 요약/표 생성: 역할부여+CoT(출력비공개) 적용, 형식=한국어 설명+표(최대10행)+근거"
    ) 