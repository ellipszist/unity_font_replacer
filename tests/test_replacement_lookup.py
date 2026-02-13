from unity_font_replacer_core import build_replacement_lookup


def test_build_replacement_lookup_normalizes_and_filters() -> None:
    """KR: 교체 룩업 빌더의 정규화/필터 동작을 검증합니다.
    EN: Validate normalization and filtering in replacement lookup builder.
    """
    replacements = {
        "ok-ttf": {
            "Type": "TTF",
            "File": "sharedassets0.assets",
            "assets_name": "sharedassets0.assets",
            "Path_ID": 101,
            "Replace_to": "Mulmaru.ttf",
        },
        "ok-sdf": {
            "Type": "SDF",
            "File": "sharedassets1.assets",
            "assets_name": "sharedassets1.assets",
            "Path_ID": "202",
            "Replace_to": "NanumGothic SDF Atlas.png",
        },
        "skip-empty": {
            "Type": "SDF",
            "File": "sharedassets1.assets",
            "assets_name": "sharedassets1.assets",
            "Path_ID": 303,
            "Replace_to": "",
        },
        "skip-invalid-path": {
            "Type": "TTF",
            "File": "sharedassets2.assets",
            "assets_name": "sharedassets2.assets",
            "Path_ID": "not-int",
            "Replace_to": "Mulmaru",
        },
    }

    lookup, files = build_replacement_lookup(replacements)

    assert lookup[("TTF", "sharedassets0.assets", "sharedassets0.assets", 101)] == "Mulmaru"
    assert lookup[("SDF", "sharedassets1.assets", "sharedassets1.assets", 202)] == "NanumGothic"
    assert "sharedassets0.assets" in files
    assert "sharedassets1.assets" in files
    assert "sharedassets2.assets" not in files
