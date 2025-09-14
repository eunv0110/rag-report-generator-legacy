# src/date_utils.py
from datetime import datetime, date, timedelta
from typing import Optional
import calendar


class DateUtils:
    """날짜 관련 유틸리티 클래스"""

    # 프로젝트 시작일 설정 (2025년 7월 1일을 1주차 시작으로 가정)
    PROJECT_START_DATE = date(2025, 7, 1)  # 실제 프로젝트 시작일로 수정하세요

    @staticmethod
    def parse_notion_date(date_str: str) -> Optional[date]:
        """Notion 날짜 문자열을 파싱"""
        if not date_str:
            return None
        try:
            # "2025-08-01" 형식
            return datetime.strptime(date_str.split("T")[0], "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def get_week_number_monthly(target_date: date) -> int:
        """해당 월에서 몇 주차인지 계산 (기존 방식 - 월별)"""
        # 해당 월의 첫 번째 날
        first_day = target_date.replace(day=1)

        # 첫 번째 월요일 찾기
        first_monday = first_day
        while first_monday.weekday() != 0:  # 0 = 월요일
            first_monday = first_monday.replace(day=first_monday.day + 1)
            if first_monday.month != target_date.month:
                # 첫 번째 월요일이 다음 달로 넘어간 경우
                first_monday = first_day
                break

        # 타겟 날짜가 첫 번째 월요일보다 이전인 경우 1주차
        if target_date < first_monday:
            return 1

        # 주차 계산
        days_diff = (target_date - first_monday).days
        return (days_diff // 7) + 1

    @staticmethod
    def get_week_number_project_based(target_date: date) -> int:
        """프로젝트 시작일 기준 주차 계산 (연속 주차)"""
        if target_date < DateUtils.PROJECT_START_DATE:
            return 0

        # 프로젝트 시작일 기준 경과 일수
        days_diff = (target_date - DateUtils.PROJECT_START_DATE).days

        # 주차 계산 (1주차부터 시작)
        week_number = (days_diff // 7) + 1

        return week_number

    @staticmethod
    def get_week_number_iso(target_date: date) -> tuple[int, int]:
        """ISO 8601 기준 주차 (년도, 주차 반환)"""
        iso_year, iso_week, _ = target_date.isocalendar()
        return iso_year, iso_week

    @staticmethod
    def get_monday_of_week(target_date: date) -> date:
        """해당 주의 월요일 날짜 반환"""
        days_since_monday = target_date.weekday()
        monday = target_date - timedelta(days=days_since_monday)
        return monday

    @staticmethod
    def get_week_range(target_date: date) -> tuple[date, date]:
        """해당 주의 월요일~일요일 범위 반환"""
        monday = DateUtils.get_monday_of_week(target_date)
        sunday = monday + timedelta(days=6)
        return monday, sunday

    @staticmethod
    def format_korean_date(target_date: date) -> str:
        """한국어 날짜 형식으로 포맷 (예: "8월 1일")"""
        return f"{target_date.month}월 {target_date.day}일"

    @staticmethod
    def format_korean_date_with_weekday(target_date: date) -> str:
        """한국어 날짜 + 요일 형식 (예: "8월 1일 (월)")"""
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        weekday = weekdays[target_date.weekday()]
        return f"{target_date.month}월 {target_date.day}일 ({weekday})"

    @staticmethod
    def get_date_info(
        date_str: str, week_calculation_method: str = "project"
    ) -> tuple[str, int]:
        """
        날짜 문자열을 받아서 "몇월 몇일, 몇주차" 정보 반환

        Args:
            date_str: Notion 날짜 문자열
            week_calculation_method: "project" (프로젝트 기준) | "monthly" (월별) | "iso" (ISO 8601)
        """
        parsed_date = DateUtils.parse_notion_date(date_str)
        if not parsed_date:
            return "날짜 없음", 0

        korean_date = DateUtils.format_korean_date_with_weekday(parsed_date)

        if week_calculation_method == "monthly":
            week_num = DateUtils.get_week_number_monthly(parsed_date)
        elif week_calculation_method == "iso":
            _, week_num = DateUtils.get_week_number_iso(parsed_date)
        else:  # "project" (기본값)
            week_num = DateUtils.get_week_number_project_based(parsed_date)

        return korean_date, week_num

    @staticmethod
    def get_week_summary(week_number: int) -> dict:
        """주차 정보 요약 반환"""
        if week_number <= 0:
            return {
                "week_number": week_number,
                "start_date": None,
                "end_date": None,
                "korean_range": "유효하지 않은 주차",
            }

        # 해당 주차의 시작일 계산
        week_start = DateUtils.PROJECT_START_DATE + timedelta(weeks=week_number - 1)
        week_end = week_start + timedelta(days=6)

        korean_range = f"{DateUtils.format_korean_date(week_start)} ~ {DateUtils.format_korean_date(week_end)}"

        return {
            "week_number": week_number,
            "start_date": week_start,
            "end_date": week_end,
            "korean_range": korean_range,
        }

    @staticmethod
    def set_project_start_date(start_date: date):
        """프로젝트 시작일 설정"""
        DateUtils.PROJECT_START_DATE = start_date

    @staticmethod
    def get_current_project_week() -> int:
        """현재 날짜 기준 프로젝트 주차 반환"""
        today = date.today()
        return DateUtils.get_week_number_project_based(today)


# 사용 예시
if __name__ == "__main__":
    # 테스트용 날짜들
    test_dates = [
        "2025-07-01",  # 프로젝트 시작일
        "2025-07-07",  # 1주차 마지막
        "2025-07-08",  # 2주차 시작
        "2025-08-01",  # 8월 첫날
        "2025-08-15",  # 8월 중순
    ]

    print("=== 주차 계산 방식 비교 ===")
    for date_str in test_dates:
        print(f"\n날짜: {date_str}")

        # 월별 계산
        korean_date, monthly_week = DateUtils.get_date_info(date_str, "monthly")
        print(f"  월별: {korean_date} - {monthly_week}주차")

        # 프로젝트 기준 계산
        korean_date, project_week = DateUtils.get_date_info(date_str, "project")
        print(f"  프로젝트: {korean_date} - {project_week}주차")

        # 주차 요약
        week_summary = DateUtils.get_week_summary(project_week)
        print(f"  범위: {week_summary['korean_range']}")
