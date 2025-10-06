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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class LangChainVectorStore:
    def __init__(self):
        self.conn = psycopg2.connect(
            dbname="mydb", user="hwangeunbi", password="", host="localhost", port="5432"
        )

        # PostgreSQL 연결 문자열 (LangChain용)
        self.connection_string = "postgresql+psycopg://hwangeunbi:@localhost:5432/mydb"

        # 캐싱 임베딩
        self.embeddings = self._init_embeddings()

        # 텍스트 분할기
        self.text_splitters = self._init_splitters()

    def _init_embeddings(self):
        """캐싱된 임베딩 초기화"""
        store = LocalFileStore("./cache/")
        base_embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small", openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        cached_embeddings = CacheBackedEmbeddings.from_bytes_store(
            base_embeddings, store, namespace="openai_embeddings"
        )

        logger.info("임베딩 모델 초기화 완료")
        return cached_embeddings

    def _init_splitters(self):
        """텍스트 분할기 초기화"""
        markdown_splitter = MarkdownTextSplitter(
            chunk_size=2000, chunk_overlap=200  # 마크다운 헤더 기준으로 큰 청크
        )

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
        """PGVector 벡터스토어 생성"""
        logger.info("벡터스토어 생성 중...")

        vectorstore = PGVector.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name="notion_documents",
            connection=self.connection_string,
            use_jsonb=True,
        )

        logger.info("벡터스토어 생성 완료")
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

    def test_search(self, vectorstore, query="모멘텀 예측", k=3):
        """검색 테스트"""
        logger.info(f"\n검색 테스트: '{query}'")

        retriever = self.get_retriever(vectorstore, k=k)
        results = retriever.invoke(query)

        print("\n" + "=" * 80)
        print(f"검색 쿼리: '{query}'")
        print("=" * 80)

        for i, doc in enumerate(results, 1):
            print(f"\n[{i}] 제목: {doc.metadata['title']}")
            print(f"카테고리: {doc.metadata['category']}")
            print(f"날짜: {doc.metadata.get('date', 'N/A')}")
            print(f"내용: {doc.page_content[:200]}...")
            print("-" * 80)

        return results

    def test_filtered_search(
        self, vectorstore, query="모멘텀", category="결과분석", k=3
    ):
        """필터링 검색 테스트"""
        logger.info(f"\n필터링 검색: '{query}' (카테고리: {category})")

        retriever = self.get_retriever(vectorstore, k=k, filters={"category": category})
        results = retriever.invoke(query)

        print("\n" + "=" * 80)
        print(f"검색 쿼리: '{query}' | 필터: category={category}")
        print("=" * 80)

        for i, doc in enumerate(results, 1):
            print(f"\n[{i}] 제목: {doc.metadata['title']}")
            print(f"카테고리: {doc.metadata['category']}")
            print(f"내용: {doc.page_content[:150]}...")
            print("-" * 80)

        return results

    def close(self):
        """연결 종료"""
        self.conn.close()


def main():
    vs = LangChainVectorStore()

    # 1. 문서 로드 및 분할
    documents = vs.load_and_split_documents()

    # 2. 벡터스토어 생성
    vectorstore = vs.create_vectorstore(documents)

    # 3. 기본 검색 테스트
    vs.test_search(vectorstore, "모멘텀 예측", k=3)

    # 4. 필터링 검색 테스트
    vs.test_filtered_search(vectorstore, "모멘텀", "결과분석", k=3)

    # 5. 연결 종료
    vs.close()

    print("\n벡터스토어 생성 완료")
    print("\n사용 예시:")
    print("retriever = vectorstore.as_retriever(search_kwargs={'k': 5})")
    print("results = retriever.invoke('검색 쿼리')")


if __name__ == "__main__":
    main()
