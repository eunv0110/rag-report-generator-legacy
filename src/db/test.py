import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    dbname="mydb", user="hwangeunbi", password="", host="localhost", port="5432"
)

cursor = conn.cursor()

# 1. 특정 페이지의 청크들 보기
page_title = "공공AX프로젝트_데이터리서치"

cursor.execute(
    """
    SELECT chunk_index, chunk_text, metadata
    FROM notion_chunks
    WHERE metadata->>'title' = %s
    ORDER BY chunk_index
""",
    (page_title,),
)

chunks = cursor.fetchall()

print("=" * 80)
print(f"📄 '{page_title}' 페이지의 청크들 ({len(chunks)}개)")
print("=" * 80)

for idx, text, metadata in chunks[:5]:  # 처음 5개만 출력
    # PostgreSQL JSONB는 이미 dict로 반환됨
    print(f"\n[청크 {idx}]")
    print(f"카테고리: {metadata.get('category', 'N/A')}")
    if "섹션" in metadata:
        print(f"섹션: {metadata['섹션']}")
    if "하위섹션" in metadata:
        print(f"하위섹션: {metadata['하위섹션']}")
    print(f"텍스트 ({len(text)}자):")
    print("-" * 40)
    print(text[:200] + "..." if len(text) > 200 else text)
    print("-" * 40)

print(f"\n... (총 {len(chunks)}개 중 5개만 표시)")

# 2. 전체 통계
cursor.execute(
    """
    SELECT 
        metadata->>'title' as title,
        COUNT(*) as chunk_count,
        AVG(LENGTH(chunk_text)) as avg_length
    FROM notion_chunks
    GROUP BY metadata->>'title'
    ORDER BY chunk_count DESC
    LIMIT 10
"""
)

stats = cursor.fetchall()

print("\n" + "=" * 80)
print("📊 페이지별 청크 수 (상위 10개)")
print("=" * 80)
for title, count, avg_len in stats:
    print(f"{title[:40]:40} | {count:3}개 청크 | 평균 {avg_len:.0f}자")

conn.close()
