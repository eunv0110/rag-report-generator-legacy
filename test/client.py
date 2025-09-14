# src/client.py
import json
import requests
from typing import Optional, List, Dict, Any

from test.config import APIConfig
from test.exceptions import NotionAPIError


class NotionClient:
    """개선된 Notion API 클라이언트"""

    def __init__(self, config: APIConfig):
        self.config = config
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Notion-Version": config.version,
            "Content-Type": "application/json",
        }

    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """HTTP 요청을 만들고 에러 처리"""
        try:
            response = getattr(requests, method.lower())(
                url, headers=self.headers, **kwargs
            )
        except requests.RequestException as e:
            raise NotionAPIError(0, f"네트워크 요청 실패: {str(e)}")

        if response.status_code // 100 == 2:
            return response.json()

        # 에러 처리
        try:
            error_data = response.json()
            message = error_data.get("message", response.text)
        except json.JSONDecodeError:
            message = response.text

        raise NotionAPIError(response.status_code, message)

    # ========== Database Methods ==========

    def get_database(self, database_id: Optional[str] = None) -> Dict[str, Any]:
        """데이터베이스 정보 조회"""
        db_id = database_id or self.config.database_id
        url = f"{self.base_url}/databases/{db_id}"
        return self._make_request("GET", url)

    def query_database(
        self,
        database_id: Optional[str] = None,
        filter_obj: Optional[Dict] = None,
        sorts: Optional[List[Dict]] = None,
        page_size: int = 100,
        start_cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """데이터베이스 쿼리 (단일 페이지)"""
        db_id = database_id or self.config.database_id
        url = f"{self.base_url}/databases/{db_id}/query"

        payload = {"page_size": min(page_size, 100)}  # API 제한: 최대 100
        if filter_obj:
            payload["filter"] = filter_obj
        if sorts:
            payload["sorts"] = sorts
        if start_cursor:
            payload["start_cursor"] = start_cursor

        return self._make_request("POST", url, json=payload)

    def query_database_all(
        self,
        database_id: Optional[str] = None,
        filter_obj: Optional[Dict] = None,
        sorts: Optional[List[Dict]] = None,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """데이터베이스의 모든 페이지 조회 (페이지네이션 처리)"""
        all_results = []
        cursor = None

        while True:
            data = self.query_database(
                database_id, filter_obj, sorts, page_size, cursor
            )
            all_results.extend(data["results"])

            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return all_results

    # ========== Page Methods ==========

    def get_page(self, page_id: str) -> Dict[str, Any]:
        """페이지 정보 조회"""
        url = f"{self.base_url}/pages/{page_id}"
        return self._make_request("GET", url)

    # ========== Block Methods ==========

    def get_block_children(
        self, block_id: str, start_cursor: Optional[str] = None, page_size: int = 100
    ) -> Dict[str, Any]:
        """블록의 자식 요소들 조회"""
        url = f"{self.base_url}/blocks/{block_id}/children"
        params = {"page_size": min(page_size, 100)}
        if start_cursor:
            params["start_cursor"] = start_cursor

        return self._make_request("GET", url, params=params)

    def get_page_content_flat(self, page_id: str) -> List[Dict[str, Any]]:
        """페이지의 최상위 블록들을 평면 리스트로 조회"""
        all_blocks = []
        cursor = None

        while True:
            data = self.get_block_children(page_id, start_cursor=cursor)
            all_blocks.extend(data["results"])

            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return all_blocks

    def get_block_tree(
        self, block_id: str, max_depth: int = 10, current_depth: int = 0
    ) -> List[Dict[str, Any]]:
        """블록 트리를 재귀적으로 조회 (깊이 제한 추가)"""
        if current_depth >= max_depth:
            return []

        children = []
        cursor = None

        while True:
            try:
                data = self.get_block_children(block_id, start_cursor=cursor)
            except NotionAPIError as e:
                print(f"블록 조회 실패 (ID: {block_id}): {e}")
                break

            for block in data["results"]:
                if block.get("has_children") and current_depth < max_depth - 1:
                    try:
                        block["children"] = self.get_block_tree(
                            block["id"], max_depth, current_depth + 1
                        )
                    except NotionAPIError as e:
                        print(f"자식 블록 조회 실패: {e}")
                        block["children"] = []
                children.append(block)

            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return children
