# src/renderers.py
from typing import Dict, List, Any, Optional


class NotionBlockRenderer:
    """Notion 블록을 텍스트로 렌더링하는 유틸리티 클래스"""

    HEADING_PREFIXES = {"heading_1": "# ", "heading_2": "## ", "heading_3": "### "}

    @staticmethod
    def extract_rich_text(rich_text: List[Dict[str, Any]]) -> str:
        """Rich text에서 plain text 추출"""
        return "".join(r.get("plain_text", "") for r in rich_text)

    @staticmethod
    def block_to_text(block: Dict[str, Any]) -> str:
        """블록을 plain text로 변환"""
        block_type = block.get("type")
        if not block_type:
            return ""

        data = block.get(block_type, {})
        rich_text = data.get("rich_text", [])
        text = NotionBlockRenderer.extract_rich_text(rich_text)

        # 헤딩 처리
        if block_type in NotionBlockRenderer.HEADING_PREFIXES:
            return NotionBlockRenderer.HEADING_PREFIXES[block_type] + text

        # To-do 리스트 처리
        elif block_type == "to_do":
            checked = data.get("checked", False)
            return f"[{'x' if checked else ' '}] {text}"

        # 리스트 처리
        elif block_type == "bulleted_list_item":
            return f"- {text}"
        elif block_type == "numbered_list_item":
            return f"1. {text}"

        # 코드 블록 처리
        elif block_type == "code":
            language = data.get("language", "")
            return f"```{language}\n{text}\n```"

        # 인용문 처리
        elif block_type == "quote":
            return f"> {text}"

        # 구분선 처리
        elif block_type == "divider":
            return "---"

        # 기본 텍스트 (paragraph 등)
        return text

    @staticmethod
    def render_blocks(blocks: List[Dict[str, Any]], indent: int = 0) -> str:
        """블록 트리를 문자열로 렌더링 (출력 대신 반환)"""
        result = []
        for block in blocks:
            line = NotionBlockRenderer.block_to_text(block)
            if line.strip():
                result.append(" " * indent + line)

            # 자식 블록 재귀 렌더링
            children = block.get("children", [])
            if children:
                child_content = NotionBlockRenderer.render_blocks(children, indent + 2)
                if child_content:
                    result.append(child_content)

        return "\n".join(result)


class NotionPageFormatter:
    """페이지 정보를 포맷팅하는 유틸리티 클래스"""

    @staticmethod
    def format_property_value(prop: Dict[str, Any]) -> str:
        """속성 값을 문자열로 포맷"""
        prop_type = prop.get("type")

        if prop_type == "title" and prop.get("title"):
            return prop["title"][0]["plain_text"]
        elif prop_type == "rich_text" and prop.get("rich_text"):
            return NotionBlockRenderer.extract_rich_text(prop["rich_text"])
        elif prop_type == "select" and prop.get("select"):
            return prop["select"]["name"]
        elif prop_type == "multi_select" and prop.get("multi_select"):
            return ", ".join(v["name"] for v in prop["multi_select"])
        elif prop_type == "date" and prop.get("date"):
            date_info = prop["date"]
            end_date = f" ~ {date_info.get('end')}" if date_info.get("end") else ""
            return f"{date_info['start']}{end_date}"
        elif prop_type == "number" and prop.get("number") is not None:
            return str(prop["number"])
        elif prop_type == "checkbox":
            return "✓" if prop.get("checkbox") else "✗"
        elif prop_type == "url" and prop.get("url"):
            return prop["url"]
        elif prop_type == "email" and prop.get("email"):
            return prop["email"]
        elif prop_type == "phone_number" and prop.get("phone_number"):
            return prop["phone_number"]

        return ""

    @staticmethod
    def get_page_date(properties: Dict[str, Any]) -> Optional[str]:
        """페이지에서 날짜 속성 찾기"""
        for prop_name, prop in properties.items():
            if prop.get("type") == "date" and prop.get("date"):
                return prop["date"]["start"]
        return None

    @staticmethod
    def format_page_properties(properties: Dict[str, Any]) -> Dict[str, str]:
        """페이지 속성을 읽기 쉬운 형태로 포맷"""
        formatted = {}

        for prop_name, prop in properties.items():
            value = NotionPageFormatter.format_property_value(prop)
            if value:
                display_name = "제목" if prop.get("type") == "title" else prop_name
                formatted[display_name] = value

        return formatted

    @staticmethod
    def print_page_info(page: Dict[str, Any], page_number: int) -> None:
        """페이지 정보를 콘솔에 출력"""
        print(f"\n{'='*50}")
        print(f"페이지 {page_number}")
        print(f"{'='*50}")
        print(f"ID: {page['id']}")
        print(f"생성일: {page['created_time']}")
        print(f"수정일: {page.get('last_edited_time', 'N/A')}")
        print(f"URL: {page['url']}")
        print("-" * 50)

        # 속성 출력
        formatted_props = NotionPageFormatter.format_page_properties(page["properties"])
        if formatted_props:
            print("속성:")
            for key, value in formatted_props.items():
                print(f"  {key}: {value}")
        else:
            print("속성: 없음")
