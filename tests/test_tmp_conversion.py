from unity_font_replacer_core import (
    _resolve_creation_settings_key,
    _sync_creation_settings_payload,
    convert_glyphs_new_to_old,
    detect_tmp_version,
    normalize_sdf_data,
)


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
    # old(top-origin) y=2, h=12, atlas=512 -> new(bottom-origin) y=498
    assert normalized["m_GlyphTable"][0]["m_GlyphRect"]["m_Y"] == 498


def test_detect_tmp_version_uses_unity_version_hint_on_ambiguous_schema() -> None:
    """KR: 양쪽 키가 공존하는 모호한 데이터에서 Unity 버전 힌트를 사용하는지 검증합니다.
    EN: Verify Unity version hint is used for ambiguous dual-schema data.
    """
    ambiguous = {
        "m_FaceInfo": {},
        "m_fontInfo": {},
        "m_GlyphTable": [],
        "m_glyphInfoList": [],
        "m_AtlasTextures": [{"m_FileID": 0, "m_PathID": 1}],
        "atlas": {"m_FileID": 0, "m_PathID": 1},
    }
    assert detect_tmp_version(ambiguous, unity_version="2018.3.14f1") == "old"
    assert detect_tmp_version(ambiguous, unity_version="2019.1.0f1") == "new"


def test_detect_tmp_version_prioritizes_glyph_evidence_over_version_hint() -> None:
    """KR: 버전 힌트보다 실제 글리프 데이터 증거를 우선하는지 검증합니다.
    EN: Verify glyph evidence takes priority over version hint.
    """
    data = {
        "m_FaceInfo": {},
        "m_fontInfo": {},
        "m_GlyphTable": [{"m_Index": 0}],
        "m_glyphInfoList": [],
        "m_AtlasTextures": [{"m_FileID": 0, "m_PathID": 1}],
        "atlas": {"m_FileID": 0, "m_PathID": 1},
    }
    assert detect_tmp_version(data, unity_version="2018.3.14f1") == "new"


def test_sync_creation_settings_payload_with_legacy_keys() -> None:
    """KR: 구형 creation settings 키 이름을 동기화하는지 검증합니다.
    EN: Verify syncing legacy creation-settings key names.
    """
    cs = {
        "atlasWidth": 64,
        "atlasHeight": 64,
        "padding": 1,
        "pointSize": 10,
        "characterSequence": "abc",
    }
    _sync_creation_settings_payload(cs, atlas_width=1024, atlas_height=512, padding=7, point_size=42)
    assert cs["atlasWidth"] == 1024
    assert cs["atlasHeight"] == 512
    assert cs["padding"] == 7
    assert cs["pointSize"] == 42
    assert cs["characterSequence"] == ""


def test_sync_creation_settings_payload_with_editor_style_keys() -> None:
    """KR: editor 계열 키(m_*) 패턴도 동기화하는지 검증합니다.
    EN: Verify syncing editor-style (m_*) key patterns as well.
    """
    cs = {
        "m_AtlasWidth": 64,
        "m_AtlasHeight": 64,
        "m_Padding": 1,
        "m_PointSize": 10,
        "m_CharacterSequence": "xyz",
    }
    _sync_creation_settings_payload(cs, atlas_width=2048, atlas_height=2048, padding=9, point_size=36)
    assert cs["m_AtlasWidth"] == 2048
    assert cs["m_AtlasHeight"] == 2048
    assert cs["m_Padding"] == 9
    assert cs["m_PointSize"] == 36
    assert cs["m_CharacterSequence"] == ""


def test_resolve_creation_settings_key_prefers_present_dict() -> None:
    """KR: 타겟 데이터에 존재하는 creation settings 키를 우선 선택하는지 검증합니다.
    EN: Verify resolver prefers actually present creation-settings dict keys.
    """
    data = {
        "m_FontAssetCreationSettings": {"atlasWidth": 512},
        "m_CreationSettings": "not-a-dict",
    }
    assert _resolve_creation_settings_key(data, unity_version="2019.4.40f1") == "m_FontAssetCreationSettings"


def test_convert_glyphs_new_to_old_applies_fixed_tmp_formula() -> None:
    """KR: new(bottom-origin) -> old(top-origin) Y 변환 공식을 고정 적용하는지 검증합니다.
    EN: Verify fixed TMP Y conversion formula for new(bottom) -> old(top).
    """
    glyph_table = [
        {
            "m_Index": 0,
            "m_Metrics": {
                "m_Width": 10,
                "m_Height": 12,
                "m_HorizontalBearingX": 0,
                "m_HorizontalBearingY": 11,
                "m_HorizontalAdvance": 10,
            },
            "m_GlyphRect": {
                "m_X": 1,
                "m_Y": 498,  # new(bottom-origin)
                "m_Width": 10,
                "m_Height": 12,
            },
            "m_Scale": 1.0,
        }
    ]
    char_table = [{"m_Unicode": 65, "m_GlyphIndex": 0}]
    old = convert_glyphs_new_to_old(glyph_table, char_table, atlas_height=512)
    assert old[0]["y"] == 2.0
