"""Korean launcher for TMP font export CLI."""

import logging
import sys

from export_fonts_core import main_cli

logger = logging.getLogger(__name__)


def main() -> None:
    """KR: 한국어 추출기 CLI를 실행합니다.
    EN: Run the Korean exporter CLI entrypoint.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main_cli(lang="ko")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logger.exception("예상치 못한 오류가 발생했습니다: %s", error)
        input("\n엔터를 눌러 종료...")
        sys.exit(1)
