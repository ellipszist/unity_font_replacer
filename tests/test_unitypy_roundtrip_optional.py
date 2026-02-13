import os

import pytest
import UnityPy


def test_unitypy_save_roundtrip_optional() -> None:
    """KR: UnityPy 저장 라운드트립이 안정적인지 선택적으로 검증합니다.
    EN: Optionally validate UnityPy save roundtrip stability.
    """
    sample_path = os.environ.get("UNITY_FONT_REPLACER_SAMPLE_ASSET")
    if not sample_path:
        pytest.skip("UNITY_FONT_REPLACER_SAMPLE_ASSET not set")

    env = UnityPy.load(sample_path)
    save1 = env.file.save()
    save2 = UnityPy.load(save1).file.save()
    assert save1 == save2
