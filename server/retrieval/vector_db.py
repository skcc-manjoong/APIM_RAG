import os
import json
import faiss
import numpy as np
import pickle
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
import logging
from pathlib import Path
from pypdf import PdfReader
from bs4 import BeautifulSoup

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='vector_db.log'
)
logger = logging.getLogger(__name__)

class VectorDB:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """
        벡터 데이터베이스 초기화
        Args:
            model_name: 사용할 Sentence Transformer 모델 이름
        """
        self.model = SentenceTransformer(model_name)
        self.documents = []
        self.index = None
        self.vector_dim = 384  # all-MiniLM-L6-v2 모델의 벡터 차원

    def ingest_pdfs(self, pdf_dir: str, chunk_size: int = 2500, overlap: int = 300) -> None:
        """
        지정한 디렉토리의 PDF들을 읽어 텍스트를 청크로 나누고 문서 리스트(self.documents)에 적재합니다.
        Args:
            pdf_dir: PDF 파일이 위치한 디렉토리 경로
            chunk_size: 청크 크기(문자 기준)
            overlap: 청크 겹침(문자 기준)
        """
        pdf_path = Path(pdf_dir)
        if not pdf_path.exists() or not pdf_path.is_dir():
            raise FileNotFoundError(f"PDF 디렉토리를 찾을 수 없습니다: {pdf_dir}")
        docs: List[Dict[str, Any]] = []
        for pdf_file in sorted(list(pdf_path.rglob("*.pdf"))):
            try:
                reader = PdfReader(str(pdf_file))
                text_parts: List[str] = []
                for page in reader.pages:
                    try:
                        text_parts.append(page.extract_text() or "")
                    except Exception:
                        text_parts.append("")
                full_text = "\n".join(text_parts).strip()
                if not full_text:
                    continue
                # 간단한 문자 기반 청크 분할
                start = 0
                chunk_index = 0
                while start < len(full_text):
                    end = min(start + chunk_size, len(full_text))
                    chunk_text = full_text[start:end]
                    # 다음 시작 위치(오버랩 적용)
                    start = end - overlap if end - overlap > start else end
                    # 문서 엔트리 생성
                    docs.append({
                        'service': 'apim',
                        'name': f"{pdf_file.stem}_chunk_{chunk_index}",
                        'description': f"Chunk {chunk_index} from {pdf_file.name}",
                        'parameters': [],
                        'search_text': chunk_text
                    })
                    chunk_index += 1
                logger.info(f"Ingested {pdf_file.name} into {chunk_index} chunks")
            except Exception as e:
                logger.error(f"PDF 처리 실패: {pdf_file} - {e}")
        self.documents = docs
        logger.info(f"총 {len(self.documents)}개 청크 문서를 적재했습니다 (디렉토리: {pdf_dir})")

    def ingest_htmls(self, html_dir: str, chunk_size: int = 2500, overlap: int = 300) -> None:
        """
        지정한 디렉토리의 HTML 파일들을 (하위 폴더 포함) 읽어 텍스트를 청크로 나누고 문서 리스트(self.documents)에 적재합니다.
        Args:
            html_dir: HTML 파일이 위치한 루트 디렉토리 경로
            chunk_size: 청크 크기(문자 기준)
            overlap: 청크 겹침(문자 기준)
        """
        html_path = Path(html_dir)
        if not html_path.exists() or not html_path.is_dir():
            raise FileNotFoundError(f"HTML 디렉토리를 찾을 수 없습니다: {html_dir}")
        docs: List[Dict[str, Any]] = []
        html_files = list(html_path.rglob("*.html")) + list(html_path.rglob("*.htm"))
        logger.info(f"HTML 파일 {len(html_files)}개 발견: 루트={html_path}")
        for html_file in sorted(html_files):
            try:
                with open(html_file, "r", encoding="utf-8", errors="ignore") as f:
                    html = f.read()
                soup = BeautifulSoup(html, "html.parser")
                # 스크립트/스타일 제거
                for tag in soup(["script", "style", "noscript"]):
                    tag.extract()
                # 헤딩/문단/리스트 중심으로 텍스트 재구성
                pieces: List[str] = []
                title = soup.title.get_text(strip=True) if soup.title else html_file.stem
                pieces.append(f"# {title}")
                for node in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "code", "pre"]):
                    text = node.get_text(separator=" ", strip=True)
                    if not text:
                        continue
                    if node.name in ["h1", "h2", "h3", "h4"]:
                        pieces.append(f"\n## {text}\n")
                    elif node.name in ["li"]:
                        pieces.append(f"- {text}")
                    else:
                        pieces.append(text)
                full_text = "\n".join(pieces)
                if not full_text.strip():
                    continue
                # 문자 기반 청크 분할
                start = 0
                chunk_index = 0
                while start < len(full_text):
                    end = min(start + chunk_size, len(full_text))
                    chunk_text = full_text[start:end]
                    start = end - overlap if end - overlap > start else end
                    docs.append({
                        'service': 'apim',
                        'name': f"{html_file.stem}_chunk_{chunk_index}",
                        'description': f"Chunk {chunk_index} from {html_file.name}",
                        'parameters': [],
                        'search_text': chunk_text
                    })
                    chunk_index += 1
                logger.info(f"Ingested {html_file.name} into {chunk_index} chunks")
            except Exception as e:
                logger.error(f"HTML 처리 실패: {html_file} - {e}")
        self.documents = docs
        logger.info(f"총 {len(self.documents)}개 청크 문서를 적재했습니다 (디렉토리: {html_dir})")

    def create_index(self) -> None:
        """문서로부터 FAISS 인덱스 생성"""
        try:
            if not self.documents:
                raise ValueError("인덱싱할 문서가 없습니다. 먼저 ingest_pdfs() 또는 ingest_htmls()를 호출하세요.")
            
            # 문서 텍스트를 벡터로 변환
            texts = [doc['search_text'] for doc in self.documents]
            embeddings = self.model.encode(texts, show_progress_bar=True)
            
            # FAISS 인덱스 생성
            self.index = faiss.IndexFlatL2(self.vector_dim)
            self.index.add(embeddings.astype('float32'))
            
            logger.info(f"Successfully created FAISS index with {len(self.documents)} documents")
            
        except Exception as e:
            logger.error(f"Error creating index: {str(e)}")
            raise

    def save(self, vector_data_path: str = 'vector_data.pkl', index_path: str = 'faiss_index.bin') -> None:
        """
        벡터 DB 상태 저장
        Args:
            vector_data_path: 벡터 데이터를 저장할 경로
            index_path: FAISS 인덱스를 저장할 경로
        """
        try:
            # 문서 데이터 저장
            with open(vector_data_path, 'wb') as f:
                pickle.dump(self.documents, f)
                
            # FAISS 인덱스 저장
            if self.index is not None:
                faiss.write_index(self.index, index_path)
                
            logger.info(f"Saved vector data to {vector_data_path} and index to {index_path}")
            
        except Exception as e:
            logger.error(f"Error saving vector DB: {str(e)}")
            raise

    def load(self, vector_data_path: str = 'vector_data.pkl', index_path: str = 'faiss_index.bin') -> None:
        """
        저장된 벡터 DB 상태 로드
        Args:
            vector_data_path: 벡터 데이터 파일 경로
            index_path: FAISS 인덱스 파일 경로
        """
        try:
            # 문서 데이터 로드
            with open(vector_data_path, 'rb') as f:
                self.documents = pickle.load(f)
                
            # FAISS 인덱스 로드
            self.index = faiss.read_index(index_path)
            
            logger.info(f"Loaded {len(self.documents)} documents and FAISS index")
            
        except Exception as e:
            logger.error(f"Error loading vector DB: {str(e)}")
            raise

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        쿼리와 가장 유사한 문서 검색
        Args:
            query: 검색 쿼리
            k: 반환할 결과 수
        Returns:
            유사한 문서 리스트
        """
        try:
            # 쿼리를 벡터로 변환
            query_vector = self.model.encode([query])
            
            # 유사한 벡터 검색
            distances, indices = self.index.search(query_vector.astype('float32'), k)
            
            results = []
            for i, idx in enumerate(indices[0]):
                if idx != -1 and idx < len(self.documents):
                    doc = self.documents[idx]
                    results.append({
                        'document': doc,
                        'distance': float(distances[0][i]),
                        'similarity': float(1.0 - distances[0][i]/2)
                    })
                    
            return results
            
        except Exception as e:
            logger.error(f"Error in search: {str(e)}")
            return []

# 전역 싱글톤 관리
GLOBAL_VECTOR_DB: VectorDB | None = None

def _latest_mtime_in_dir(root: Path) -> float:
    latest = 0.0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in [".html", ".htm", ".pdf"]:
            try:
                latest = max(latest, p.stat().st_mtime)
            except Exception:
                continue
    return latest


def init_global_vector_db(pdf_dir: str, vector_data_path: str, index_path: str) -> None:
    global GLOBAL_VECTOR_DB
    vdb = VectorDB()
    vec_p = Path(vector_data_path)
    idx_p = Path(index_path)
    base_dir = Path(pdf_dir)

    need_rebuild = True
    if vec_p.exists() and idx_p.exists():
        # 콘텐츠가 더 최신이면 재인덱싱
        content_mtime = _latest_mtime_in_dir(base_dir)
        index_mtime = max(vec_p.stat().st_mtime, idx_p.stat().st_mtime)
        if index_mtime >= content_mtime:
            need_rebuild = False

    if not need_rebuild:
        vdb.load(vector_data_path=vector_data_path, index_path=index_path)
    else:
        html_candidates = list(base_dir.rglob("*.html")) + list(base_dir.rglob("*.htm"))
        pdf_candidates = list(base_dir.rglob("*.pdf"))
        if html_candidates:
            vdb.ingest_htmls(str(base_dir))
        elif pdf_candidates:
            vdb.ingest_pdfs(str(base_dir))
        else:
            raise FileNotFoundError(f"{base_dir}에서 .html/.htm/.pdf 파일을 찾을 수 없습니다")
        vdb.create_index()
        vdb.save(vector_data_path=vector_data_path, index_path=index_path)
    GLOBAL_VECTOR_DB = vdb
    logger.info("Global VectorDB initialized")


def get_global_vector_db() -> VectorDB | None:
    return GLOBAL_VECTOR_DB

def main():
    """
    벡터 DB 생성 및 테스트 (APIM 문서 기반)
    """
    try:
        # 기존 벡터 DB 파일 삭제
        for file in ['apim_vector_data.pkl', 'apim_faiss_index.bin']:
            if os.path.exists(file):
                os.remove(file)
                logger.info(f"Removed existing {file}")
        
        # 벡터 DB 초기화
        vector_db = VectorDB()
        
        # APIM HTML 파일 인덱싱
        apim_docs_dir = "apim_docs"
        if os.path.exists(apim_docs_dir):
            logger.info("Ingesting APIM documentation...")
            vector_db.ingest_htmls(apim_docs_dir)
        else:
            logger.warning(f"APIM docs directory not found: {apim_docs_dir}")
            return
        
        # 인덱스 생성
        logger.info("Creating vector database index...")
        vector_db.create_index()
        
        # 벡터 DB 저장
        logger.info("Saving vector database...")
        vector_db.save(vector_data_path='apim_vector_data.pkl', index_path='apim_faiss_index.bin')
        
        # 테스트 검색 수행 (APIM 관련)
        test_queries = [
            "How to configure API rate limiting",
            "APIM policy management guide",
            "API authentication setup steps",
            "Gateway configuration for microservices",
            "User role and permission management"
        ]
        
        logger.info("Testing search functionality...")
        for query in test_queries:
            results = vector_db.search(query)
            print(f"\nQuery: {query}")
            print(f"Found {len(results)} results")
            
            for i, result in enumerate(results[:3], 1):
                doc = result['document']
                print(f"\n{i}. {doc['name']}")
                print(f"Service: {doc['service'].upper()}")
                print(f"Similarity: {result['similarity']:.2f}")
                print(f"Description: {doc['description']}")
        
        logger.info("Vector database creation and testing completed successfully")
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main()
