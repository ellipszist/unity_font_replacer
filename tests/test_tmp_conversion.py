from unity_font_replacer_core import detect_tmp_version, normalize_sdf_data


def test_detect_tmp_version_for_old_format() -> None:
    """KR: 구형 TMP 데이터 버전 감지가 정상인지 검증합니다.
    EN: Verify old TMP format version detection.
    """
    old = {
        "m_fontInfo": {"Name": "Old Font", "PointSize": 42},
        "m_glyphInfoList": [{"id": 65, "x": 0, "y": 0, "width": 10, "height": 12}],
        "atlas": {"m_FileID": 0, "m_PathID": 777},
    }
    assert detect_tmp_version(old) == "old"


def test_normalize_sdf_data_converts_old_to_new() -> None:
    """KR: 구형 TMP 데이터가 신형 스키마로 변환되는지 검증합니다.
    EN: Verify normalization from old TMP schema to new TMP schema.
    """
    old = {
        "m_fontInfo": {
            "Name": "Old Font",
            "PointSize": 42,
            "Scale": 1.0,
            "LineHeight": 50,
            "Ascender": 40,
            "CapHeight": 35,
            "CenterLine": 20,
            "Baseline": 10,
            "Descender": -5,
            "SuperscriptOffset": 0,
            "SubscriptOffset": 0,
            "SubSize": 0.5,
            "Underline": -2,
            "UnderlineThickness": 1,
            "strikethrough": 8,
            "strikethroughThickness": 1,
            "TabWidth": 20,
            "Padding": 5,
            "AtlasWidth": 512,
            "AtlasHeight": 512,
        },
        "m_glyphInfoList": [
            {
                "id": 65,
                "x": 1,
                "y": 2,
                "width": 10,
                "height": 12,
                "xOffset": 0,
                "yOffset": 11,
                "xAdvance": 10,
                "scale": 1.0,
            }
        ],
        "atlas": {"m_FileID": 0, "m_PathID": 777},
    }

    normalized = normalize_sdf_data(old)

    assert detect_tmp_version(normalized) == "new"
    assert normalized["m_FaceInfo"]["m_PointSize"] == 42
    assert normalized["m_GlyphTable"][0]["m_Index"] == 0
    assert normalized["m_CharacterTable"][0]["m_Unicode"] == 65
    assert normalized["m_AtlasTextures"][0]["m_PathID"] == 777
