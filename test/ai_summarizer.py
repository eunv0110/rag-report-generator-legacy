# src/ai_summerizer.py
import requests
import json
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from langchain_core.prompts import load_prompt


class AISummarizer(ABC):
    @abstractmethod
    def summarize(self, content: str, format_instruction: str = "") -> str:
        pass


class ReportSummarizer(AISummarizer):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # 프롬프트 파일 경로 매핑
        self.prompt_files = {
            "weekly": "prompts/weekly_summary.yaml",
            "problem": "prompts/problem_summary.yaml",
            "thoughts": "prompts/thoughts_summary.yaml",
            "plan": "prompts/plan_summary.yaml",
        }

    def _make_request(
        self, formatted_prompt: str, max_tokens: int = 1000, temperature: float = 0.3
    ) -> str:
        """공통 API 요청 처리"""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": formatted_prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = requests.post(self.base_url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            return f"❌ 네트워크 요청 실패: {str(e)}"
        except (KeyError, IndexError) as e:
            return f"❌ API 응답 파싱 실패: {str(e)}"
        except Exception as e:
            return f"❌ GPT API 에러: {str(e)}"

    def _get_summary(
        self, content: str, summary_type: str, format_instruction: str = ""
    ) -> str:
        """공통 요약 처리 로직"""
        if not content.strip():
            return "요약할 내용이 없습니다."

        if summary_type not in self.prompt_files:
            return f"❌ 지원하지 않는 요약 타입: {summary_type}"

        try:
            prompt = load_prompt(self.prompt_files[summary_type])
            formatted_prompt = prompt.format(
                content=content, format_instruction=format_instruction
            )
            return self._make_request(formatted_prompt)
        except FileNotFoundError:
            return f"❌ 프롬프트 파일을 찾을 수 없습니다: {self.prompt_files[summary_type]}"
        except Exception as e:
            return f"❌ 프롬프트 처리 에러: {str(e)}"

    def summarize(self, content: str, format_instruction: str = "") -> str:
        """기본 요약 (주간 요약과 동일)"""
        return self.weekly_summarize(content, format_instruction)

    def weekly_summarize(self, content: str, format_instruction: str = "") -> str:
        """주간 보고서 요약"""
        return self._get_summary(content, "weekly", format_instruction)

    def problem_summarize(self, content: str, format_instruction: str = "") -> str:
        """문제점 분석 요약"""
        return self._get_summary(content, "problem", format_instruction)

    def thoughts_summarize(self, content: str, format_instruction: str = "") -> str:
        """생각 정리 요약"""
        return self._get_summary(content, "thoughts", format_instruction)

    def plan_summarize(self, content: str, format_instruction: str = "") -> str:
        """계획 요약"""
        return self._get_summary(content, "plan", format_instruction)

    def custom_summarize(
        self, content: str, prompt_file_path: str, format_instruction: str = ""
    ) -> str:
        """커스텀 프롬프트를 사용한 요약"""
        if not content.strip():
            return "요약할 내용이 없습니다."

        try:
            prompt = load_prompt(prompt_file_path)
            formatted_prompt = prompt.format(
                content=content, format_instruction=format_instruction
            )
            return self._make_request(formatted_prompt)
        except FileNotFoundError:
            return f"❌ 프롬프트 파일을 찾을 수 없습니다: {prompt_file_path}"
        except Exception as e:
            return f"❌ 커스텀 요약 에러: {str(e)}"

    def get_available_summary_types(self) -> list:
        """사용 가능한 요약 타입 목록 반환"""
        return list(self.prompt_files.keys())

    def set_model(self, model: str) -> None:
        """모델 변경"""
        self.model = model

    def add_prompt_type(self, type_name: str, prompt_file_path: str) -> None:
        """새로운 요약 타입 추가"""
        self.prompt_files[type_name] = prompt_file_path
