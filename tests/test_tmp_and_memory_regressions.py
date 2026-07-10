from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import export_fonts_core as exporter
import unity_font_replacer_core as core
from UnityPy.files.replacers import Replacer


ROOT = Path(__file__).resolve().parents[1]


class _BaseReplacer:
    def __init__(self, data: bytes):
        self.data = data
        self.size = len(data)
        self.read_called = False

    def __len__(self) -> int:
        return len(self.data)

    def iter_chunks(self, chunk_size: int = 1024 * 1024):
        yield self.data

    def write_to(self, writer, chunk_size: int = 1024 * 1024) -> None:
        writer.write(self.data)

    def read_bytes(self) -> bytes:
        self.read_called = True
        return self.data

    def cleanup(self) -> None:
        return None


class _AssetsFile:
    def __init__(self) -> None:
        self.changed = False

    def mark_changed(self) -> None:
        self.changed = True


class _Object:
    def __init__(self, data: Replacer):
        self.data = data
        self.assets_file = _AssetsFile()


class TmpAndMemoryRegressionTests(unittest.TestCase):
    def test_only_singular_atlas_reference_is_detected(self) -> None:
        data = {
            "m_GlyphTable": [{"m_Index": 1}],
            "m_AtlasTexture": {"m_FileID": 2, "m_PathID": 99},
        }
        info = core.inspect_tmp_font_schema(data, unity_version="2021.3.0f1")
        self.assertTrue(info["is_tmp"])
        self.assertEqual(info["version"], "new")
        self.assertEqual((info["atlas_file_id"], info["atlas_path_id"]), (2, 99))
        export_info = exporter.inspect_tmp_font_schema(data, unity_version="2021.3.0f1")
        self.assertEqual(export_info["atlas_path_id"], 99)

    def test_new_schema_fields_override_old_unity_hint(self) -> None:
        data = {"m_GlyphTable": [], "m_CharacterTable": [], "m_AtlasWidth": 64}
        self.assertEqual(core.detect_tmp_version(data, "2018.3.14f1"), "new")
        self.assertEqual(exporter.detect_tmp_version(data, "2018.3.14f1"), "new")

    def test_new_to_old_uses_packed_rect_and_flips_y(self) -> None:
        glyphs = [
            {
                "m_Index": 7,
                "m_GlyphRect": {"m_X": 3, "m_Y": 5, "m_Width": 9, "m_Height": 11},
                "m_Metrics": {
                    "m_Width": 8.25,
                    "m_Height": 10.5,
                    "m_HorizontalBearingX": 1,
                    "m_HorizontalBearingY": 2,
                    "m_HorizontalAdvance": 12,
                },
            }
        ]
        chars = [{"m_Unicode": 65, "m_GlyphIndex": "7"}]
        old = core.convert_glyphs_new_to_old(glyphs, chars, atlas_height=64)[0]
        self.assertEqual((old["width"], old["height"]), (9.0, 11.0))
        self.assertEqual(old["y"], 48.0)
        self.assertEqual(old["y"] + 5 + old["height"], 64)

    def test_hybrid_legacy_face_keeps_actual_character_count(self) -> None:
        legacy = core.convert_face_info_new_to_old(
            {"m_FamilyName": "Hybrid"},
            atlas_padding=7,
            atlas_width=64,
            atlas_height=64,
            character_count=3,
        )
        self.assertEqual(legacy["CharacterCount"], 3)

    def test_all_creation_settings_key_variants_are_supported(self) -> None:
        for key in core._TMP_CREATION_SETTINGS_KEYS:
            payload = {key: {"characterSequence": "abc"}}
            self.assertEqual(core._resolve_creation_settings_key(payload), key)
            self.assertEqual(exporter._resolve_creation_settings_key(payload), key)

    def test_stale_feature_records_are_cleared_without_adding_fields(self) -> None:
        target = {
            "m_GlyphPairAdjustmentRecords": [{"old": 1}],
            "m_LigatureSubstitutionRecords": [{"old": 2}],
        }
        core._sync_existing_record_table(
            target,
            {"m_GlyphPairAdjustmentRecords": []},
        )
        self.assertEqual(
            target,
            {
                "m_GlyphPairAdjustmentRecords": [],
                "m_LigatureSubstitutionRecords": [],
            },
        )

    def test_single_atlas_state_is_consistent_and_shape_preserving(self) -> None:
        target = {
            "m_AtlasTextures": [
                {"m_FileID": 0, "m_PathID": 0},
                {"m_FileID": 2, "m_PathID": 88},
            ],
            "m_AtlasTexture": {"m_FileID": 0, "m_PathID": 1},
            "atlas": {"m_FileID": 0, "m_PathID": 2},
            "m_AtlasTextureIndex": 3,
            "m_IsMultiAtlasTexturesEnabled": True,
            "m_AtlasPopulationMode": 1,
            "InternalDynamicOS": True,
        }
        template = core._best_atlas_ref(target, prefer_new=True)
        core._sync_single_atlas_state(
            target,
            5,
            123,
            reference_template=template,
        )
        expected_ref = {"m_FileID": 5, "m_PathID": 123}
        self.assertEqual(target["m_AtlasTextures"], [expected_ref])
        self.assertEqual(target["m_AtlasTexture"], expected_ref)
        self.assertEqual(target["atlas"], expected_ref)
        self.assertEqual(target["m_AtlasTextureIndex"], 0)
        self.assertFalse(target["m_IsMultiAtlasTexturesEnabled"])
        self.assertEqual(target["m_AtlasPopulationMode"], 0)
        self.assertFalse(target["InternalDynamicOS"])

        minimal = {"m_AtlasTextures": []}
        core._sync_single_atlas_state(minimal, 0, 7)
        self.assertEqual(set(minimal), {"m_AtlasTextures"})

    def test_material_reference_is_optional_for_textcore_assets(self) -> None:
        self.assertEqual(core._get_tmp_material_reference({}), (None, 0, 0))
        self.assertEqual(
            core._get_tmp_material_reference(
                {"material": {"m_FileID": 4, "m_PathID": 12}}
            ),
            ("material", 4, 12),
        )
    def test_trailing_bytes_wrap_replacer_without_materializing_it(self) -> None:
        base = _BaseReplacer(b"base")
        obj = _Object(base)
        core._append_trailing_bytes(obj, b"tail")
        self.assertFalse(base.read_called)
        self.assertTrue(isinstance(obj.data, Replacer))
        self.assertEqual(b"".join(obj.data.iter_chunks()), b"basetail")
        self.assertTrue(obj.assets_file.changed)

    def test_segmented_replacer_streams_without_joining_segments(self) -> None:
        tail = memoryview(b"tail")
        replacement = core._SegmentedBytesReplacer(
            (bytearray(b"head"), b"-", tail)
        )
        self.assertEqual(len(replacement), 9)
        self.assertEqual(b"".join(replacement.iter_chunks(2)), b"head-tail")
        replacement.cleanup()
        self.assertEqual(replacement.segments, [])

    def test_typetree_mismatch_counter_reuses_parsed_object_without_buffering(self) -> None:
        parsed = object()
        captured_streams = []

        class FakeObject:
            reader = SimpleNamespace(endian="<")
            assets_file = object()
            byte_size = 9

            def read_typetree(self, **kwargs):
                raise AssertionError("the already parsed object must be reused")

            def _get_typetree_node(self):
                return object()

        def count_write(value, node, writer, assets_file) -> None:
            self.assertIs(value, parsed)
            captured_streams.append(writer.stream)
            writer.write_bytes(b"12345678")

        obj = FakeObject()
        with patch(
            "UnityPy.helpers.TypeTreeHelper.write_typetree",
            side_effect=count_write,
        ):
            self.assertTrue(core._detect_typetree_size_mismatch(obj, parsed))

        self.assertEqual(len(captured_streams), 1)
        self.assertIsInstance(captured_streams[0], core._CountingWriteStream)
        self.assertTrue(captured_streams[0].closed)

    def test_binary_texture_fallback_keeps_replacement_segmented(self) -> None:
        children = [
            SimpleNamespace(m_Name="m_Width", m_Type="int"),
            SimpleNamespace(m_Name="m_Height", m_Type="int"),
            SimpleNamespace(m_Name="m_CompleteImageSize", m_Type="unsigned int"),
            SimpleNamespace(m_Name="image data", m_Type="TypelessData"),
        ]
        original = (
            struct.pack("<iii", 2, 2, 4)
            + struct.pack("<i", 4)
            + b"OLD!"
            + (b"TAIL" * 10)
        )

        class FakeAssetsFile:
            changed = False

            def mark_changed(self) -> None:
                self.changed = True

        class FakeObject:
            reader = SimpleNamespace(endian="<")
            assets_file = FakeAssetsFile()
            path_id = 99
            data = None

            def get_raw_data(self) -> bytes:
                return original

            def _get_typetree_node(self):
                return SimpleNamespace(m_Children=children)

            def set_raw_data(self, data) -> None:
                self.data = data
                self.assets_file.mark_changed()

        def advance_scalar(child, reader, config):
            reader.Position += 4
            return None

        obj = FakeObject()
        with patch(
            "UnityPy.helpers.TypeTreeHelper.read_value",
            side_effect=advance_scalar,
        ):
            self.assertTrue(
                core._binary_patch_texture2d(
                    obj,
                    image_data=b"NEWNEW",
                    width=7,
                    height=8,
                    lang="en",
                )
            )

        self.assertIsInstance(obj.data, core._SegmentedBytesReplacer)
        self.assertNotIsInstance(obj.data.segments[-1], memoryview)
        saved = b"".join(obj.data.iter_chunks(3))
        self.assertEqual(struct.unpack_from("<iii", saved, 0), (7, 8, 6))
        self.assertEqual(struct.unpack_from("<i", saved, 12)[0], 6)
        self.assertEqual(saved[16:22], b"NEWNEW")
        self.assertTrue(saved.endswith(b"TAIL"))
        self.assertTrue(obj.assets_file.changed)
        obj.data.cleanup()

    def test_static_font_cache_keeps_path_not_decoded_atlas(self) -> None:
        core._load_font_assets_cached.cache_clear()
        cached = core._load_font_assets_cached(str(ROOT), "NanumGothic", False, None)
        self.assertNotIn("sdf_atlas", cached)
        self.assertTrue(Path(cached["sdf_atlas_path"]).is_file())
        loaded = core.load_font_assets("NanumGothic", generate_sdf=False)
        self.assertIsInstance(loaded["sdf_atlas"], Image.Image)
        loaded["sdf_atlas"].close()

    def test_spilled_source_atlas_is_closed_once(self) -> None:
        image = Image.new("RGBA", (4, 4), (255, 255, 255, 255))
        core._close_unique_images(image, image)
        with self.assertRaises(ValueError):
            image.getpixel((0, 0))

    def test_invalid_ttf_parser_does_not_overwrite_existing_names(self) -> None:
        class Font:
            m_FontSize = 16
            m_FontNames = ["Original"]
            m_Ascent = 1.0
            m_Descent = -1.0
            m_LineSpacing = 2.0

        font = Font()
        with patch.object(core, "TTFont", None):
            metadata = core.apply_ttf_metadata_to_font(font, b"bad", "Fallback")
        self.assertFalse(metadata["parsed"])
        self.assertEqual(font.m_FontNames, ["Original"])

    def test_alpha8_linear_encoding_has_explicit_bottom_row_first_order(self) -> None:
        image = Image.new("L", (2, 2))
        image.putdata([1, 2, 3, 4])
        raw, width, height, mode = core._encode_alpha8_replacement_bytes(
            image,
            ps5_swizzle=False,
            target_swizzled_state=False,
        )
        self.assertEqual((width, height, mode), (2, 2, "linear_flipped"))
        self.assertEqual(raw, bytes([3, 4, 1, 2]))
        image.close()

    def test_logical_key_wins_over_output_only_copy_path(self) -> None:
        logical = str(ROOT / "Game_Data" / "sharedassets0.assets")
        output_copy = str(ROOT / "output" / "Game_Data" / "sharedassets0.assets")
        self.assertEqual(
            core._resolve_current_file_key(output_copy, logical),
            core._normalize_asset_file_key(logical),
        )

    def test_ttf_only_scan_does_not_build_typetree_generator(self) -> None:
        with (
            patch.object(core, "get_data_path", return_value=str(ROOT)),
            patch.object(core, "find_assets_files", return_value=[]),
            patch.object(
                core,
                "get_unity_version",
                side_effect=AssertionError("TTF-only scan must not read Unity version"),
            ),
            patch.object(
                core,
                "_create_generator",
                side_effect=AssertionError("TTF-only scan must not create TypeTree"),
            ),
        ):
            result = core.scan_fonts(
                "unused",
                isolate_files=False,
                scan_ttf=True,
                scan_sdf=False,
            )
        self.assertEqual(result, {"ttf": [], "sdf": []})

        # With both scan types disabled, even path discovery is skipped.
        with patch.object(
            core,
            "get_data_path",
            side_effect=AssertionError("disabled scan must return immediately"),
        ):
            self.assertEqual(
                core.scan_fonts("unused", scan_ttf=False, scan_sdf=False),
                {"ttf": [], "sdf": []},
            )

    def test_split_files_are_not_queued_for_unsafe_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            game = Path(temp_dir) / "Game"
            data = game / "Game_Data"
            data.mkdir(parents=True)
            (data / "normal.assets").write_bytes(b"normal")
            (data / "bundle.split0").write_bytes(b"first")
            (data / "bundle.split1").write_bytes(b"second")

            replacement_files = core.find_assets_files(str(game), lang="en")
            self.assertEqual(
                [Path(path).name for path in replacement_files],
                ["normal.assets"],
            )
            export_files = exporter.find_assets_files(str(data))
            self.assertEqual(
                sorted(Path(path).name for path in export_files),
                ["bundle.split0", "normal.assets"],
            )

    def test_asset_scan_prunes_only_tool_temp_not_nested_game_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "Game_Data"
            root_temp = data_path / "temp"
            nested_temp = data_path / "StreamingAssets" / "temp"
            rollback = data_path / ".unity_font_replacer_rollback"
            root_temp.mkdir(parents=True)
            nested_temp.mkdir(parents=True)
            rollback.mkdir(parents=True)
            ignored_temp = root_temp / "ignored.assets"
            kept_nested = nested_temp / "kept.assets"
            ignored_rollback = rollback / "ignored.rollback"
            regular = data_path / "regular.assets"
            for path in (ignored_temp, kept_nested, ignored_rollback, regular):
                path.write_bytes(b"asset")

            with patch.object(core, "get_data_path", return_value=str(data_path)):
                core_files = core.find_assets_files(str(data_path), lang="en")
            export_files = exporter.find_assets_files(str(data_path))

            self.assertEqual(
                {Path(path) for path in core_files},
                {kept_nested, regular},
            )
            self.assertEqual(
                {Path(path) for path in export_files},
                {kept_nested, regular},
            )


if __name__ == "__main__":
    unittest.main()
