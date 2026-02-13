import sys

from export_fonts_core import main_cli


def main() -> None:
    """KR: 영어 추출기 CLI를 실행합니다.
    EN: Run the English exporter CLI entrypoint.
    """
    main_cli(lang="en")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        input("\nPress Enter to exit...")
        sys.exit(1)
