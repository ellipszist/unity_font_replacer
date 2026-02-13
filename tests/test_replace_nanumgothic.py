import pytest

from tests._replace_integration_common import DEFAULT_GAME_PATHS, run_replace_and_assert


@pytest.mark.integration
@pytest.mark.nanumgothic
@pytest.mark.parametrize("game_path", DEFAULT_GAME_PATHS)
def test_replace_nanumgothic_on_real_games(game_path: str) -> None:
    """KR: NanumGothic 일괄 교체가 실제 게임에서 정상 동작하는지 검증합니다.
    EN: Verify NanumGothic bulk replacement on real game samples.
    """
    run_replace_and_assert(game_path, "--nanumgothic", "NanumGothic")
