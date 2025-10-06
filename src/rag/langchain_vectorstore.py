import psycopg2
from dotenv import load_dotenv
import os
import logging
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document
from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore
from langchain.text_splitter import MarkdownTextSplitter, RecursiveCharacterTextSplitter
from langchain_teddynote import logging as teddynote_logging
from langchain_upstage import UpstageEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
import warnings
import numpy as np


load_dotenv()

warnings.filterwarnings("ignore", category=UserWarning)

teddynote_logging.langsmith("report-generator")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LangChainVectorStore:
    def __init__(self, embedding_type="openai"):
        """
        embedding_type: "openai", "upstage", "huggingface" 중 선택
        """
        self.embedding_type = embedding_type

        self.conn = psycopg2.connect(
            dbname="mydb", user="hwangeunbi", password="", host="localhost", port="5432"
        )

        # PostgreSQL 연결 문자열 (LangChain용)
        self.connection_string = "postgresql+psycopg://hwangeunbi:@localhost:5432/mydb"

        # 캐싱 임베딩
        self.embeddings = self._init_embeddings(embedding_type)

        # 텍스트 분할기
        self.text_splitters = self._init_splitters()

    def _init_embeddings(self, embedding_type):
        """캐싱된 임베딩 초기화 - 여러 모델 지원"""

        if embedding_type == "openai":
            store = LocalFileStore("./cache/openai/")
            base_embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=os.getenv("OPENAI_API_KEY"),
            )
            cached_embeddings = CacheBackedEmbeddings.from_bytes_store(
                base_embeddings, store, namespace="openai_embeddings"
            )
            logger.info("OpenAI 임베딩 모델 초기화 완료")
            return cached_embeddings

        elif embedding_type == "upstage":
            store = LocalFileStore("./cache/upstage/")
            base_embeddings = UpstageEmbeddings(
                model="solar-embedding-1-large-passage",
                upstage_api_key=os.getenv("UPSTAGE_API_KEY"),
            )
            cached_embeddings = CacheBackedEmbeddings.from_bytes_store(
                base_embeddings, store, namespace="upstage_embeddings"
            )
            logger.info("Upstage 임베딩 모델 초기화 완료")
            return cached_embeddings

        elif embedding_type == "huggingface":

            store = LocalFileStore("./cache/huggingface/")
            base_embeddings = HuggingFaceEmbeddings(
                model_name="intfloat/multilingual-e5-large-instruct",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            cached_embeddings = CacheBackedEmbeddings.from_bytes_store(
                base_embeddings, store, namespace="huggingface_embeddings"
            )
            logger.info("HuggingFace 임베딩 모델 초기화 완료")
            return cached_embeddings

        else:
            raise ValueError(f"지원하지 않는 임베딩 타입: {embedding_type}")

    def _init_splitters(self):
        """텍스트 분할기 초기화"""
        markdown_splitter = MarkdownTextSplitter(chunk_size=2000, chunk_overlap=200)

        recursive_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        return {"markdown": markdown_splitter, "recursive": recursive_splitter}

    def load_and_split_documents(self):
        """notion_pages에서 문서 로드 및 분할"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT page_id, title, category, date, content, 
                       created_time, last_edited_time
                FROM notion_pages
                ORDER BY created_time
            """
            )

            rows = cur.fetchall()
            all_chunks = []

            logger.info(f"처리할 페이지: {len(rows)}개")

            for page_id, title, category, date, content, created, edited in rows:
                # 1단계: MarkdownTextSplitter로 섹션 분할
                markdown_chunks = self.text_splitters["markdown"].split_text(content)

                # 2단계: 큰 청크는 RecursiveCharacterTextSplitter로 재분할
                for md_chunk in markdown_chunks:
                    if len(md_chunk) > 1000:
                        sub_chunks = self.text_splitters["recursive"].split_text(
                            md_chunk
                        )
                    else:
                        sub_chunks = [md_chunk]

                    # Document 객체 생성
                    for chunk_text in sub_chunks:
                        doc = Document(
                            page_content=chunk_text,
                            metadata={
                                "page_id": page_id,
                                "title": title,
                                "category": category or "미분류",
                                "date": str(date) if date else None,
                                "created_time": str(created),
                                "last_edited_time": str(edited),
                                "source": "notion",
                            },
                        )
                        all_chunks.append(doc)

                logger.info(
                    f"처리 완료: {title} ({len([d for d in all_chunks if d.metadata['page_id'] == page_id])}개 청크)"
                )

            logger.info(f"총 {len(all_chunks)}개 청크 생성 완료")
            return all_chunks

    def create_vectorstore(self, documents):
        """PGVector 벡터스토어 생성 - 기존 컬렉션 삭제 후 재생성"""
        collection_name = f"notion_documents_{self.embedding_type}"

        # 기존 컬렉션 삭제
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM langchain_pg_embedding 
                    WHERE collection_id = (
                        SELECT uuid FROM langchain_pg_collection 
                        WHERE name = %s
                    )
                """,
                    (collection_name,),
                )
                cur.execute(
                    "DELETE FROM langchain_pg_collection WHERE name = %s",
                    (collection_name,),
                )
                self.conn.commit()
            logger.info(f"기존 컬렉션 삭제: {collection_name}")
        except Exception as e:
            logger.info(f"기존 컬렉션 없음: {e}")

        logger.info(f"벡터스토어 생성 중... (컬렉션: {collection_name})")

        vectorstore = PGVector.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name=collection_name,
            connection=self.connection_string,
            use_jsonb=True,
        )

        logger.info(f"벡터스토어 생성 완료 (컬렉션: {collection_name})")
        return vectorstore

    def get_retriever(self, vectorstore, k=5, filters=None):
        """리트리버 생성"""
        search_kwargs = {"k": k}
        if filters:
            search_kwargs["filter"] = filters

        retriever = vectorstore.as_retriever(
            search_type="similarity", search_kwargs=search_kwargs
        )

        return retriever

    def close(self):
        """연결 종료"""
        self.conn.close()


def create_all_vectorstores():
    """모든 임베딩 모델에 대해 벡터스토어 생성"""
    embedding_types = ["openai", "upstage", "huggingface"]
    vectorstores = {}

    # 문서는 한 번만 로드
    vs_temp = LangChainVectorStore(embedding_type="openai")
    documents = vs_temp.load_and_split_documents()
    vs_temp.close()

    # 각 임베딩 모델별로 벡터스토어 생성
    for emb_type in embedding_types:
        logger.info(f"\n{'='*50}")
        logger.info(f"{emb_type.upper()} 임베딩 처리 시작")
        logger.info(f"{'='*50}")

        vs = LangChainVectorStore(embedding_type=emb_type)
        vectorstore = vs.create_vectorstore(documents)
        vectorstores[emb_type] = vectorstore
        vs.close()

    return vectorstores, documents


def compare_retrievers(vectorstores, query, k=5):
    """여러 임베딩 모델의 검색 성능 비교 (유사도 점수 포함)"""
    logger.info(f"\n{'='*70}")
    logger.info(f"검색 쿼리: {query}")
    logger.info(f"{'='*70}\n")

    results = {}

    for emb_type, vectorstore in vectorstores.items():
        logger.info(f"\n[{emb_type.upper()}] 검색 결과:")
        logger.info("-" * 70)

        # similarity_search_with_score 사용
        docs_with_scores = vectorstore.similarity_search_with_score(query, k=k)
        results[emb_type] = docs_with_scores

        # 상세 정보 출력
        for i, (doc, score) in enumerate(docs_with_scores, 1):
            logger.info(f"\n{i}. [유사도 거리: {score:.4f}]")
            logger.info(f"   제목: {doc.metadata.get('title', 'N/A')}")
            logger.info(f"   카테고리: {doc.metadata.get('category', 'N/A')}")
            logger.info(f"   내용 미리보기: {doc.page_content[:100]}...")

        # 유사도 점수만 간단히 출력
        print(f"\n[Query] {query} ({emb_type.upper()})")
        print(f"{'='*70}")
        for i, (doc, score) in enumerate(docs_with_scores):
            title = doc.metadata.get("title", "N/A")[:40]
            content_preview = doc.page_content[:60].replace("\n", " ")
            # PGVector는 거리를 반환하므로, 유사도로 변환 (1 - 정규화된 거리)
            # 또는 그냥 거리값 사용 (낮을수록 유사)
            print(f"[{i}] 거리: {score:.4f} | {title}")
            print(f"    내용: {content_preview}...")
        print()

    return results


def compare_retrievers_with_similarity(vectorstores, query, k=5):
    """
    여러 임베딩 모델의 검색 성능 비교
    유사도를 코사인 유사도로 변환하여 표시 (높을수록 유사)
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"검색 쿼리: {query}")
    logger.info(f"{'='*70}\n")

    results = {}

    for emb_type, vectorstore in vectorstores.items():
        logger.info(f"\n[{emb_type.upper()}] 검색 결과:")
        logger.info("-" * 70)

        # similarity_search_with_score 사용
        docs_with_scores = vectorstore.similarity_search_with_score(query, k=k)
        results[emb_type] = docs_with_scores

        # 거리를 유사도로 변환 (선택적)
        # L2 거리의 경우: similarity = 1 / (1 + distance)
        # 코사인 거리의 경우: similarity = 1 - distance

        print(f"\n[Query] {query} ({emb_type.upper()})")
        print(f"{'='*70}")

        for i, (doc, distance) in enumerate(docs_with_scores):
            # 유사도 변환 (L2 거리 가정)
            similarity = 1 / (1 + distance)

            title = doc.metadata.get("title", "N/A")[:40]
            content_preview = doc.page_content[:60].replace("\n", " ")

            print(f"[{i}] 유사도: {similarity:.4f} (거리: {distance:.4f})")
            print(f"    제목: {title}")
            print(f"    내용: {content_preview}...")
            print()

    return results


def compare_retrievers_table(vectorstores, query, k=5):
    """표 형식으로 모든 모델 결과 비교"""
    print(f"\n{'='*100}")
    print(f"검색 쿼리: {query}")
    print(f"{'='*100}\n")

    all_results = {}

    # 모든 모델에서 검색
    for emb_type, vectorstore in vectorstores.items():
        docs_with_scores = vectorstore.similarity_search_with_score(query, k=k)
        all_results[emb_type] = docs_with_scores

    # 순위별로 비교
    for rank in range(k):
        print(f"\n[순위 {rank + 1}]")
        print("-" * 100)

        for emb_type, docs_with_scores in all_results.items():
            if rank < len(docs_with_scores):
                doc, score = docs_with_scores[rank]
                title = doc.metadata.get("title", "N/A")[:35]
                similarity = 1 / (1 + score)  # 거리를 유사도로 변환
                content_preview = doc.page_content[:80].replace("\n", " ")
                print(
                    f"{emb_type:12s}: 유사도={similarity:.4f} (거리={score:.4f}) | {title}"
                )
                print(f"             내용: {content_preview}...")
    print(f"\n{'='*100}\n")

    return all_results


def main():
    """
    사용 예시:
    1. 단일 임베딩 모델로 벡터스토어 생성
    2. 모든 임베딩 모델로 벡터스토어 생성 및 성능 비교
    """

    # 옵션 1: 단일 모델 테스트
    # vs = LangChainVectorStore(embedding_type="openai")
    # documents = vs.load_and_split_documents()
    # vectorstore = vs.create_vectorstore(documents)
    #
    # # 유사도와 함께 검색
    # docs_with_scores = vectorstore.similarity_search_with_score("프로젝트 일정", k=5)
    # for i, (doc, score) in enumerate(docs_with_scores, 1):
    #     print(f"{i}. 거리: {score:.4f} | {doc.metadata.get('title')}")
    #
    # vs.close()

    # 옵션 2: 모든 모델 비교
    vectorstores, documents = create_all_vectorstores()

    # 검색 쿼리들
    test_queries = ["RAG", "프로젝트 일정", "모멘텀 예측"]

    for query in test_queries:
        print(f"\n\n{'#'*100}")
        print(f"# 쿼리: {query}")
        print(f"{'#'*100}")

        # 방법 1: 기본 비교
        # compare_retrievers(vectorstores, query, k=3)

        # 방법 2: 유사도 변환 포함
        # compare_retrievers_with_similarity(vectorstores, query, k=3)

        # 방법 3: 표 형식 비교
        compare_retrievers_table(vectorstores, query, k=3)

    logger.info("\n\n벡터스토어 생성 및 비교 완료!")


if __name__ == "__main__":
    # 벡터스토어 생성 (최초 1회만)
    vectorstores, documents = create_all_vectorstores()

    # 1. 먼저 중복 확인
    print("\n[중복 체크: page_id 확인]")
    print("=" * 50)
    docs_with_scores = vectorstores["openai"].similarity_search_with_score("RAG", k=5)
    for i, (doc, score) in enumerate(docs_with_scores):
        print(
            f"{i}. 거리={score:.4f} | page_id={doc.metadata['page_id']} | 제목={doc.metadata['title'][:30]}"
        )

    # 2. 그 다음 전체 비교
    print("\n\n[전체 모델 비교]")
    test_queries = ["RAG", "테니스", "급이량"]
    for query in test_queries:
        compare_retrievers_table(vectorstores, query, k=3)
