from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from make_sdf import generate_sdf_assets_from_ttf


def test_generate_sdf_assets_from_ttf_returns_tmp_payload() -> None:
    """KR: TTF 기반 자동 SDF 생성이 TMP 호환 페이로드를 반환하는지 검증합니다.
    EN: Verify TTF-based auto SDF generation returns TMP-compatible payload.
    """
    repo_root = Path(__file__).resolve().parents[1]
    ttf_path = repo_root / "KR_ASSETS" / "Mulmaru.ttf"
    assert ttf_path.exists()

    ttf_data = ttf_path.read_bytes()
    generated = generate_sdf_assets_from_ttf(
        ttf_data=ttf_data,
        font_name="Mulmaru",
        unicodes=[9, 32, 65, 66, 67, 95],
        point_size=48,
        atlas_padding=5,
        atlas_width=256,
        atlas_height=256,
    )

    assert generated is not None
    sdf_data = generated["sdf_data"]
    atlas = generated["sdf_atlas"]

    assert atlas is not None
    assert atlas.mode == "RGBA"
    assert int(sdf_data["m_AtlasWidth"]) == 256
    assert int(sdf_data["m_AtlasHeight"]) == 256
    assert len(sdf_data["m_GlyphTable"]) == len(sdf_data["m_CharacterTable"])

    glyph_indices = {char["m_GlyphIndex"] for char in sdf_data["m_CharacterTable"]}
    assert len(glyph_indices) == len(sdf_data["m_CharacterTable"])

    y_bearings = [float(g["m_Metrics"]["m_HorizontalBearingY"]) for g in sdf_data["m_GlyphTable"]]
    assert max(y_bearings) > 0
    assert float(sdf_data["m_FaceInfo"]["m_CapLine"]) > 0
    assert float(sdf_data["m_FaceInfo"]["m_MeanLine"]) > 0

    alpha = atlas.getchannel("A")
    assert alpha.getbbox() is not None
