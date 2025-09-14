# src/models.py
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PageProperty:
    """페이지 속성 모델"""

    name: str
    type: str
    value: Any


@dataclass
class NotionPage:
    """Notion 페이지 모델"""

    id: str
    created_time: str
    url: str
    properties: Dict[str, Any]

    def get_title(self) -> str:
        """페이지 제목 반환"""
        for prop in self.properties.values():
            if prop.get("type") == "title" and prop.get("title"):
                return prop["title"][0]["plain_text"]
        return "제목 없음"


@dataclass
class NotionBlock:
    """Notion 블록 모델"""

    id: str
    type: str
    has_children: bool
    data: Dict[str, Any]
    children: Optional[List["NotionBlock"]] = None
