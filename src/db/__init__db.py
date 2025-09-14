import psycopg2

# DB 연결
conn = psycopg2.connect(
    dbname="mydb",
    user="hwangeunbi",
    password="",
    host="localhost",
    port="5432",
)
cur = conn.cursor()

# 테이블 생성 쿼리 실행
cur.execute(
    """
CREATE TABLE IF NOT EXISTS notion_pages (
    id SERIAL PRIMARY KEY,
    page_id TEXT UNIQUE,   -- Notion page 고유 ID
    title TEXT,
    date DATE,
    content TEXT
);
"""
)

# 저장 & 종료
conn.commit()
cur.close()
conn.close()

print("✅ notion_pages 테이블 생성 완료!")
