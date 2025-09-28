import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

# DB 연결
conn = psycopg2.connect(
    dbname="mydb", user="hwangeunbi", password="", host="localhost", port="5432"
)

cursor = conn.cursor()

# 특정 페이지 내용 조회
page_title = "공공AX프로젝트_데이터리서치"

cursor.execute(
    """
    SELECT title, category, date, content, 
           created_time, last_edited_time,
           LENGTH(content) as content_length
    FROM notion_pages 
    WHERE title = %s
""",
    (page_title,),
)

result = cursor.fetchone()

if result:
    title, category, date, content, created, edited, content_len = result

    print("=" * 80)
    print(f"📄 제목: {title}")
    print(f"📂 카테고리: {category}")
    print(f"📅 날짜: {date}")
    print(f"📝 내용 길이: {content_len:,}자")
    print(f"🕐 생성: {created}")
    print(f"✏️ 수정: {edited}")
    print("=" * 80)
    print("\n📋 전체 내용:")
    print("-" * 80)
    print(content)
    print("-" * 80)

else:
    print(f"❌ '{page_title}' 페이지를 찾을 수 없습니다.")

conn.close()
