from export_fonts_core import extract_tmp_refs


def test_extract_tmp_refs_new_format() -> None:
    """KR: 신형 TMP 포맷의 참조 추출을 검증합니다.
    EN: Validate reference extraction for new TMP format.
    """
    parse_dict = {
        "m_GlyphTable": [{"m_Index": 0}],
        "m_AtlasTextures": [{"m_FileID": 0, "m_PathID": 1234}],
        "m_Material": {"m_PathID": 4567},
        "m_CreationSettings": {"characterSequence": "abc"},
    }

    refs = extract_tmp_refs(parse_dict)

    assert refs is not None
    assert refs["atlas_path_id"] == 1234
    assert refs["material_path_id"] == 4567
    assert parse_dict["m_CreationSettings"]["characterSequence"] == ""


def test_extract_tmp_refs_old_format() -> None:
    """KR: 구형 TMP 포맷의 참조 추출을 검증합니다.
    EN: Validate reference extraction for old TMP format.
    """
    parse_dict = {
        "m_fontInfo": {"Name": "Old"},
        "m_glyphInfoList": [{"id": 65}],
        "atlas": {"m_FileID": 0, "m_PathID": 987},
        "material": {"m_PathID": 654},
    }

    refs = extract_tmp_refs(parse_dict)

    assert refs is not None
    assert refs["atlas_path_id"] == 987
    assert refs["material_path_id"] == 654


def test_extract_tmp_refs_skips_external_stub() -> None:
    """KR: 외부 참조 stub 데이터가 제외되는지 검증합니다.
    EN: Ensure external-reference stubs are skipped.
    """
    parse_dict = {
        "m_GlyphTable": [{"m_Index": 0}],
        "m_AtlasTextures": [{"m_FileID": 2, "m_PathID": 0}],
    }
    assert extract_tmp_refs(parse_dict) is None
