# src/config.py
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class APIConfig:
    """API 설정 클래스"""

    api_key: str
    database_id: str
    version: str

    @classmethod
    def from_env(cls) -> "APIConfig":
        """환경변수에서 설정을 로드"""
        api_key = os.getenv("NOTION_API_KEY")
        database_id = os.getenv("NOTION_DATABASE_ID")
        version = os.getenv("NOTION_VERSION", "2022-06-28")
        openai_api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("NOTION_API_KEY 환경변수가 설정되지 않았습니다.")
        if not database_id:
            raise ValueError("NOTION_DATABASE_ID 환경변수가 설정되지 않았습니다.")

        return cls(api_key=api_key, database_id=database_id, version=version)
