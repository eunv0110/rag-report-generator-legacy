import psycopg2
from dotenv import load_dotenv
import os
from langchain.text_splitter import (
    HTMLHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class NotionChunkProcessor:
    def __init__(self):
        self.conn = psycopg2.connect(
            dbname="mydb", user="hwangeunbi", password="", host="localhost", port="5432"
        )

    def create_chunks_table(self):
        """청크 저장용 테이블 생성"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS notion_chunks (
                    id SERIAL PRIMARY KEY,
                    page_id TEXT,
                    chunk_index INTEGER,
                    chunk_text TEXT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_chunks_page_id ON notion_chunks(page_id);
            """
            )
            self.conn.commit()
            logger.info("✅ notion_chunks 테이블 생성 완료")

    def convert_notion_to_html(self, content, title):
        """Notion 콘텐츠를 HTML로 변환"""
        lines = content.split("\n")
        html_lines = ["<html><body>"]
        html_lines.append(f"<h1>{title}</h1>")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # # 기호로 시작하는 헤더 처리
            if line.startswith("#"):
                # #의 개수로 헤더 레벨 결정
                header_level = 0
                for char in line:
                    if char == "#":
                        header_level += 1
                    else:
                        break

                # 최대 h3까지만
                header_level = min(header_level + 1, 3)  # h2, h3으로 변환
                header_text = line.lstrip("#").strip()

                # 괄호 안의 숫자 제거 (예: #(1) -> #)
                if header_text.startswith("(") and ")" in header_text:
                    header_text = header_text.split(")", 1)[1].strip()

                html_lines.append(f"<h{header_level}>{header_text}</h{header_level}>")
            else:
                # 일반 텍스트는 p 태그로
                html_lines.append(f"<p>{line}</p>")

        html_lines.append("</body></html>")
        return "\n".join(html_lines)

    def split_content(self, html_content):
        """HTML 헤더 기준으로 1차 분할 후, 크기별로 2차 분할"""

        # 1단계: HTML 헤더 기준 분할
        headers_to_split_on = [
            ("h1", "제목"),
            ("h2", "섹션"),
            ("h3", "하위섹션"),
        ]

        html_splitter = HTMLHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        html_chunks = html_splitter.split_text(html_content)

        # 2단계: 각 섹션을 크기 기준으로 재분할
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        final_chunks = []
        for chunk in html_chunks:
            # 청크가 크면 재분할
            if len(chunk.page_content) > 1000:
                sub_chunks = text_splitter.split_text(chunk.page_content)
                for sub_chunk in sub_chunks:
                    final_chunks.append({"text": sub_chunk, "metadata": chunk.metadata})
            else:
                final_chunks.append(
                    {"text": chunk.page_content, "metadata": chunk.metadata}
                )

        return final_chunks

    def process_all_pages(self):
        """모든 페이지 처리"""
        with self.conn.cursor() as cur:
            # 모든 페이지 가져오기
            cur.execute(
                """
                SELECT page_id, title, category, date, content 
                FROM notion_pages
            """
            )

            pages = cur.fetchall()
            logger.info(f"📄 처리할 페이지: {len(pages)}개")

            for page_id, title, category, date, content in pages:
                try:
                    logger.info(f"➡️ 처리 중: {title}")

                    # HTML 변환
                    html_content = self.convert_notion_to_html(content, title)

                    # 청크 분할
                    chunks = self.split_content(html_content)

                    # DB에 저장
                    for idx, chunk in enumerate(chunks):
                        metadata = {
                            "title": title,
                            "category": category,
                            "date": str(date) if date else None,
                            **chunk["metadata"],
                        }

                        cur.execute(
                            """
                            INSERT INTO notion_chunks (page_id, chunk_index, chunk_text, metadata)
                            VALUES (%s, %s, %s, %s)
                        """,
                            (
                                page_id,
                                idx,
                                chunk["text"],
                                json.dumps(metadata, ensure_ascii=False),
                            ),
                        )

                    self.conn.commit()
                    logger.info(f"   ✅ {len(chunks)}개 청크 저장 완료")

                except Exception as e:
                    logger.error(f"   ❌ 오류: {e}")
                    self.conn.rollback()
                    continue

    def get_stats(self):
        """통계 출력"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    COUNT(*) as total_chunks,
                    COUNT(DISTINCT page_id) as total_pages,
                    AVG(LENGTH(chunk_text)) as avg_chunk_length,
                    MAX(LENGTH(chunk_text)) as max_chunk_length,
                    MIN(LENGTH(chunk_text)) as min_chunk_length
                FROM notion_chunks
            """
            )

            stats = cur.fetchone()
            print("\n" + "=" * 80)
            print("📊 청크 통계")
            print("=" * 80)
            print(f"전체 청크 수: {stats[0]:,}개")
            print(f"전체 페이지 수: {stats[1]:,}개")
            print(f"평균 청크 길이: {stats[2]:.0f}자")
            print(f"최대 청크 길이: {stats[3]:,}자")
            print(f"최소 청크 길이: {stats[4]:,}자")
            print("=" * 80)

    def close(self):
        """연결 종료"""
        self.conn.close()


def main():
    processor = NotionChunkProcessor()

    # 1. 테이블 생성
    processor.create_chunks_table()

    # 2. 모든 페이지 처리
    processor.process_all_pages()

    # 3. 통계 출력
    processor.get_stats()

    # 4. 연결 종료
    processor.close()

    print("\n✅ 모든 처리 완료!")


if __name__ == "__main__":
    main()
