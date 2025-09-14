import os
import psycopg2
from notion_client import Client
from dotenv import load_dotenv

# =====================
# 1. 환경 변수 로드
# =====================
load_dotenv()  # .env 파일 자동 로드

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

if not NOTION_API_KEY or not NOTION_DATABASE_ID:
    raise ValueError(
        "❌ NOTION_API_KEY 또는 NOTION_DATABASE_ID 환경변수가 비어 있습니다!"
    )

# =====================
# 2. Notion 연결
# =====================
notion = Client(auth=NOTION_API_KEY)

# =====================
# 3. PostgreSQL 연결
# =====================
conn = psycopg2.connect(
    dbname="mydb",
    user="hwangeunbi",  # DB owner
    password="",  # Mac은 기본 비움
    host="localhost",
    port="5432",
)
cur = conn.cursor()

# 테이블 없으면 생성
cur.execute(
    """
CREATE TABLE IF NOT EXISTS notion_pages (
    id SERIAL PRIMARY KEY,
    page_id TEXT UNIQUE,
    title TEXT,
    date DATE,
    content TEXT
);
"""
)
conn.commit()


# =====================
# 4. Notion 블록 파싱 함수
# =====================
def get_text_from_block(block):
    block_type = block["type"]
    texts = []
    if "rich_text" in block[block_type]:
        texts.extend([t["plain_text"] for t in block[block_type]["rich_text"]])

    if block_type in ["heading_1", "heading_2", "heading_3"]:
        texts = ["# " * int(block_type[-1]) + "".join(texts)]
    elif block_type in ["bulleted_list_item", "numbered_list_item"]:
        texts = ["- " + "".join(texts)]
    elif block_type == "to_do":
        checked = "✅" if block[block_type]["checked"] else "⬜"
        texts = [f"{checked} " + "".join(texts)]

    return "\n".join(texts)


def get_all_blocks(block_id):
    blocks = notion.blocks.children.list(block_id=block_id)["results"]
    content_list = []
    for block in blocks:
        content_list.append(get_text_from_block(block))
        if block.get("has_children"):
            content_list.extend(get_all_blocks(block["id"]))
    return content_list


# =====================
# 5. Notion → DB 적재
# =====================
results = notion.databases.query(database_id=NOTION_DATABASE_ID)["results"]

for page in results:
    page_id = page["id"]

    # 제목
    title = ""
    if page["properties"]["이름"]["title"]:
        title = page["properties"]["이름"]["title"][0]["plain_text"]

    # 날짜
    date = page["properties"]["날짜"]["date"]
    date = date["start"] if date else None

    # 내용
    contents = get_all_blocks(page_id)
    content_text = "\n".join(c for c in contents if c.strip())

    # DB insert (중복 방지)
    cur.execute(
        """
        INSERT INTO notion_pages (page_id, title, date, content)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (page_id) DO NOTHING;
    """,
        (page_id, title, date, content_text),
    )

conn.commit()
cur.close()
conn.close()

print("✅ Notion 데이터가 PostgreSQL에 적재 완료되었습니다!")
