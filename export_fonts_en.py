"""English launcher for TMP font export CLI."""

import logging
import sys

from export_fonts_core import main_cli

logger = logging.getLogger(__name__)


def main() -> None:
    """KR: 영어 추출기 CLI를 실행합니다.
    EN: Run the English exporter CLI entrypoint.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main_cli(lang="en")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logger.exception("An unexpected error occurred: %s", error)
        input("\nPress Enter to exit...")
        sys.exit(1)
