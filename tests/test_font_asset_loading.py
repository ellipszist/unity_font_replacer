import json
from pathlib import Path

from PIL import Image

import unity_font_replacer_core as core


def test_load_font_assets_cached_supports_raster_name_convention(tmp_path: Path) -> None:
    """KR: `Font Raster` 네이밍(`.json`, `Atlas.png`)을 로더가 인식하는지 검증합니다.
    EN: Verify loader supports `Font Raster` naming (`.json`, `Atlas.png`).
    """
    kr_assets = tmp_path / "KR_ASSETS"
    kr_assets.mkdir(parents=True, exist_ok=True)

    (kr_assets / "Mulmaru.ttf").write_bytes(b"dummy-ttf")
    (kr_assets / "Mulmaru Raster.json").write_text(
        json.dumps(
            {
                "m_FaceInfo": {"m_PointSize": 32},
                "m_GlyphTable": [],
                "m_CharacterTable": [],
                "m_AtlasWidth": 32,
                "m_AtlasHeight": 32,
                "m_AtlasPadding": 5,
            }
        ),
        encoding="utf-8",
    )
    Image.new("RGBA", (4, 4), (0, 0, 0, 255)).save(kr_assets / "Mulmaru Raster Atlas.png")
    (kr_assets / "Mulmaru Raster Material.json").write_text(
        json.dumps({"m_SavedProperties": {"m_Floats": []}}),
        encoding="utf-8",
    )

    core._load_font_assets_cached.cache_clear()
    try:
        loaded = core._load_font_assets_cached(str(tmp_path), "Mulmaru Raster")
    finally:
        core._load_font_assets_cached.cache_clear()

    assert loaded["ttf_data"] == b"dummy-ttf"
    assert isinstance(loaded["sdf_data"], dict)
    assert loaded["sdf_atlas"] is not None


def test_load_font_assets_cached_supports_plain_ngothic_name_set(tmp_path: Path) -> None:
    """KR: `NGothic.json / NGothic Atlas.png / NGothic Material.json` 세트를 인식하는지 검증합니다.
    EN: Verify loader supports `NGothic.json / NGothic Atlas.png / NGothic Material.json`.
    """
    kr_assets = tmp_path / "KR_ASSETS"
    kr_assets.mkdir(parents=True, exist_ok=True)

    (kr_assets / "NGothic.otf").write_bytes(b"dummy-otf")
    (kr_assets / "NGothic.json").write_text(
        json.dumps(
            {
                "m_FaceInfo": {"m_PointSize": 28},
                "m_GlyphTable": [],
                "m_CharacterTable": [],
                "m_AtlasWidth": 32,
                "m_AtlasHeight": 32,
                "m_AtlasPadding": 5,
            }
        ),
        encoding="utf-8",
    )
    Image.new("RGBA", (4, 4), (0, 0, 0, 255)).save(kr_assets / "NGothic Atlas.png")
    (kr_assets / "NGothic Material.json").write_text(
        json.dumps({"m_SavedProperties": {"m_Floats": []}}),
        encoding="utf-8",
    )

    core._load_font_assets_cached.cache_clear()
    original_get_script_dir = core.get_script_dir
    core.get_script_dir = lambda: str(tmp_path)
    try:
        loaded_by_plain = core.load_font_assets("NGothic")
        loaded_by_atlas_name = core.load_font_assets("NGothic Atlas.png")
        loaded_by_material_name = core.load_font_assets("NGothic Material.json")
    finally:
        core.get_script_dir = original_get_script_dir
        core._load_font_assets_cached.cache_clear()

    assert loaded_by_plain["ttf_data"] == b"dummy-otf"
    assert isinstance(loaded_by_plain["sdf_data"], dict)
    assert loaded_by_plain["sdf_atlas"] is not None

    assert loaded_by_atlas_name["ttf_data"] == b"dummy-otf"
    assert isinstance(loaded_by_atlas_name["sdf_data"], dict)
    assert loaded_by_atlas_name["sdf_atlas"] is not None

    assert loaded_by_material_name["ttf_data"] == b"dummy-otf"
    assert isinstance(loaded_by_material_name["sdf_data"], dict)
    assert loaded_by_material_name["sdf_atlas"] is not None
