from pathlib import Path
import json
import shutil

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from make_sdf import run_make_sdf


def test_make_sdf_cli_generates_outputs(tmp_path: Path) -> None:
    """KR: make_sdf CLI가 TTF에서 JSON/Atlas를 생성하는지 검증합니다.
    EN: Verify make_sdf CLI generates JSON/atlas from TTF.
    """
    repo_root = Path(__file__).resolve().parents[1]
    source_ttf = repo_root / "KR_ASSETS" / "Mulmaru.ttf"
    assert source_ttf.exists()

    target_ttf = tmp_path / "Mulmaru.ttf"
    shutil.copy2(source_ttf, target_ttf)

    exit_code = run_make_sdf(
        [
            "--ttf",
            str(target_ttf),
            "--atlas-size",
            "256,256",
            "--point-size",
            "32",
            "--padding",
            "5",
            "--charset",
            "ABC가나다",
            "--rendermode",
            "sdf",
        ]
    )
    assert exit_code == 0

    json_path = tmp_path / "Mulmaru SDF.json"
    atlas_path = tmp_path / "Mulmaru SDF Atlas.png"
    material_path = tmp_path / "Mulmaru SDF Material.json"

    assert json_path.exists()
    assert atlas_path.exists()
    assert material_path.exists()
    with open(json_path, "r", encoding="utf-8") as f:
        sdf_data = json.load(f)
    assert int(sdf_data["m_AtlasWidth"]) == 256
    assert int(sdf_data["m_AtlasHeight"]) == 256


def test_make_sdf_cli_raster_auto_mode(tmp_path: Path) -> None:
    """KR: make_sdf CLI의 raster/auto 옵션이 동작하는지 검증합니다.
    EN: Verify raster/auto options in make_sdf CLI.
    """
    repo_root = Path(__file__).resolve().parents[1]
    source_ttf = repo_root / "KR_ASSETS" / "Mulmaru.ttf"
    assert source_ttf.exists()

    target_ttf = tmp_path / "Mulmaru.ttf"
    shutil.copy2(source_ttf, target_ttf)

    exit_code = run_make_sdf(
        [
            "--ttf",
            str(target_ttf),
            "--atlas-size",
            "256,256",
            "--point-size",
            "auto",
            "--padding",
            "7",
            "--charset",
            "ABC",
            "--rendermode",
            "raster",
        ]
    )
    assert exit_code == 0

    json_path = tmp_path / "Mulmaru Raster.json"
    atlas_path = tmp_path / "Mulmaru Raster Atlas.png"
    material_path = tmp_path / "Mulmaru Raster Material.json"

    assert json_path.exists()
    assert atlas_path.exists()
    assert material_path.exists()
    with open(json_path, "r", encoding="utf-8") as f:
        sdf_data = json.load(f)
    assert int(sdf_data["m_AtlasWidth"]) == 256
    assert int(sdf_data["m_AtlasHeight"]) == 256
