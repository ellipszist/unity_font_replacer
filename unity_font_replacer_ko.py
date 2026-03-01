"""Korean launcher for Unity Font Replacer CLI."""

import logging

from unity_font_replacer_core import run_main_ko

logger = logging.getLogger(__name__)


def main() -> None:
    """Run Korean CLI entrypoint."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_main_ko()


if __name__ == "__main__":
    main()
