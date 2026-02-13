import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_GAME_PATHS: list[str] = [
    r"D:\SteamLibrary\steamapps\common\Hookah Haze",
    r"D:\SteamLibrary\steamapps\common\Spice&Wolf VR2",
    r"D:\Games\SOUL COVENANT",
    r"D:\Games\SashinomiSuika",
]


def _parse_modified_count(output_text: str) -> int | None:
    """KR: 실행 로그에서 수정된 파일 수를 파싱합니다.
    EN: Parse modified file count from replacer output text.
    """
    match_ko = re.search(r"완료!\s*(\d+)개의 파일이 수정되었습니다", output_text)
    if match_ko:
        return int(match_ko.group(1))

    match_en = re.search(r"Done!\s*Modified\s*(\d+)\s*file", output_text)
    if match_en:
        return int(match_en.group(1))

    return None


def run_replace_and_assert(
    game_path: str,
    mode_arg: str,
    font_label: str,
    timeout_sec: int = 7200,
) -> None:
    """KR: 실제 게임 경로에서 교체기를 실행하고 정상 종료를 검증합니다.
    EN: Run replacer against a real game path and assert successful execution.
    """
    if not os.path.isdir(game_path):
        pytest.skip(f"Game path not found: {game_path}")

    cmd = [
        sys.executable,
        "unity_font_replacer.py",
        "--gamepath",
        game_path,
        mode_arg,
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        input="\n",
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout_sec,
    )

    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    modified_count = _parse_modified_count(output)
    tail = "\n".join([line for line in output.splitlines() if line.strip()][-40:])

    assert proc.returncode == 0, (
        f"{font_label} replacement failed for {game_path}\n"
        f"exit={proc.returncode}\n"
        f"{tail}"
    )
    assert modified_count is not None, (
        f"Could not parse modified file count for {font_label} on {game_path}\n"
        f"{tail}"
    )
