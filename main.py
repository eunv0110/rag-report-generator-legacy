from test.config import APIConfig
from test.client import NotionClient
from test.exceptions import NotionAPIError
from test.renderers import NotionBlockRenderer, NotionPageFormatter
from test.weekly_manager import WeeklyManager
from test.date_utils import DateUtils
from typing import Dict, Any
from test.ai_summarizer import ReportSummarizer
import os
from datetime import date


def print_database_summary(db_info: Dict[str, Any]) -> None:
    """데이터베이스 요약 정보 출력"""
    title = "제목 없음"
    if db_info.get("title"):
        title = db_info["title"][0]["plain_text"]

    print("=" * 60)
    print("📊 NOTION 데이터베이스 정보")
    print("=" * 60)
    print(f"제목: {title}")
    print(f"생성일: {db_info['created_time']}")
    print(f"ID: {db_info['id']}")
    print(f"URL: {db_info['url']}")

    # 속성 정보
    properties = db_info.get("properties", {})
    if properties:
        print(f"\n속성 목록 ({len(properties)}개):")
        for prop_name, prop_info in properties.items():
            prop_type = prop_info.get("type", "unknown")
            print(f"  • {prop_name} ({prop_type})")


def select_week_calculation_method():
    """주차 계산 방식 선택"""
    print("\n" + "=" * 60)
    print("📅 주차 계산 방식 선택")
    print("=" * 60)
    print("1. 프로젝트 기준 (권장) - 연속적인 주차 계산")
    print("2. 월별 기준 (기존) - 매월 1주차부터 시작")
    print("3. ISO 8601 기준 - 국제 표준 주차")

    while True:
        try:
            choice = input("\n선택하세요 (1-3, 기본값: 1): ").strip()

            if not choice:
                choice = "1"

            if choice == "1":
                return "project"
            elif choice == "2":
                return "monthly"
            elif choice == "3":
                return "iso"
            else:
                print("❌ 1, 2, 3 중에서 선택해주세요.")
        except KeyboardInterrupt:
            print("\n👋 프로그램을 종료합니다.")
            exit()


def configure_project_start_date():
    """프로젝트 시작일 설정 (프로젝트 기준 계산인 경우)"""
    print(f"\n현재 프로젝트 시작일: {DateUtils.PROJECT_START_DATE}")

    while True:
        try:
            user_input = (
                input("프로젝트 시작일을 변경하시겠습니까? (y/N): ").strip().lower()
            )

            if user_input in ["", "n", "no"]:
                break
            elif user_input in ["y", "yes"]:
                date_input = input("새로운 시작일을 입력하세요 (YYYY-MM-DD): ").strip()
                try:
                    new_start_date = date.fromisoformat(date_input)
                    DateUtils.set_project_start_date(new_start_date)
                    print(f"✅ 프로젝트 시작일이 {new_start_date}로 설정되었습니다.")
                    break
                except ValueError:
                    print("❌ 올바른 날짜 형식을 입력해주세요 (YYYY-MM-DD)")
            else:
                print("❌ y 또는 n을 입력해주세요.")
        except KeyboardInterrupt:
            print("\n👋 프로그램을 종료합니다.")
            exit()


def interactive_week_selection(weekly_manager: WeeklyManager):
    """대화형 주차 선택"""
    available_weeks = weekly_manager.get_available_weeks()

    if not available_weeks:
        print("📭 선택할 수 있는 주차가 없습니다.")
        return

    # 현재 주차 계산 방식 정보 출력
    weekly_manager.print_calculation_method_info()
    print(f"\n💡 사용 가능한 주차: {', '.join(map(str, available_weeks))}주차")

    while True:
        try:
            print("\n" + "=" * 50)
            print("🎯 작업 선택")
            print("=" * 50)
            print("1. 주차별 상세 내용 보기")
            print("2. 주차별 AI 요약")
            print("3. 주차별 보고서 생성")
            print("4. 주차 계산 방식 변경")
            print("q. 종료")

            action = input("\n원하는 작업을 선택하세요: ").strip()

            if action.lower() == "q":
                print("👋 프로그램을 종료합니다.")
                break
            elif action == "4":
                # 주차 계산 방식 변경
                new_method = select_week_calculation_method()
                weekly_manager.set_week_calculation_method(new_method)

                # 프로젝트 기준인 경우 시작일 설정
                if new_method == "project":
                    configure_project_start_date()

                # 페이지 재분석
                print("\n🔄 페이지를 다시 분석하는 중...")
                # 여기서는 pages를 다시 가져와야 하지만,
                # 간단히 하기 위해 사용자에게 프로그램 재시작을 권장
                print("⚠️  주차 계산 방식이 변경되었습니다.")
                print("🔄 변경사항을 적용하려면 프로그램을 다시 시작해주세요.")
                continue
            elif action in ["1", "2", "3"]:
                week_input = input(
                    f"\n작업할 주차를 입력하세요 (사용 가능: {', '.join(map(str, available_weeks))}주차): "
                ).strip()

                try:
                    week_num = int(week_input)

                    if week_num not in available_weeks:
                        print(f"❌ {week_num}주차는 존재하지 않습니다.")
                        continue

                    if action == "1":
                        # 상세 내용 보기
                        weekly_manager.print_week_details(week_num)

                    elif action == "2":
                        # AI 요약
                        print("\n📝 요약 타입 선택:")
                        print("1. weekly (주간 요약)")
                        print("2. problem (문제점 분석)")
                        print("3. thoughts (생각/느낌)")
                        print("4. plan (계획/목표)")

                        summary_choice = input(
                            "요약 타입을 선택하세요 (1-4, 기본값: 1): "
                        ).strip()

                        summary_types = {
                            "1": "weekly",
                            "2": "problem",
                            "3": "thoughts",
                            "4": "plan",
                        }
                        summary_type = summary_types.get(summary_choice, "weekly")

                        weekly_manager.summarize_week(week_num, summary_type)

                    elif action == "3":
                        # 보고서 생성
                        report_week_input = input(
                            f"생성할 보고서의 주차를 입력해주세요 (기본값: {week_num}): "
                        ).strip()
                        report_week = (
                            int(report_week_input) if report_week_input else week_num
                        )

                        if weekly_manager.summarizer:
                            report_paths = weekly_manager.generate_week_report(
                                week_num, report_week
                            )

                            if report_paths:
                                print(f"\n📁 생성된 파일:")
                                if report_paths.get("word"):
                                    print(f"  📄 Word: {report_paths['word']}")
                                if report_paths.get("pdf"):
                                    print(f"  📄 PDF: {report_paths['pdf']}")
                        else:
                            print("❌ AI 요약기가 설정되지 않았습니다.")

                except ValueError:
                    print("❌ 올바른 숫자를 입력해주세요.")
            else:
                print("❌ 올바른 선택지를 입력해주세요.")

        except KeyboardInterrupt:
            print("\n\n👋 프로그램을 종료합니다.")
            break


def main():
    """메인 함수"""
    try:
        print("🚀 Notion API 클라이언트 시작")

        # 주차 계산 방식 선택
        week_method = select_week_calculation_method()

        # 프로젝트 기준인 경우 시작일 설정
        if week_method == "project":
            configure_project_start_date()

        # 설정 로드
        config = APIConfig.from_env()
        client = NotionClient(config)

        # AI 요약기 설정 (OpenAI API 키가 있는 경우에만)
        summarizer = None
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            try:
                summarizer = ReportSummarizer(openai_api_key)
                print("✅ AI 요약기가 설정되었습니다.")
            except Exception as e:
                print(f"⚠️  AI 요약기 설정 실패: {e}")
        else:
            print(
                "⚠️  OPENAI_API_KEY가 설정되지 않았습니다. AI 요약 기능을 사용할 수 없습니다."
            )

        # 데이터베이스 정보 조회
        print("\n📥 데이터베이스 정보를 가져오는 중...")
        db_info = client.get_database()
        print_database_summary(db_info)

        # 모든 페이지 조회
        print("\n📋 데이터베이스 페이지 쿼리 중...")
        pages = client.query_database_all()
        print(f"✅ 총 {len(pages)}개의 페이지를 찾았습니다.")

        if not pages:
            print("📭 페이지가 없습니다.")
            return

        # 주차별 분석 (선택된 계산 방식으로)
        print(f"\n🗓️  페이지를 주차별로 분석 중... ({week_method} 방식)")
        weekly_manager = WeeklyManager(client, summarizer, week_method)
        weekly_pages = weekly_manager.analyze_pages_by_week(pages)

        # 주차별 요약 출력
        weekly_manager.print_weekly_summary()

        # 대화형 주차 선택
        interactive_week_selection(weekly_manager)

    except NotionAPIError as e:
        print(f"❌ Notion API 에러: {e}")
    except ValueError as e:
        print(f"❌ 설정 에러: {e}")
    except Exception as e:
        print(f"❌ 예상치 못한 에러: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
