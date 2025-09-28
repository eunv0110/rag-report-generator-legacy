import os
import psycopg2
from notion_client import Client
from dotenv import load_dotenv
from datetime import datetime, timedelta
from contextlib import contextmanager
import logging

# =====================
# 로깅 설정
# =====================
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# =====================
# 환경 변수 및 설정
# =====================
load_dotenv()


class Config:
    NOTION_API_KEY = os.getenv("NOTION_API_KEY")
    NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

    # DB 설정
    DB_CONFIG = {
        "dbname": "mydb",
        "user": "hwangeunbi",
        "password": "",
        "host": "localhost",
        "port": "5432",
    }

    # 테이블 스키마 - 안전한 생성 (존재하지 않을 때만)
    TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS notion_pages (
        id SERIAL PRIMARY KEY,
        page_id TEXT UNIQUE,
        title TEXT,
        category TEXT,
        date DATE,
        content TEXT,
        created_time TIMESTAMP,
        last_edited_time TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    # 컬럼 추가 스키마 (기존 테이블에 새 컬럼이 없을 경우)
    ADD_COLUMNS_SCHEMA = [
        "ALTER TABLE notion_pages ADD COLUMN IF NOT EXISTS category TEXT;",
    ]

    @classmethod
    def validate(cls):
        if not cls.NOTION_API_KEY or not cls.NOTION_DATABASE_ID:
            raise ValueError(
                "❌ NOTION_API_KEY 또는 NOTION_DATABASE_ID 환경변수가 비어 있습니다!"
            )


# =====================
# 데이터베이스 관리 클래스
# =====================
class DatabaseManager:
    def __init__(self, config):
        self.config = config

    @contextmanager
    def get_connection(self):
        """데이터베이스 연결 컨텍스트 매니저"""
        conn = None
        try:
            conn = psycopg2.connect(**self.config)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"DB 연결 오류: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def create_table(self):
        """테이블 생성 및 스키마 업데이트"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 기본 테이블 생성 (존재하지 않을 때만)
                cur.execute(Config.TABLE_SCHEMA)

                # 추가 컬럼들 생성 (기존 테이블에 없을 경우)
                for add_column_sql in Config.ADD_COLUMNS_SCHEMA:
                    try:
                        cur.execute(add_column_sql)
                    except psycopg2.Error as e:
                        # 컬럼이 이미 존재하는 경우 등의 에러는 무시
                        logger.debug(f"컬럼 추가 스킵: {e}")

                conn.commit()
                logger.info("✅ notion_pages 테이블 준비 완료!")

    def upsert_page(self, conn, page_data):
        """페이지 데이터 삽입/업데이트"""
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notion_pages (page_id, title, category, date, content, created_time, last_edited_time)
                VALUES (%(page_id)s, %(title)s, %(category)s, %(date)s, %(content)s, %(created_time)s, %(last_edited_time)s)
                ON CONFLICT (page_id) DO UPDATE
                SET title = EXCLUDED.title,
                    category = EXCLUDED.category,
                    date = EXCLUDED.date,
                    content = EXCLUDED.content,
                    created_time = EXCLUDED.created_time,
                    last_edited_time = EXCLUDED.last_edited_time,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                page_data,
            )


# =====================
# Notion 데이터 처리 클래스
# =====================
class NotionProcessor:
    def __init__(self, api_key):
        self.notion = Client(auth=api_key)

    def get_text_from_block(self, block):
        """블록에서 텍스트 추출"""
        block_type = block["type"]
        texts = []

        if "rich_text" in block[block_type]:
            texts.extend([t["plain_text"] for t in block[block_type]["rich_text"]])

        # Heading은 강조 처리
        if block_type in ["heading_1", "heading_2", "heading_3"]:
            return "\n\n" + "".join(texts).upper() + "\n"
        else:
            return "".join(texts)

    def get_all_blocks(self, block_id):
        """모든 하위 블록 재귀적으로 가져오기"""
        try:
            blocks = self.notion.blocks.children.list(block_id=block_id)["results"]
            content_list = []

            for block in blocks:
                content_list.append(self.get_text_from_block(block))
                if block.get("has_children"):
                    content_list.extend(self.get_all_blocks(block["id"]))

            return content_list
        except Exception as e:
            logger.warning(f"블록 읽기 실패 ({block_id}): {e}")
            return []

    def query_recent_pages(self, database_id, days=7):
        """최근 N일 이내 생성/수정된 페이지 조회"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_iso = cutoff_date.isoformat()

        logger.info(
            f"📅 {cutoff_date.strftime('%Y-%m-%d')} 이후 생성되거나 수정된 페이지를 조회합니다."
        )

        try:
            # 시스템 프로퍼티를 사용한 필터링
            results = self.notion.databases.query(
                database_id=database_id,
                filter={
                    "or": [
                        {
                            "timestamp": "created_time",
                            "created_time": {"after": cutoff_iso},
                        },
                        {
                            "timestamp": "last_edited_time",
                            "last_edited_time": {"after": cutoff_iso},
                        },
                    ]
                },
                sorts=[{"timestamp": "last_edited_time", "direction": "descending"}],
            )["results"]

            logger.info(f"🔍 발견된 페이지: {len(results)}개")
            return results

        except Exception as e:
            logger.error(f"시간 기반 쿼리 실패: {e}")
            # 실패시 전체 페이지 조회로 폴백
            logger.info("📋 전체 페이지 조회로 전환합니다...")
            return self.query_all_pages(database_id)

    def query_all_pages(self, database_id):
        """모든 페이지 조회"""
        try:
            results = self.notion.databases.query(database_id=database_id)["results"]
            logger.info(f"🔍 전체 페이지: {len(results)}개")
            return results
        except Exception as e:
            logger.error(f"Notion 쿼리 실패: {e}")
            raise

    def extract_page_data(self, page):
        """페이지에서 데이터 추출"""
        page_id = page["id"]

        # 시스템 프로퍼티에서 시간 정보 추출
        created_time = page["created_time"]
        last_edited_time = page["last_edited_time"]

        # 제목 추출 (프로퍼티명: "이름")
        title = ""
        if "이름" in page["properties"] and page["properties"]["이름"]["title"]:
            title = page["properties"]["이름"]["title"][0]["plain_text"]

        # 카테고리 추출 (프로퍼티명: "유형")
        category = ""
        if "유형" in page["properties"] and page["properties"]["유형"]["select"]:
            category = page["properties"]["유형"]["select"]["name"]

        # 날짜 추출 (프로퍼티명: "날짜")
        date = None
        if "날짜" in page["properties"] and page["properties"]["날짜"]["date"]:
            date = page["properties"]["날짜"]["date"]["start"]

        # 내용 추출
        contents = self.get_all_blocks(page_id)
        content_text = "\n".join(c for c in contents if c.strip())

        return {
            "page_id": page_id,
            "title": title,
            "category": category,
            "date": date,
            "content": content_text,
            "created_time": created_time,
            "last_edited_time": last_edited_time,
        }


# =====================
# 메인 동기화 클래스
# =====================
class NotionSync:
    def __init__(self):
        Config.validate()
        self.db_manager = DatabaseManager(Config.DB_CONFIG)
        self.notion_processor = NotionProcessor(Config.NOTION_API_KEY)

    def reset_database(self):
        """데이터베이스 완전 초기화 (주의: 모든 데이터 삭제됨)"""
        logger.warning(
            "⚠️ 데이터베이스를 완전히 초기화합니다. 모든 데이터가 삭제됩니다!"
        )

        reset_schema = """
        DROP TABLE IF EXISTS notion_pages;
        CREATE TABLE notion_pages (
            id SERIAL PRIMARY KEY,
            page_id TEXT UNIQUE,
            title TEXT,
            category TEXT,
            date DATE,
            content TEXT,
            created_time TIMESTAMP,
            last_edited_time TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(reset_schema)
                conn.commit()
                logger.info("✅ 데이터베이스 초기화 완료!")

    def sync_recent_pages(self, days=7):
        """최근 N일 페이지 동기화"""
        logger.info("🚀 최근 페이지 동기화 시작...")

        # 테이블 준비 (안전한 방식)
        self.db_manager.create_table()

        # 페이지 조회
        pages = self.notion_processor.query_recent_pages(
            Config.NOTION_DATABASE_ID, days
        )

        # 데이터베이스에 저장
        self._save_pages(pages)

        logger.info("✅ 최근 페이지 동기화 완료!")

    def sync_all_pages(self):
        """전체 페이지 동기화"""
        logger.info("🚀 전체 페이지 동기화 시작...")

        # 테이블 준비 (안전한 방식)
        self.db_manager.create_table()

        # 페이지 조회
        pages = self.notion_processor.query_all_pages(Config.NOTION_DATABASE_ID)

        # 데이터베이스에 저장
        self._save_pages(pages)

        logger.info("✅ 전체 페이지 동기화 완료!")

    def _save_pages(self, pages):
        """페이지들을 데이터베이스에 저장"""
        with self.db_manager.get_connection() as conn:
            for page in pages:
                try:
                    # 페이지 데이터 추출
                    page_data = self.notion_processor.extract_page_data(page)

                    # 진행상황 출력
                    created_date = page_data["created_time"][:10]
                    edited_date = page_data["last_edited_time"][:10]
                    category = page_data["category"] or "미분류"

                    if created_date == edited_date:
                        logger.info(
                            f"➡️ 처리 중: [{category}] {page_data['title']} (생성: {created_date})"
                        )
                    else:
                        logger.info(
                            f"➡️ 처리 중: [{category}] {page_data['title']} (생성: {created_date}, 수정: {edited_date})"
                        )

                    # DB에 저장
                    self.db_manager.upsert_page(conn, page_data)
                    logger.info(f"   ✅ DB 반영 완료: {page_data['title']}")

                except Exception as e:
                    logger.error(f"페이지 처리 실패 ({page['id']}): {e}")
                    continue

            # 커밋
            conn.commit()


# =====================
# 실행 부분
# =====================
def main():
    """메인 실행 함수"""
    sync = NotionSync()

    # 사용법 예시:
    # 1. 최근 일주일 페이지만 동기화 (기본)
    # sync.sync_recent_pages(days=7)

    # 2. 전체 페이지 동기화 (필요시)
    # sync.sync_all_pages()

    # 3. 데이터베이스 완전 초기화 (주의: 모든 데이터 삭제)
    sync.reset_database()
    sync.sync_all_pages()


if __name__ == "__main__":
    main()
