import pytest

from tests._replace_integration_common import DEFAULT_GAME_PATHS, run_replace_and_assert


@pytest.mark.integration
@pytest.mark.mulmaru
@pytest.mark.parametrize("game_path", DEFAULT_GAME_PATHS)
def test_replace_mulmaru_on_real_games(game_path: str) -> None:
    """KR: Mulmaru 일괄 교체가 실제 게임에서 정상 동작하는지 검증합니다.
    EN: Verify Mulmaru bulk replacement on real game samples.
    """
    run_replace_and_assert(game_path, "--mulmaru", "Mulmaru")
