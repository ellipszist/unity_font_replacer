import sys

from export_fonts_core import main_cli


def main() -> None:
    """KR: 한국어 추출기 CLI를 실행합니다.
    EN: Run the Korean exporter CLI entrypoint.
    """
    main_cli(lang="ko")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n예상치 못한 오류가 발생했습니다: {e}")
        input("\n엔터를 눌러 종료...")
        sys.exit(1)
