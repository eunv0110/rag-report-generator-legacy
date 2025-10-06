import psycopg2
from dotenv import load_dotenv
import os
from openai import OpenAI
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class EmbeddingGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.conn = psycopg2.connect(
            dbname="mydb", user="hwangeunbi", password="", host="localhost", port="5432"
        )

    def add_embedding_column(self):
        """임베딩 컬럼 추가 (pgvector 확장 필요)"""
        with self.conn.cursor() as cur:
            # pgvector 확장 설치 확인
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                self.conn.commit()
                logger.info("✅ pgvector 확장 활성화")
            except Exception as e:
                logger.warning(f"⚠️ pgvector 확장 설치 필요: {e}")
                logger.info("PostgreSQL에 pgvector 설치 필요: brew install pgvector")
                # 대안: TEXT 타입으로 저장
                cur.execute(
                    """
                    ALTER TABLE notion_chunks 
                    ADD COLUMN IF NOT EXISTS embedding TEXT;
                """
                )
                self.conn.commit()
                logger.info("✅ embedding 컬럼 추가 (TEXT 타입)")
                return

            # vector 타입으로 컬럼 추가
            cur.execute(
                """
                ALTER TABLE notion_chunks 
                ADD COLUMN IF NOT EXISTS embedding vector(1536);
            """
            )
            self.conn.commit()
            logger.info("✅ embedding 컬럼 추가 (vector 타입)")

    def generate_embedding(self, text):
        """OpenAI API로 임베딩 생성"""
        try:
            response = self.client.embeddings.create(
                model="text-embedding-3-small",  # 또는 "text-embedding-ada-002"
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"임베딩 생성 실패: {e}")
            return None

    def process_chunks(self, batch_size=10):
        """모든 청크에 임베딩 생성"""
        with self.conn.cursor() as cur:
            # 임베딩이 없는 청크 조회
            cur.execute(
                """
                SELECT id, chunk_text 
                FROM notion_chunks 
                WHERE embedding IS NULL
                ORDER BY id
            """
            )

            chunks = cur.fetchall()
            total = len(chunks)

            if total == 0:
                logger.info("✅ 모든 청크에 임베딩이 이미 존재합니다")
                return

            logger.info(f"📊 처리할 청크: {total}개")

            for idx, (chunk_id, text) in enumerate(chunks, 1):
                try:
                    # 임베딩 생성
                    embedding = self.generate_embedding(text)

                    if embedding:
                        # DB에 저장
                        cur.execute(
                            """
                            UPDATE notion_chunks 
                            SET embedding = %s 
                            WHERE id = %s
                        """,
                            (str(embedding), chunk_id),
                        )

                        if idx % batch_size == 0:
                            self.conn.commit()
                            logger.info(
                                f"✅ 진행률: {idx}/{total} ({idx/total*100:.1f}%)"
                            )

                    # API rate limit 방지
                    time.sleep(0.1)

                except Exception as e:
                    logger.error(f"청크 {chunk_id} 처리 실패: {e}")
                    continue

            # 최종 커밋
            self.conn.commit()
            logger.info(f"✅ 완료! 총 {total}개 청크 임베딩 생성")

    def create_index(self):
        """벡터 유사도 검색을 위한 인덱스 생성"""
        with self.conn.cursor() as cur:
            try:
                # pgvector 인덱스 생성 (HNSW 알고리즘)
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
                    ON notion_chunks 
                    USING hnsw (embedding vector_cosine_ops);
                """
                )
                self.conn.commit()
                logger.info("✅ 벡터 인덱스 생성 완료")
            except Exception as e:
                logger.warning(f"⚠️ 벡터 인덱스 생성 실패 (pgvector 필요): {e}")

    def test_similarity_search(self, query="공공AX프로젝트", top_k=3):
        """유사도 검색 테스트"""
        # 쿼리 임베딩 생성
        query_embedding = self.generate_embedding(query)

        if not query_embedding:
            logger.error("쿼리 임베딩 생성 실패")
            return

        with self.conn.cursor() as cur:
            try:
                # pgvector를 사용한 유사도 검색
                cur.execute(
                    """
                    SELECT 
                        chunk_text,
                        metadata->>'title' as title,
                        1 - (embedding <=> %s::vector) as similarity
                    FROM notion_chunks
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """,
                    (str(query_embedding), str(query_embedding), top_k),
                )
            except:
                # pgvector 없으면 TEXT 기반 검색 (느림)
                logger.warning("pgvector 미설치. 전체 스캔으로 유사도 계산...")
                cur.execute(
                    """
                    SELECT chunk_text, metadata->>'title' as title
                    FROM notion_chunks
                    WHERE chunk_text ILIKE %s
                    LIMIT %s
                """,
                    (f"%{query}%", top_k),
                )

            results = cur.fetchall()

            print("\n" + "=" * 80)
            print(f"🔍 검색 쿼리: '{query}'")
            print("=" * 80)

            for i, result in enumerate(results, 1):
                if len(result) == 3:
                    text, title, similarity = result
                    print(f"\n[{i}] 제목: {title}")
                    print(f"유사도: {similarity:.4f}")
                else:
                    text, title = result
                    print(f"\n[{i}] 제목: {title}")

                print(f"내용: {text[:200]}...")
                print("-" * 80)

    def close(self):
        """연결 종료"""
        self.conn.close()


def main():
    generator = EmbeddingGenerator()

    # 1. 임베딩 컬럼 추가
    generator.add_embedding_column()

    # 2. 모든 청크에 임베딩 생성
    generator.process_chunks(batch_size=10)

    # 3. 인덱스 생성 (선택)
    generator.create_index()

    # 4. 유사도 검색 테스트
    generator.test_similarity_search("감염병 데이터")

    # 5. 연결 종료
    generator.close()


if __name__ == "__main__":
    main()
