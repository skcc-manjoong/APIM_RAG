from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings, ChatOpenAI

# .env 파일에서 환경 변수 로드
load_dotenv()


class Settings(BaseSettings):
    # Azure OpenAI 설정
    AOAI_API_KEY: str
    AOAI_ENDPOINT: str
    AOAI_DEPLOY_GPT4O: str
    AOAI_EMBEDDING_DEPLOYMENT: str
    AOAI_API_VERSION: str

    # OpenRouter 설정
    OPENROUTER_API_KEY: str 
    OPENROUTER_BASE_URL: str 
    OPENROUTER_MODEL: str 
    

    # Langfuse 설정
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_HOST: str

    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Debate Arena API"

    API_BASE_URL: str

    # SQLite 데이터베이스 설정
    DB_PATH: str = "history.db"
    SQLALCHEMY_DATABASE_URI: str = f"sqlite:///./{DB_PATH}"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    def get_llm_azopai(self):
        """Azure OpenAI LLM 인스턴스 반환 (툴 바인딩 없음)"""
        return AzureChatOpenAI(
            openai_api_key=settings.AOAI_API_KEY,
            azure_endpoint=settings.AOAI_ENDPOINT,
            azure_deployment=settings.AOAI_DEPLOY_GPT4O,
            api_version=settings.AOAI_API_VERSION,
            temperature=0.7,
            streaming=True,
        )

    def get_llm_openrouter(self):
        """OpenRouter LLM 인스턴스 반환 (툴 바인딩 없음)"""
        print(settings.OPENROUTER_API_KEY)
        return ChatOpenAI(
            openai_api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            model=settings.OPENROUTER_MODEL,
            temperature=0.7,
            streaming=True,
        )

    def get_embedding_azopai(self):
        """Azure OpenAI Embeddings 인스턴스를 반환합니다."""
        return AzureOpenAIEmbeddings(
            model=settings.AOAI_EMBEDDING_DEPLOYMENT,
            openai_api_version=settings.AOAI_API_VERSION,
            api_key=settings.AOAI_API_KEY,
            azure_endpoint=settings.AOAI_ENDPOINT,
        )


# 설정 인스턴스 생성
settings = Settings()


# 새로운 함수명으로만 노출

def get_llm_azopai():
    return settings.get_llm_azopai()

def get_llm_openrouter():
    return settings.get_llm_openrouter()

def get_embedding_azopai():
    return settings.get_embedding_azopai()
