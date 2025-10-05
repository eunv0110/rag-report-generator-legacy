import os
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from dotenv import load_dotenv
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()


class DataExplorer:
    def __init__(self):
        self.db_config = {
            "dbname": "mydb",
            "user": "hwangeunbi",
            "password": "",
            "host": "localhost",
            "port": "5432",
        }

    def get_connection(self):
        """데이터베이스 연결"""
        try:
            conn = psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)
            return conn
        except Exception as e:
            logger.error(f"DB 연결 실패: {e}")
            raise

    def get_basic_stats(self):
        """기본 통계 정보"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 전체 레코드 수
                cur.execute("SELECT COUNT(*) as total_count FROM notion_pages;")
                total_count = cur.fetchone()["total_count"]

                # 카테고리별 분포
                cur.execute(
                    """
                    SELECT category, COUNT(*) as count 
                    FROM notion_pages 
                    GROUP BY category 
                    ORDER BY count DESC;
                """
                )
                category_stats = cur.fetchall()

                # 날짜 범위
                cur.execute(
                    """
                    SELECT 
                        MIN(created_time) as earliest_created,
                        MAX(created_time) as latest_created,
                        MIN(last_edited_time) as earliest_edited,
                        MAX(last_edited_time) as latest_edited
                    FROM notion_pages;
                """
                )
                date_stats = cur.fetchone()

                # 콘텐츠 길이 통계
                cur.execute(
                    """
                    SELECT 
                        AVG(LENGTH(content)) as avg_content_length,
                        MIN(LENGTH(content)) as min_content_length,
                        MAX(LENGTH(content)) as max_content_length,
                        COUNT(CASE WHEN content IS NULL OR content = '' THEN 1 END) as empty_content_count
                    FROM notion_pages;
                """
                )
                content_stats = cur.fetchone()

                return {
                    "total_count": total_count,
                    "category_stats": category_stats,
                    "date_stats": date_stats,
                    "content_stats": content_stats,
                }

    def get_sample_records(self, limit=5):
        """샘플 레코드 조회"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        id, page_id, title, category, date,
                        LEFT(content, 200) as content_preview,
                        LENGTH(content) as content_length,
                        created_time, last_edited_time
                    FROM notion_pages 
                    ORDER BY last_edited_time DESC
                    LIMIT %s;
                """,
                    (limit,),
                )
                return cur.fetchall()

    def get_content_examples_by_category(self):
        """카테고리별 콘텐츠 예시"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH ranked_pages AS (
                        SELECT 
                            category, title, 
                            LEFT(content, 300) as content_preview,
                            LENGTH(content) as content_length,
                            ROW_NUMBER() OVER (PARTITION BY category ORDER BY LENGTH(content) DESC) as rn
                        FROM notion_pages 
                        WHERE content IS NOT NULL AND content != ''
                    )
                    SELECT category, title, content_preview, content_length
                    FROM ranked_pages 
                    WHERE rn <= 2
                    ORDER BY category, content_length DESC;
                """
                )
                return cur.fetchall()

    def get_long_content_samples(self, min_length=1000):
        """긴 콘텐츠 샘플 (텍스트 분할 대상)"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        title, category,
                        LENGTH(content) as content_length,
                        LEFT(content, 500) as content_start,
                        RIGHT(content, 200) as content_end
                    FROM notion_pages 
                    WHERE LENGTH(content) > %s
                    ORDER BY LENGTH(content) DESC
                    LIMIT 5;
                """,
                    (min_length,),
                )
                return cur.fetchall()

    def analyze_content_structure(self):
        """콘텐츠 구조 분석 (마크다운 요소 등)"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        title,
                        CASE 
                            WHEN content LIKE '%#%' THEN 'has_headings'
                            ELSE 'no_headings'
                        END as has_headings,
                        CASE 
                            WHEN content LIKE '%```%' THEN 'has_code_blocks'
                            ELSE 'no_code_blocks'  
                        END as has_code_blocks,
                        CASE 
                            WHEN content LIKE '%-%' OR content LIKE '%*%' THEN 'has_lists'
                            ELSE 'no_lists'
                        END as has_lists,
                        LENGTH(content) as content_length
                    FROM notion_pages 
                    WHERE content IS NOT NULL AND content != ''
                    ORDER BY content_length DESC
                    LIMIT 10;
                """
                )
                return cur.fetchall()


def main():
    """데이터 탐색 실행"""
    explorer = DataExplorer()

    print("=" * 60)
    print("📊 NOTION 데이터베이스 탐색 결과")
    print("=" * 60)

    # 1. 기본 통계
    print("\n🔢 기본 통계:")
    stats = explorer.get_basic_stats()

    print(f"전체 페이지 수: {stats['total_count']:,}")
    print(f"평균 콘텐츠 길이: {stats['content_stats']['avg_content_length']:,.0f} 문자")
    print(f"최대 콘텐츠 길이: {stats['content_stats']['max_content_length']:,} 문자")
    print(f"최소 콘텐츠 길이: {stats['content_stats']['min_content_length']:,} 문자")
    print(f"빈 콘텐츠 수: {stats['content_stats']['empty_content_count']}")

    print(f"\n날짜 범위:")
    print(f"최초 생성: {stats['date_stats']['earliest_created']}")
    print(f"최근 생성: {stats['date_stats']['latest_created']}")
    print(f"최근 수정: {stats['date_stats']['latest_edited']}")

    # 2. 카테고리별 분포
    print(f"\n📁 카테고리별 분포:")
    for cat_stat in stats["category_stats"]:
        category = cat_stat["category"] or "미분류"
        print(f"  {category}: {cat_stat['count']}개")

    # 3. 샘플 레코드
    print(f"\n📄 최신 샘플 레코드 (5개):")
    samples = explorer.get_sample_records(5)
    for i, sample in enumerate(samples, 1):
        print(f"\n[{i}] {sample['title']}")
        print(f"    카테고리: {sample['category'] or '미분류'}")
        print(f"    콘텐츠 길이: {sample['content_length']:,} 문자")
        print(f"    미리보기: {sample['content_preview'][:100]}...")
        print(f"    생성일: {sample['created_time']}")

    # 4. 카테고리별 콘텐츠 예시
    print(f"\n📝 카테고리별 콘텐츠 예시:")
    category_examples = explorer.get_content_examples_by_category()
    current_category = None
    for example in category_examples:
        if example["category"] != current_category:
            current_category = example["category"] or "미분류"
            print(f"\n[{current_category}]")

        print(f"  제목: {example['title']}")
        print(f"  길이: {example['content_length']:,} 문자")
        print(f"  내용: {example['content_preview'][:150]}...")
        print()

    # 5. 긴 콘텐츠 분석 (텍스트 분할 대상)
    print(f"\n📚 긴 콘텐츠 분석 (1000자 이상):")
    long_contents = explorer.get_long_content_samples(1000)
    for i, content in enumerate(long_contents, 1):
        print(f"\n[{i}] {content['title']}")
        print(f"    카테고리: {content['category'] or '미분류'}")
        print(f"    길이: {content['content_length']:,} 문자")
        print(f"    시작: {content['content_start'][:100]}...")
        print(f"    끝: ...{content['content_end']}")

    # 6. 콘텐츠 구조 분석
    print(f"\n🏗️ 콘텐츠 구조 분석:")
    structure_analysis = explorer.analyze_content_structure()
    for analysis in structure_analysis:
        print(f"\n제목: {analysis['title']}")
        print(f"  길이: {analysis['content_length']:,} 문자")
        print(f"  헤딩 포함: {analysis['has_headings']}")
        print(f"  코드블록 포함: {analysis['has_code_blocks']}")
        print(f"  리스트 포함: {analysis['has_lists']}")


if __name__ == "__main__":
    main()
