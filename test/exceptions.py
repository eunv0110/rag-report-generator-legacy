# src/exceptions.py
class NotionAPIError(Exception):
    """Notion API 에러 클래스"""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Notion API Error {status_code}: {message}")


class NotionConfigError(Exception):
    """Notion 설정 에러 클래스"""

    pass
