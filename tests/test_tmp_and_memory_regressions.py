from __future__ import annotations

import base64
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import export_fonts_core as exporter
import make_sdf
import unity_font_replacer_core as core
import unitypy_runtime as runtime
from addressables_catalog import (
    inspect_addressables_bundle_options,
    patch_addressables_catalog_bytes,
    validate_local_addressables_bundle_load,
)
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
    def test_addressables_catalog_patch_preserves_compact_offsets(self) -> None:
        def make_record(
            bundle_name: str,
            crc: int,
            size: int,
            *,
            use_uwr: bool = False,
        ) -> bytes:
            assembly = b"Unity.ResourceManager"
            class_name = (
                b"UnityEngine.ResourceManagement.ResourceProviders."
                b"AssetBundleRequestOptions"
            )
            payload = json.dumps(
                {
                    "m_Hash": "abc",
                    "m_Crc": crc,
                    "m_BundleName": bundle_name,
                    "m_BundleSize": size,
                    "m_UseUWRForLocalBundles": use_uwr,
                },
                separators=(",", ":"),
            ).encode("utf-16-le")
            return (
                bytes([7, len(assembly)])
                + assembly
                + bytes([len(class_name)])
                + class_name
                + struct.pack("<i", len(payload))
                + payload
            )

        first = make_record("font.bundle", 3653417969, 12345678)
        second = make_record("untouched.bundle", 99, 88)
        extra_data = first + second
        entries = bytearray(struct.pack("<i", 2))
        for internal_id_index, data_offset in enumerate((0, len(first))):
            entries.extend(
                struct.pack("<7i", internal_id_index, 0, -1, 0, data_offset, 0, 0)
            )
        catalog = json.dumps(
            {
                "m_EntryDataString": base64.b64encode(entries).decode("ascii"),
                "m_ExtraDataString": base64.b64encode(extra_data).decode("ascii"),
                "m_InternalIds": [
                    "{UnityEngine.AddressableAssets.Addressables.RuntimePath}/font.bundle",
                    "{UnityEngine.AddressableAssets.Addressables.RuntimePath}/untouched.bundle",
                ],
            },
            separators=(",", ":"),
        ).encode("utf-8")

        patched, names = patch_addressables_catalog_bytes(
            catalog,
            {"font.bundle": 23456789},
        )
        records = {
            record["value"]["m_BundleName"]: record["value"]
            for record in inspect_addressables_bundle_options(patched)
        }

        self.assertEqual(len(patched), len(catalog))
        self.assertEqual(names, ["font.bundle"])
        self.assertEqual(records["font.bundle"]["m_Hash"], "abc")
        self.assertEqual(records["font.bundle"]["m_Crc"], 0)
        self.assertEqual(records["font.bundle"]["m_BundleSize"], 23456789)
        self.assertEqual(records["untouched.bundle"]["m_Crc"], 99)

        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "catalog.json"
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text(
                json.dumps({"m_buildTarget": "StandaloneWindows64"}),
                encoding="utf-8",
            )
            validate_local_addressables_bundle_load(
                str(catalog_path),
                catalog,
                names,
            )

            remote_catalog = json.loads(catalog.decode("utf-8"))
            remote_catalog["m_InternalIds"][0] = "https://example.test/font.bundle"
            with self.assertRaisesRegex(ValueError, "local RuntimePath contract"):
                validate_local_addressables_bundle_load(
                    str(catalog_path),
                    json.dumps(remote_catalog).encode("utf-8"),
                    names,
                )

            forced_record = make_record(
                "font.bundle",
                1,
                2,
                use_uwr=True,
            )
            forced_entries = struct.pack("<i7i", 1, 0, 0, -1, 0, 0, 0, 0)
            forced_catalog = json.dumps(
                {
                    "m_EntryDataString": base64.b64encode(forced_entries).decode(
                        "ascii"
                    ),
                    "m_ExtraDataString": base64.b64encode(forced_record).decode(
                        "ascii"
                    ),
                    "m_InternalIds": [
                        "{UnityEngine.AddressableAssets.Addressables.RuntimePath}/font.bundle"
                    ],
                }
            ).encode("utf-8")
            with self.assertRaisesRegex(ValueError, "forces UnityWebRequest"):
                validate_local_addressables_bundle_load(
                    str(catalog_path),
                    forced_catalog,
                    names,
                )

            settings_path.write_text(
                json.dumps({"m_buildTarget": "Android"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "local standalone"):
                validate_local_addressables_bundle_load(
                    str(catalog_path),
                    catalog,
                    names,
                )

    def test_sdf_used_rects_use_tmp_bottom_origin(self) -> None:
        packed = make_sdf._pack_rectangles_shelf([(1, 10, 8)], 64, 64)
        self.assertIsNotNone(packed)
        placements, used_rects = packed

        self.assertEqual(placements[1], (0, 0, 10, 8))
        self.assertEqual(
            used_rects,
            [{"m_X": 0, "m_Y": 56, "m_Width": 10, "m_Height": 8}],
        )

    def test_sdf_coverage_edt_preserves_zero_contour_and_edge_levels(
        self,
    ) -> None:
        np = make_sdf.np
        self.assertIsNotNone(np)
        assert np is not None

        alpha = np.zeros((12, 11), dtype=np.uint8)
        alpha[:, 3:8] = np.asarray([0, 124, 255, 124, 0], dtype=np.uint8)
        alpha[3:9, 8] = 160
        alpha[4:8, 9] = 240
        coverage_sdf = make_sdf._compute_sdf_tile(alpha, 21)

        self.assertEqual(coverage_sdf.shape, alpha.shape)
        self.assertTrue(np.array_equal(coverage_sdf >= 128, alpha > 127))
        self.assertEqual(
            int((coverage_sdf >= 128).sum()),
            int((alpha > 127).sum()),
        )
        coverage_ramp = np.tile(
            np.asarray(
                [1, 32, 64, 96, 124, 128, 160, 192, 224, 254],
                dtype=np.uint8,
            ),
            (3, 1),
        )
        for spread in (5, 7, 15, 20, 64):
            with self.subTest(spread=spread):
                ramp_sdf = make_sdf._compute_sdf_tile(coverage_ramp, spread)
                self.assertTrue(
                    np.array_equal(ramp_sdf >= 128, coverage_ramp > 127)
                )
                self.assertLess(int(ramp_sdf[1, 4]), 128)
                self.assertGreaterEqual(int(ramp_sdf[1, 5]), 128)

        ramp_sdf = make_sdf._compute_sdf_tile(coverage_ramp, 21)
        edge_levels = {
            int(value) for value in np.unique(ramp_sdf) if 124 <= value <= 131
        }
        self.assertEqual(edge_levels, set(range(124, 132)))

        horizontal = np.zeros((11, 12), dtype=np.uint8)
        horizontal[4:7, :] = 255
        diagonal = np.zeros((11, 12), dtype=np.uint8)
        diagonal[np.arange(10), np.arange(10)] = 255
        thin_vertical = np.zeros((11, 12), dtype=np.uint8)
        thin_vertical[:, 5] = 255
        edge_columns = np.zeros((11, 12), dtype=np.uint8)
        edge_columns[:, (0, -1)] = 255
        for name, fixture in (
            ("horizontal", horizontal),
            ("diagonal", diagonal),
            ("thin_vertical", thin_vertical),
            ("edge_columns", edge_columns),
        ):
            with self.subTest(fixture=name):
                fixture_sdf = make_sdf._compute_sdf_tile(fixture, 21)
                self.assertTrue(
                    np.array_equal(fixture_sdf >= 128, fixture > 127)
                )
        edge_sdf = make_sdf._compute_sdf_tile(edge_columns, 21)
        self.assertGreater(int(edge_sdf[5, 0]), int(edge_sdf[5, 1]))
        self.assertGreater(int(edge_sdf[5, -1]), int(edge_sdf[5, -2]))

        hard_edge = np.zeros((9, 48), dtype=np.uint8)
        hard_edge[:, :24] = 255
        hard_sdf = make_sdf._compute_sdf_tile(hard_edge, 21)
        middle_row = hard_sdf[4].astype(np.int16)
        self.assertEqual(
            [int(middle_row[index]) for index in (22, 23, 24, 25)],
            [137, 131, 124, 118],
        )
        outside_steps = np.diff(middle_row[25:32])
        self.assertTrue(np.all((outside_steps == -6) | (outside_steps == -7)))

        with (
            patch.object(
                make_sdf.scipy_ndimage,
                "binary_erosion",
                side_effect=lambda values, **_kwargs: values.copy(),
            ),
            patch.object(
                make_sdf.scipy_ndimage,
                "binary_dilation",
                side_effect=lambda values, **_kwargs: values.copy(),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "no boundary seed"):
                make_sdf._compute_sdf_tile(hard_edge, 21)

        empty = np.zeros((3, 5), dtype=np.uint8)
        full = np.full((3, 5), 255, dtype=np.uint8)
        self.assertTrue(
            np.array_equal(
                make_sdf._compute_sdf_tile(empty, 3),
                empty,
            )
        )
        self.assertTrue(
            np.array_equal(
                make_sdf._compute_sdf_tile(full, 3),
                full,
            )
        )
        subthreshold = np.asarray([[0, 64, 127, 64, 0]], dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, "never crosses"):
            make_sdf._compute_sdf_tile(subthreshold, 3)

    def test_generated_sdf_preserves_textcore_sampling_guard(self) -> None:
        generated = make_sdf.generate_sdf_assets_from_ttf(
            ttf_data=(ROOT / "KR_ASSETS" / "NanumGothic.ttf").read_bytes(),
            font_name="NanumGothic",
            unicodes=[ord(char) for char in "가나다라"],
            point_size=16,
            atlas_padding=2,
            atlas_width=64,
            atlas_height=64,
        )
        self.assertIsInstance(generated, dict)
        assert generated is not None
        try:
            data = generated["sdf_data"]
            atlas_alpha = make_sdf.np.asarray(
                generated["sdf_atlas"].getchannel("A")
            )
            atlas_height = int(data["m_AtlasHeight"])
            padding = int(data["m_AtlasPadding"])
            used_rects = data["m_UsedGlyphRects"]

            for glyph in data["m_GlyphTable"]:
                glyph_rect = glyph["m_GlyphRect"]
                glyph_x = int(glyph_rect["m_X"])
                glyph_y = int(glyph_rect["m_Y"])
                glyph_width = int(glyph_rect["m_Width"])
                glyph_height = int(glyph_rect["m_Height"])
                containing = [
                    used
                    for used in used_rects
                    if int(used["m_X"]) <= glyph_x
                    and int(used["m_Y"]) <= glyph_y
                    and glyph_x + glyph_width
                    <= int(used["m_X"]) + int(used["m_Width"])
                    and glyph_y + glyph_height
                    <= int(used["m_Y"]) + int(used["m_Height"])
                ]
                self.assertEqual(len(containing), 1)
                used = containing[0]
                used_x = int(used["m_X"])
                used_y = int(used["m_Y"])
                used_width = int(used["m_Width"])
                used_height = int(used["m_Height"])

                self.assertEqual(used_width, glyph_width + padding * 2 + 1)
                self.assertEqual(used_height, glyph_height + padding * 2 + 1)
                self.assertEqual(glyph_x - used_x, padding + 1)
                self.assertEqual(glyph_y - used_y, padding + 1)
                self.assertEqual(
                    used_x + used_width - glyph_x - glyph_width,
                    padding,
                )
                self.assertEqual(
                    used_y + used_height - glyph_y - glyph_height,
                    padding,
                )

                used_top = atlas_height - used_y - used_height
                self.assertTrue(
                    make_sdf.np.all(
                        atlas_alpha[used_top : used_top + used_height, used_x] == 0
                    )
                )
                self.assertTrue(
                    make_sdf.np.all(
                        atlas_alpha[
                            used_top + used_height - 1,
                            used_x : used_x + used_width,
                        ]
                        == 0
                    )
                )
        finally:
            generated["sdf_atlas"].close()

    def test_generated_raster_uses_bitmap_packing_without_sdf_guard(self) -> None:
        generated = make_sdf.generate_sdf_assets_from_ttf(
            ttf_data=(ROOT / "KR_ASSETS" / "NanumGothic.ttf").read_bytes(),
            font_name="NanumGothic",
            unicodes=[ord(char) for char in "가나다라"],
            point_size=16,
            atlas_padding=2,
            atlas_width=64,
            atlas_height=64,
            render_mode="raster",
        )
        self.assertIsInstance(generated, dict)
        assert generated is not None
        try:
            data = generated["sdf_data"]
            self.assertEqual(
                generated["sdf_atlas"].convert("RGB").getextrema(),
                ((255, 255), (255, 255), (255, 255)),
            )
            padding = int(data["m_AtlasPadding"])
            used_rects = data["m_UsedGlyphRects"]

            for glyph in data["m_GlyphTable"]:
                glyph_rect = glyph["m_GlyphRect"]
                glyph_x = int(glyph_rect["m_X"])
                glyph_y = int(glyph_rect["m_Y"])
                glyph_width = int(glyph_rect["m_Width"])
                glyph_height = int(glyph_rect["m_Height"])
                containing = [
                    used
                    for used in used_rects
                    if int(used["m_X"]) <= glyph_x
                    and int(used["m_Y"]) <= glyph_y
                    and glyph_x + glyph_width
                    <= int(used["m_X"]) + int(used["m_Width"])
                    and glyph_y + glyph_height
                    <= int(used["m_Y"]) + int(used["m_Height"])
                ]
                self.assertEqual(len(containing), 1)
                used = containing[0]
                used_x = int(used["m_X"])
                used_y = int(used["m_Y"])
                used_width = int(used["m_Width"])
                used_height = int(used["m_Height"])

                self.assertEqual(used_width, glyph_width + padding * 2)
                self.assertEqual(used_height, glyph_height + padding * 2)
                self.assertEqual(glyph_x - used_x, padding)
                self.assertEqual(glyph_y - used_y, padding)
                self.assertEqual(
                    used_x + used_width - glyph_x - glyph_width,
                    padding,
                )
                self.assertEqual(
                    used_y + used_height - glyph_y - glyph_height,
                    padding,
                )
        finally:
            generated["sdf_atlas"].close()

    def test_dynamic_tmp_population_is_rejected(self) -> None:
        self.assertFalse(
            core._prepare_static_tmp_population(
                {"m_AtlasPopulationMode": 0, "InternalDynamicOS": False}
            )
        )
        with self.assertRaisesRegex(ValueError, "Dynamic TMP FontAsset"):
            core._prepare_static_tmp_population({"m_AtlasPopulationMode": 1})

        dynamic = {
            "m_AtlasPopulationMode": 1,
            "InternalDynamicOS": True,
            "m_SourceFontFile": {"m_FileID": 2, "m_PathID": -7},
            "m_SourceFontFileGUID": "preserved-editor-metadata",
        }
        self.assertTrue(
            core._prepare_static_tmp_population(dynamic, allow_freeze=True)
        )
        self.assertEqual(dynamic["m_AtlasPopulationMode"], 0)
        self.assertFalse(dynamic["InternalDynamicOS"])
        self.assertEqual(
            dynamic["m_SourceFontFile"],
            {"m_FileID": 0, "m_PathID": 0},
        )
        self.assertEqual(
            dynamic["m_SourceFontFileGUID"],
            "preserved-editor-metadata",
        )

    def test_generated_sdf_uses_real_glyph_ids_and_rebuilds_kern_pairs(self) -> None:
        self.assertEqual(
            make_sdf._quantize_tmp_font_units(-152 * 86 / 2048),
            -6.390625,
        )
        ttf_path = ROOT / "KR_ASSETS" / "NanumGothic.ttf"
        ttf_data = ttf_path.read_bytes()
        with make_sdf.TTFont(str(ttf_path), lazy=True) as font:
            cmap = font.getBestCmap()
            glyph_a = int(font.getGlyphID(cmap[65]))
            glyph_v = int(font.getGlyphID(cmap[86]))

        self.assertNotEqual(glyph_a, 65)
        self.assertEqual(
            make_sdf._resolve_unicode_glyph_map(ttf_data, [65, 86]),
            [(65, glyph_a), (86, glyph_v)],
        )

        generated = make_sdf.generate_sdf_assets_from_ttf(
            ttf_data=ttf_data,
            font_name="NanumGothic",
            unicodes=[65, 86],
            point_size=16,
            atlas_padding=2,
            atlas_width=128,
            atlas_height=128,
        )
        self.assertIsInstance(generated, dict)
        assert generated is not None
        try:
            data = generated["sdf_data"]
            self.assertEqual(data["m_AtlasRenderMode"], 4169)
            material_floats = dict(
                generated["sdf_materials"]["m_SavedProperties"]["m_Floats"]
            )
            self.assertEqual(
                material_floats["_GradientScale"],
                float(data["m_AtlasPadding"] + 1),
            )
            np = make_sdf.np
            self.assertIsNotNone(np)
            assert np is not None
            atlas_alpha = np.asarray(generated["sdf_atlas"].getchannel("A"))
            atlas_levels = {int(value) for value in np.unique(atlas_alpha)}
            self.assertGreater(len(atlas_levels), 32)
            self.assertTrue(atlas_levels.intersection(range(122, 133)))
            self.assertEqual(
                {glyph["m_Index"] for glyph in data["m_GlyphTable"]},
                {glyph_a, glyph_v},
            )
            self.assertEqual(
                {
                    character["m_Unicode"]: character["m_GlyphIndex"]
                    for character in data["m_CharacterTable"]
                },
                {65: glyph_a, 86: glyph_v},
            )
            pairs = data["m_FontFeatureTable"][
                "m_GlyphPairAdjustmentRecords"
            ]
            av_pair = next(
                pair
                for pair in pairs
                if pair["m_FirstAdjustmentRecord"]["m_GlyphIndex"] == glyph_a
                and pair["m_SecondAdjustmentRecord"]["m_GlyphIndex"] == glyph_v
            )
            self.assertAlmostEqual(
                av_pair["m_FirstAdjustmentRecord"]["m_GlyphValueRecord"][
                    "m_XAdvance"
                ],
                make_sdf._quantize_tmp_font_units(-92 * 16 / 1000),
            )
            legacy_pair = next(
                pair
                for pair in data["m_kerningInfo"]["kerningPairs"]
                if pair["AscII_Left"] == 65 and pair["AscII_Right"] == 86
            )
            self.assertAlmostEqual(
                legacy_pair["XadvanceOffset"],
                make_sdf._quantize_tmp_font_units(-92 * 16 / 1000),
            )
        finally:
            generated["sdf_atlas"].close()

    def test_selected_gdef_class_is_preserved_without_empty_auxiliary_noise(
        self,
    ) -> None:
        ttf_data = (ROOT / "KR_ASSETS" / "Mulmaru.ttf").read_bytes()
        mapping = make_sdf._resolve_unicode_glyph_map(ttf_data, [0x200B])
        self.assertEqual(len(mapping), 1)
        glyph_index = mapping[0][1]
        sdf_data = {"m_GlyphTable": [{"m_Index": glyph_index}]}

        make_sdf.apply_tmp_gdef_classes(ttf_data, sdf_data)

        self.assertEqual(
            sdf_data["m_GlyphTable"][0]["m_ClassDefinitionType"],
            1,
        )

    def test_raster_shader_contracts_are_name_and_property_driven(self) -> None:
        sprite_properties = {
            "_MainTex",
            "_Color",
            "_ClipRect",
            "_Stencil",
            "_StencilComp",
            "_ColorMask",
        }
        self.assertEqual(
            core._classify_compatible_raster_shader(
                "TextMeshPro/Sprite",
                sprite_properties,
            ),
            "tmp_sprite",
        )
        self.assertIsNone(
            core._classify_compatible_raster_shader(
                "TextMeshPro/Sprite",
                sprite_properties - {"_Stencil"},
            )
        )
        self.assertIsNone(
            core._classify_compatible_raster_shader(
                "TextMeshPro/Distance Field",
                sprite_properties,
            )
        )

    def test_raster_shader_retarget_prefers_dedicated_bitmap(self) -> None:
        def shader_reader(path_id: int, name: str, properties: set[str]):
            parsed_form = SimpleNamespace(
                m_Name=name,
                m_PropInfo=SimpleNamespace(
                    m_Props=[SimpleNamespace(m_Name=value) for value in properties]
                ),
            )
            reader = SimpleNamespace(
                type=SimpleNamespace(name="Shader"),
                path_id=path_id,
                parse_as_object=lambda: SimpleNamespace(
                    m_Name="",
                    m_ParsedForm=parsed_form,
                ),
            )
            return reader

        assets_file = SimpleNamespace(name="CAB-font", externals=[])
        bitmap = shader_reader(
            20,
            "TextMeshPro/Bitmap",
            {
                "_MainTex",
                "_FaceColor",
                "_ClipRect",
                "_Stencil",
                "_StencilComp",
                "_ColorMask",
            },
        )
        sprite = shader_reader(
            10,
            "TextMeshPro/Sprite",
            {
                "_MainTex",
                "_Color",
                "_ClipRect",
                "_Stencil",
                "_StencilComp",
                "_ColorMask",
            },
        )
        for reader in (bitmap, sprite):
            reader.assets_file = assets_file
        assets_file.objects = {10: sprite, 20: bitmap}
        material = SimpleNamespace(m_Shader=SimpleNamespace(m_FileID=0, m_PathID=1))

        resolved = core._resolve_compatible_raster_shader(
            assets_file,
            material,
            "font.bundle",
            source_bundle_signature="UnityFS",
            asset_file_index=None,
        )

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved["kind"], "tmp_bitmap")
        self.assertEqual((resolved["file_id"], resolved["path_id"]), (0, 20))

        gui_text = shader_reader(
            30,
            "GUI/Text Shader",
            {"_MainTex", "_Color"},
        )
        gui_text.assets_file = assets_file
        assets_file.objects = {30: gui_text}
        self.assertIsNone(
            core._resolve_compatible_raster_shader(
                assets_file,
                material,
                "font.bundle",
                source_bundle_signature="UnityFS",
                asset_file_index=None,
            )
        )
        unsafe_resolved = core._resolve_compatible_raster_shader(
            assets_file,
            material,
            "font.bundle",
            source_bundle_signature="UnityFS",
            asset_file_index=None,
            allow_unsafe_gui_text_fallback=True,
        )
        self.assertIsNotNone(unsafe_resolved)
        assert unsafe_resolved is not None
        self.assertEqual(unsafe_resolved["kind"], "gui_text")

    def test_raster_shader_retarget_preserves_current_compatible_pptr(self) -> None:
        def shader_reader(
            assets_file: SimpleNamespace,
            path_id: int,
            name: str,
            properties: set[str],
        ) -> SimpleNamespace:
            parsed_form = SimpleNamespace(
                m_Name=name,
                m_PropInfo=SimpleNamespace(
                    m_Props=[SimpleNamespace(m_Name=value) for value in properties]
                ),
            )
            return SimpleNamespace(
                type=SimpleNamespace(name="Shader"),
                path_id=path_id,
                assets_file=assets_file,
                parse_as_object=lambda: SimpleNamespace(
                    m_Name="",
                    m_ParsedForm=parsed_form,
                ),
            )

        bitmap_properties = {
            "_MainTex",
            "_FaceColor",
            "_ClipRect",
            "_Stencil",
            "_StencilComp",
            "_ColorMask",
        }
        sprite_properties = {
            "_MainTex",
            "_Color",
            "_ClipRect",
            "_Stencil",
            "_StencilComp",
            "_ColorMask",
        }
        assets_file = SimpleNamespace(name="CAB-font", externals=[])
        bitmap = shader_reader(
            assets_file, 20, "TextMeshPro/Bitmap", bitmap_properties
        )
        sprite = shader_reader(
            assets_file, 10, "TextMeshPro/Sprite", sprite_properties
        )
        assets_file.objects = {10: sprite, 20: bitmap}
        shader_ref = SimpleNamespace(
            m_FileID=0,
            m_PathID=10,
            deref=lambda: sprite,
        )
        material = SimpleNamespace(m_Shader=shader_ref)

        safe = core._resolve_compatible_raster_shader(
            assets_file,
            material,
            "font.bundle",
            source_bundle_signature="UnityFS",
            asset_file_index=None,
        )
        self.assertIsNotNone(safe)
        assert safe is not None
        self.assertEqual((safe["file_id"], safe["path_id"]), (0, 20))

        explicit = core._resolve_compatible_raster_shader(
            assets_file,
            material,
            "font.bundle",
            source_bundle_signature="UnityFS",
            asset_file_index=None,
            allow_unsafe_full_color_shader_fallback=True,
        )
        self.assertIsNotNone(explicit)
        assert explicit is not None
        self.assertEqual((explicit["file_id"], explicit["path_id"]), (0, 20))

        assets_file.objects = {10: sprite}
        explicit_current_only = core._resolve_compatible_raster_shader(
            assets_file,
            material,
            "font.bundle",
            source_bundle_signature="UnityFS",
            asset_file_index=None,
            allow_unsafe_full_color_shader_fallback=True,
        )
        self.assertIsNotNone(explicit_current_only)
        assert explicit_current_only is not None
        self.assertEqual(
            (explicit_current_only["file_id"], explicit_current_only["path_id"]),
            (0, 10),
        )

        external_assets = SimpleNamespace(name="CAB-shaders")
        external_bitmap = shader_reader(
            external_assets, 77, "TextMeshPro/Bitmap", bitmap_properties
        )
        external_material = SimpleNamespace(
            m_Shader=SimpleNamespace(
                m_FileID=2,
                m_PathID=77,
                deref=lambda: external_bitmap,
            )
        )
        assets_file.objects = {}
        external = core._resolve_compatible_raster_shader(
            assets_file,
            external_material,
            "font.bundle",
            source_bundle_signature="UnityFS",
            asset_file_index=None,
        )
        self.assertIsNotNone(external)
        assert external is not None
        self.assertEqual((external["file_id"], external["path_id"]), (2, 77))

    def test_raster_material_is_rebuilt_for_selected_shader_contract(self) -> None:
        main_texture = {"m_FileID": 2, "m_PathID": 99}
        material = SimpleNamespace(
            m_SavedProperties=SimpleNamespace(
                m_TexEnvs=[
                    (
                        "_MainTex",
                        SimpleNamespace(
                            m_Texture=SimpleNamespace(**main_texture),
                            m_Scale=SimpleNamespace(x=1.0, y=1.0),
                            m_Offset=SimpleNamespace(x=0.0, y=0.0),
                        ),
                    )
                ],
                m_Ints=[("unused", 1)],
                m_Floats=[("_Stencil", 3.0), ("_GradientScale", 8.0)],
                m_Colors=[
                    ("_FaceColor", {"r": 0.2, "g": 0.3, "b": 0.4, "a": 1.0}),
                    (
                        "_ClipRect",
                        {"r": -10.0, "g": -20.0, "b": 30.0, "a": 40.0},
                    ),
                ],
            )
        )
        properties = {
            "_MainTex",
            "_Color",
            "_ClipRect",
            "_Stencil",
            "_StencilComp",
            "_ColorMask",
        }

        changed = core._prune_material_saved_properties_for_raster(
            material,
            {},
            shader_kind="tmp_sprite",
            shader_properties=properties,
        )

        self.assertTrue(changed)
        saved = material.m_SavedProperties
        self.assertEqual([entry[0] for entry in saved.m_TexEnvs], ["_MainTex"])
        self.assertEqual(
            saved.m_TexEnvs[0][1]["m_Texture"],
            main_texture,
        )
        self.assertEqual(saved.m_Ints, [])
        self.assertNotIn("_GradientScale", dict(saved.m_Floats))
        self.assertEqual(dict(saved.m_Floats)["_Stencil"], 3.0)
        self.assertEqual(
            dict(saved.m_Colors)["_Color"],
            {"r": 0.2, "g": 0.3, "b": 0.4, "a": 1.0},
        )

    def test_raster_render_modes_follow_legacy_or_textcore_shape(self) -> None:
        self.assertEqual(
            core._select_tmp_raster_render_modes(
                {
                    "m_AtlasRenderMode": 7,
                    "fontCreationSettings": {"fontRenderMode": 7},
                },
                4121,
            ),
            (0, 0),
        )
        self.assertEqual(
            core._select_tmp_raster_render_modes(
                {
                    "m_AtlasRenderMode": 4169,
                    "m_CreationSettings": {"renderMode": 4169},
                },
                4121,
            ),
            (4121, 4121),
        )

    def test_custom_atlas_raster_material_resets_shader_padding(self) -> None:
        material = SimpleNamespace(
            m_SavedProperties=SimpleNamespace(
                m_TexEnvs=[
                    (
                        "_MainTex",
                        SimpleNamespace(
                            m_Texture=SimpleNamespace(m_FileID=0, m_PathID=9),
                        ),
                    )
                ],
                m_Floats=[("_Padding", 12.0)],
                m_Colors=[("_FaceColor", {"r": 1, "g": 1, "b": 1, "a": 1})],
            )
        )
        properties = {
            "_MainTex",
            "_FaceColor",
            "_Padding",
            "_ClipRect",
            "_Stencil",
            "_StencilComp",
            "_ColorMask",
        }

        self.assertTrue(
            core._prune_material_saved_properties_for_raster(
                material,
                {},
                shader_kind="tmp_bitmap_custom_atlas",
                shader_properties=properties,
            )
        )
        self.assertEqual(dict(material.m_SavedProperties.m_Floats)["_Padding"], 0.0)

    def test_raster_material_rebuilds_alpha_clip_keyword(self) -> None:
        material = SimpleNamespace(
            m_ShaderKeywords="UNDERLAY_ON UNITY_UI_ALPHACLIP",
            m_ValidKeywords=["UNDERLAY_ON"],
            m_InvalidKeywords=["GLOW_ON"],
            m_SavedProperties=SimpleNamespace(
                m_TexEnvs=[],
                m_Ints=[],
                m_Floats=[("_UseUIAlphaClip", 1.0)],
                m_Colors=[],
            ),
        )
        properties = {
            "_MainTex",
            "_Color",
            "_ClipRect",
            "_Stencil",
            "_StencilComp",
            "_ColorMask",
            "_UseUIAlphaClip",
        }

        self.assertTrue(
            core._prune_material_saved_properties_for_raster(
                material,
                {},
                shader_kind="tmp_sprite",
                shader_properties=properties,
            )
        )
        self.assertTrue(core._reset_raster_material_keywords(material, properties))
        self.assertEqual(material.m_ShaderKeywords, "UNITY_UI_ALPHACLIP")
        self.assertEqual(material.m_ValidKeywords, ["UNITY_UI_ALPHACLIP"])
        self.assertEqual(material.m_InvalidKeywords, [])

    def test_raster_texture_sampling_contract_is_bilinear_without_mips(self) -> None:
        texture = SimpleNamespace(
            m_TextureSettings=SimpleNamespace(m_FilterMode=0),
            m_MipMap=True,
            m_MipCount=4,
            m_StreamingMipmaps=True,
            m_StreamingMipmapsPriority=3,
        )

        self.assertTrue(core._apply_raster_texture_sampling_contract(texture))
        self.assertEqual(texture.m_TextureSettings.m_FilterMode, 1)
        self.assertFalse(texture.m_MipMap)
        self.assertEqual(texture.m_MipCount, 1)
        self.assertFalse(texture.m_StreamingMipmaps)
        self.assertEqual(texture.m_StreamingMipmapsPriority, 0)
        self.assertFalse(core._apply_raster_texture_sampling_contract(texture))

        with self.assertRaises(RuntimeError):
            core._apply_raster_texture_sampling_contract(
                SimpleNamespace(m_MipMap=False)
            )
        with self.assertRaises(RuntimeError):
            core._apply_raster_texture_sampling_contract(
                SimpleNamespace(
                    m_TextureSettings=SimpleNamespace(m_FilterMode=1)
                )
            )

    def test_raster_rgba32_storage_preserves_white_rgb_and_coverage(self) -> None:
        from UnityPy.export import Texture2DConverter

        class Texture:
            def __init__(self) -> None:
                self.m_TextureFormat = 1
                self.m_Width = 0
                self.m_Height = 0
                self.m_MipMap = True
                self.m_MipCount = 4
                self.m_CompleteImageSize = 0
                self.m_StreamData = SimpleNamespace(path="atlas.resS", offset=1, size=2)
                self.image_data = b""

            def set_image(
                self,
                image: Image.Image,
                *,
                target_format: int,
                mipmap_count: int,
            ) -> None:
                data, actual_format = Texture2DConverter.image_to_texture2d(
                    image,
                    target_format,
                )
                self.m_TextureFormat = actual_format
                self.m_Width, self.m_Height = image.size
                self.m_MipMap = mipmap_count > 1
                self.m_MipCount = mipmap_count
                self.m_CompleteImageSize = len(data)
                self.image_data = data
                self.m_StreamData.path = ""
                self.m_StreamData.offset = 0
                self.m_StreamData.size = 0

        source = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
        source.putpixel((1, 0), (0, 0, 0, 128))
        texture = Texture()
        try:
            core._apply_raster_rgba32_storage(texture, source)
        finally:
            source.close()

        self.assertEqual(int(texture.m_TextureFormat), 4)
        self.assertEqual(texture.m_MipCount, 1)
        self.assertFalse(texture.m_MipMap)
        self.assertEqual(texture.m_StreamData.path, "")
        self.assertEqual(
            list(texture.image_data),
            [255, 255, 255, 0, 255, 255, 255, 128],
        )

        missing_image = Image.new("RGBA", (1, 1))
        try:
            with self.assertRaises(RuntimeError):
                core._apply_raster_rgba32_storage(
                    SimpleNamespace(),
                    missing_image,
                )
        finally:
            missing_image.close()

    def test_replacement_sdf_json_and_png_are_validated_as_one_unit(self) -> None:
        valid = {
            "m_FaceInfo": {"m_FamilyName": "Test"},
            "m_AtlasWidth": 16,
            "m_AtlasHeight": 16,
            "m_AtlasPadding": 2,
            "m_GlyphTable": [
                {
                    "m_Index": 1,
                    "m_AtlasIndex": 0,
                    "m_GlyphRect": {
                        "m_X": 1,
                        "m_Y": 2,
                        "m_Width": 3,
                        "m_Height": 4,
                    },
                }
            ],
            "m_CharacterTable": [
                {"m_Unicode": 65, "m_GlyphIndex": 1},
            ],
            "m_UsedGlyphRects": [
                {"m_X": 0, "m_Y": 0, "m_Width": 8, "m_Height": 8},
            ],
            "m_FreeGlyphRects": [
                {"m_X": 8, "m_Y": 0, "m_Width": 8, "m_Height": 16},
            ],
        }
        with Image.new("L", (16, 16)) as atlas:
            core._validate_replacement_sdf_assets(valid, atlas)

            bad_dimensions = json.loads(json.dumps(valid))
            bad_dimensions["m_AtlasWidth"] = 32
            with self.assertRaisesRegex(ValueError, "do not match"):
                core._validate_replacement_sdf_assets(bad_dimensions, atlas)

            bad_rect = json.loads(json.dumps(valid))
            bad_rect["m_GlyphTable"][0]["m_GlyphRect"]["m_X"] = 15
            with self.assertRaisesRegex(ValueError, "outside"):
                core._validate_replacement_sdf_assets(bad_rect, atlas)

            missing_glyph = json.loads(json.dumps(valid))
            missing_glyph["m_CharacterTable"][0]["m_GlyphIndex"] = 99
            with self.assertRaisesRegex(ValueError, "missing glyph index"):
                core._validate_replacement_sdf_assets(missing_glyph, atlas)

            bad_padding = json.loads(json.dumps(valid))
            bad_padding["m_AtlasPadding"] = 0
            with self.assertRaisesRegex(ValueError, "padding"):
                core._validate_replacement_sdf_assets(bad_padding, atlas)

    def test_target_render_family_is_shape_driven(self) -> None:
        self.assertEqual(
            core._detect_tmp_font_render_family(
                {
                    "fontAssetType": 1,
                    "fontCreationSettings": {"fontRenderMode": 7},
                }
            ),
            "sdf",
        )
        self.assertEqual(
            core._detect_tmp_font_render_family(
                {
                    "m_AtlasRenderMode": 22,
                    "m_CreationSettings": {"renderMode": 22},
                }
            ),
            "bitmap",
        )
        for render_mode in (0, 1, 2, 3):
            with self.subTest(legacy_bitmap_render_mode=render_mode):
                self.assertEqual(
                    core._detect_tmp_font_render_family(
                        {"m_AtlasRenderMode": render_mode}
                    ),
                    "bitmap",
                )
        for render_mode in (6, 7):
            with self.subTest(legacy_sdf_render_mode=render_mode):
                self.assertEqual(
                    core._detect_tmp_font_render_family(
                        {"m_AtlasRenderMode": render_mode}
                    ),
                    "sdf",
                )
        self.assertEqual(
            core._detect_tmp_font_render_family(
                {"fontAssetType": 2, "m_AtlasRenderMode": 4118}
            ),
            "bitmap",
        )
        self.assertEqual(
            core._detect_tmp_font_render_family(
                {
                    "m_AtlasRenderMode": 4118,
                    "m_CreationSettings": {"renderMode": 6},
                }
            ),
            "bitmap",
        )
        for render_mode in (4138, 16422, 16426, 4165, 4169):
            with self.subTest(render_mode=render_mode):
                self.assertEqual(
                    core._detect_tmp_font_render_family(
                        {"m_AtlasRenderMode": render_mode}
                    ),
                    "sdf",
                )
        self.assertEqual(
            core._detect_tmp_font_render_family({"m_AtlasRenderMode": 0x1030}),
            "conflict",
        )
        self.assertIsNone(
            core._detect_tmp_font_render_family({"m_AtlasRenderMode": 4})
        )

    def test_il2cpp_metadata_wins_over_stale_managed_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "Game_Data"
            (data_path / "Managed").mkdir(parents=True)
            metadata = (
                data_path
                / "il2cpp_data"
                / "Metadata"
                / "global-metadata.dat"
            )
            metadata.parent.mkdir(parents=True)
            metadata.write_bytes(b"metadata")

            self.assertEqual(core.get_compile_method(str(data_path)), "Il2cpp")
            self.assertEqual(exporter.get_compile_method(str(data_path)), "Il2cpp")

            metadata.unlink()
            self.assertEqual(core.get_compile_method(str(data_path)), "Mono")
            self.assertEqual(exporter.get_compile_method(str(data_path)), "Mono")

    def test_il2cpp_dummy_dll_cache_stays_outside_game_and_is_reused(self) -> None:
        class FakeGenerator:
            def __init__(self, version: str):
                self.version = version
                self.loaded: list[bytes] = []

            def load_dll(self, data: bytes) -> None:
                self.loaded.append(data)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_path = root / "Game"
            data_path = game_path / "Game_Data"
            metadata = (
                data_path
                / "il2cpp_data"
                / "Metadata"
                / "global-metadata.dat"
            )
            metadata.parent.mkdir(parents=True)
            metadata.write_bytes(b"metadata")
            (game_path / "GameAssembly.dll").write_bytes(b"assembly")
            dumper = root / "tools" / "Il2CppDumper.exe"
            dumper.parent.mkdir()
            dumper.write_bytes(b"dumper")
            cache_root = root / "external-cache"

            def fake_run(command, **kwargs):
                output_dir = Path(command[3])
                dummy_dir = output_dir / "DummyDll"
                dummy_dir.mkdir()
                (dummy_dir / "Unity.TextMeshPro.dll").write_bytes(b"dummy")
                return SimpleNamespace(returncode=0, stdout="ok", stderr="")

            with (
                patch.object(runtime, "TypeTreeGenerator", FakeGenerator),
                patch.object(runtime.subprocess, "run", side_effect=fake_run) as run,
            ):
                first = runtime.create_type_tree_generator(
                    "2019.4.0f1",
                    str(game_path),
                    str(data_path),
                    "Il2cpp",
                    cache_root=str(cache_root),
                    dumper_path=str(dumper),
                )
                second = runtime.create_type_tree_generator(
                    "2019.4.0f1",
                    str(game_path),
                    str(data_path),
                    "Il2cpp",
                    cache_root=str(cache_root),
                    dumper_path=str(dumper),
                )

            self.assertEqual(run.call_count, 1)
            self.assertEqual(first.loaded, [b"dummy"])
            self.assertEqual(second.loaded, [b"dummy"])
            self.assertFalse((data_path / "Managed").exists())
            self.assertFalse((data_path / "Managed_").exists())
            self.assertEqual(
                len(list((cache_root / "il2cpp_cache").glob("*/manifest.json"))),
                1,
            )

    def test_material_main_texture_key_resolves_external_file_id(self) -> None:
        external = SimpleNamespace(path="sharedassets0.assets")
        assets_file = SimpleNamespace(
            name="resources.assets",
            externals=[
                SimpleNamespace(path="globalgamemanagers.assets"),
                SimpleNamespace(path="unity default resources"),
                external,
            ],
        )
        material = SimpleNamespace(
            m_SavedProperties=SimpleNamespace(
                m_TexEnvs=[
                    (
                        "_MainTex",
                        {"m_Texture": {"m_FileID": 3, "m_PathID": 154}},
                    )
                ]
            )
        )

        self.assertEqual(
            core._resolve_material_main_texture_key(
                assets_file,
                "resources.assets",
                material,
            ),
            core._make_assets_object_key("sharedassets0.assets", 154),
        )

    def test_material_main_texture_key_accepts_negative_path_id(self) -> None:
        assets_file = SimpleNamespace(name="CAB-font", externals=[])
        material = SimpleNamespace(
            m_SavedProperties=SimpleNamespace(
                m_TexEnvs=[
                    (
                        "_MainTex",
                        {
                            "m_Texture": {
                                "m_FileID": 0,
                                "m_PathID": -6690135977439950194,
                            }
                        },
                    )
                ]
            )
        )

        self.assertEqual(
            core._resolve_material_main_texture_key(
                assets_file,
                "CAB-font",
                material,
            ),
            core._make_assets_object_key("CAB-font", -6690135977439950194),
        )

    def test_outer_object_identity_prevents_bundle_collisions(self) -> None:
        first = core._make_outer_assets_object_key(
            str(ROOT / "a.bundle"),
            "CAB-font",
            -7,
        )
        second = core._make_outer_assets_object_key(
            str(ROOT / "b.bundle"),
            "CAB-font",
            -7,
        )

        self.assertNotEqual(first, second)

    def test_material_texture_identity_follows_external_cab(self) -> None:
        outer_key = core._normalize_asset_file_key(str(ROOT / "hash.bundle"))
        index = {
            "relpath_to_keys": {},
            "basename_to_keys": {},
            "relpath_by_key": {},
            "path_by_key": {outer_key: str(ROOT / "hash.bundle")},
            "internal_name_to_keys": {"cab-atlas": [outer_key]},
            "internal_name_index_complete": True,
        }
        source = SimpleNamespace(
            name="CAB-font",
            externals=[SimpleNamespace(path="archive:/CAB-atlas")],
        )
        material = SimpleNamespace(
            m_SavedProperties=SimpleNamespace(
                m_TexEnvs=[
                    (
                        "_MainTex",
                        {"m_Texture": {"m_FileID": 1, "m_PathID": -7}},
                    )
                ]
            )
        )

        self.assertEqual(
            core._resolve_material_main_texture_identity(
                source,
                "CAB-font",
                str(ROOT / "font.bundle"),
                material,
                source_bundle_signature=None,
                asset_file_index=index,
            ),
            core._make_outer_assets_object_key(outer_key, "CAB-atlas", -7),
        )

    def test_material_main_texture_can_rebind_secondary_atlas(self) -> None:
        material = SimpleNamespace(
            m_SavedProperties=SimpleNamespace(
                m_TexEnvs=[
                    (
                        "_MainTex",
                        {"m_Texture": {"m_FileID": 2, "m_PathID": 99}},
                    )
                ]
            )
        )

        self.assertTrue(core._set_material_main_texture_ref(material, 2, -7))
        self.assertEqual(core._material_main_texture_ref(material), (2, -7))

    def test_asset_index_resolves_inner_cab_to_hash_named_bundle(self) -> None:
        bundle_key = core._normalize_asset_file_key(str(ROOT / "hash.bundle"))
        index = {
            "relpath_to_keys": {},
            "basename_to_keys": {},
            "relpath_by_key": {},
            "internal_name_to_keys": {"cab-atlas": [bundle_key]},
            "internal_name_index_complete": True,
        }

        self.assertEqual(
            core._collect_asset_file_index_matches(index, "archive:/CAB-atlas"),
            [bundle_key],
        )
        self.assertEqual(
            exporter._collect_asset_file_index_matches(
                index,
                "archive:/CAB-atlas",
            ),
            [bundle_key],
        )

    def test_ambiguous_asset_match_is_rejected(self) -> None:
        first = core._normalize_asset_file_key(str(ROOT / "a" / "same.bundle"))
        second = core._normalize_asset_file_key(str(ROOT / "b" / "same.bundle"))
        self.assertIsNone(
            core._choose_asset_file_match(
                {"path_by_key": {first: first, second: second}},
                [first, second],
                current_file_key=None,
                reference_desc="same.bundle",
            )
        )
        self.assertIsNone(
            exporter._choose_asset_file_match(
                {"path_by_key": {first: first, second: second}},
                [first, second],
                current_file_key=None,
                reference_desc="same.bundle",
            )
        )

    def test_material_atlas_reconciliation_includes_earlier_files(self) -> None:
        atlas_key = core._make_assets_object_key("sharedassets0.assets", 157)
        payload = {"w": 4096, "h": 4096}
        resources_key = str(ROOT / "Game_Data" / "resources.assets")
        shared_key = str(ROOT / "Game_Data" / "sharedassets0.assets")

        buckets = core._build_material_atlas_reconciliation_buckets(
            [resources_key, shared_key],
            {atlas_key: payload},
        )

        normalized_resources = core._normalize_asset_file_key(resources_key)
        normalized_shared = core._normalize_asset_file_key(shared_key)
        self.assertIs(buckets[normalized_resources][atlas_key], payload)
        self.assertIs(buckets[normalized_shared][atlas_key], payload)

    def test_sdf_material_payload_keeps_style_and_updates_atlas_contract(self) -> None:
        payload = core._build_sdf_material_payload(
            atlas_width=4096,
            atlas_height=2048,
            material_data={
                "m_SavedProperties": {
                    "m_Floats": [
                        ["_GradientScale", 8.0],
                        ["_TextureWidth", 1024.0],
                        ["_LightAngle", 1.25],
                        ["_WeightBold", 0.75],
                    ],
                    "m_Colors": [
                        ["_FaceColor", {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0}]
                    ],
                }
            },
            replacement_is_sdf=True,
            force_raster=False,
            use_game_material=True,
            outline_ratio=1.0,
            replacement_padding=7.0,
            replacement_font="Test",
            source_entry="bundle|CAB|1",
        )

        self.assertEqual(payload["gs"], 8.0)
        self.assertTrue(payload["preserve_game_style"])
        self.assertTrue(payload["recompute_shader_ratios"])
        self.assertEqual(payload["float_overrides"], {})
        self.assertEqual(payload["color_overrides"], {})

    def test_material_style_is_preserved_and_all_scale_ratios_are_recomputed(self) -> None:
        original_face_color = {"r": 0.2, "g": 0.3, "b": 0.4, "a": 1.0}
        material = SimpleNamespace(
            m_ShaderKeywords="GLOW_ON UNDERLAY_ON",
            m_ValidKeywords=[],
            m_SavedProperties=SimpleNamespace(
                m_Floats=[
                    ("_GradientScale", 10.0),
                    ("_TextureWidth", 1024.0),
                    ("_TextureHeight", 1024.0),
                    ("_FaceDilate", 0.1),
                    ("_OutlineWidth", 0.2),
                    ("_OutlineSoftness", 0.05),
                    ("_WeightNormal", 0.0),
                    ("_WeightBold", 0.75),
                    ("_GlowOffset", 0.1),
                    ("_GlowOuter", 0.2),
                    ("_UnderlayOffsetX", 0.2),
                    ("_UnderlayOffsetY", -0.3),
                    ("_UnderlayDilate", 0.1),
                    ("_UnderlaySoftness", 0.2),
                    ("_LightAngle", 0.25),
                    ("_ScaleRatioA", 0.1),
                    ("_ScaleRatioB", 0.1),
                    ("_ScaleRatioC", 0.1),
                ],
                m_Colors=[("_FaceColor", original_face_color.copy())],
            ),
        )
        payload = {
            "w": 4096,
            "h": 2048,
            "gs": 8.0,
            "float_overrides": {
                "_GradientScale": 99.0,
                "_WeightBold": 9.0,
                "_LightAngle": 9.0,
            },
            "color_overrides": {
                "_FaceColor": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}
            },
            "outline_ratio": 1.0,
            "preserve_game_style": True,
            "recompute_shader_ratios": True,
        }

        self.assertTrue(core._apply_material_replacement_to_object(material, payload))
        floats = dict(material.m_SavedProperties.m_Floats)

        self.assertEqual(floats["_GradientScale"], 8.0)
        self.assertEqual(floats["_TextureWidth"], 4096.0)
        self.assertEqual(floats["_TextureHeight"], 2048.0)
        self.assertEqual(floats["_WeightBold"], 0.75)
        self.assertEqual(floats["_LightAngle"], 0.25)
        self.assertAlmostEqual(floats["_ScaleRatioA"], 0.875)
        self.assertAlmostEqual(floats["_ScaleRatioB"], 0.6234375)
        self.assertAlmostEqual(floats["_ScaleRatioC"], 0.6234375)
        self.assertEqual(
            material.m_SavedProperties.m_Colors[0][1],
            original_face_color,
        )

    def test_ratios_off_keyword_sets_existing_scale_ratios_to_one(self) -> None:
        material = SimpleNamespace(
            m_ShaderKeywords="RATIOS_OFF",
            m_ValidKeywords=[],
        )
        floats = [
            ("_GradientScale", 8.0),
            ("_FaceDilate", 0.0),
            ("_OutlineWidth", 0.0),
            ("_OutlineSoftness", 0.0),
            ("_ScaleRatioA", 0.25),
            ("_ScaleRatioB", 0.25),
            ("_ScaleRatioC", 0.25),
        ]

        self.assertTrue(core._recompute_tmp_shader_scale_ratios(material, floats))
        ratios = dict(floats)
        self.assertEqual(ratios["_ScaleRatioA"], 1.0)
        self.assertEqual(ratios["_ScaleRatioB"], 1.0)
        self.assertEqual(ratios["_ScaleRatioC"], 1.0)

    def test_only_singular_atlas_reference_is_detected(self) -> None:
        data = {
            "m_FaceInfo": {},
            "m_GlyphTable": [{"m_Index": 1}],
            "m_CharacterTable": [{"m_Unicode": 65, "m_GlyphIndex": 1}],
            "m_AtlasTexture": {"m_FileID": 2, "m_PathID": 99},
        }
        info = core.inspect_tmp_font_schema(data, unity_version="2021.3.0f1")
        self.assertTrue(info["is_tmp"])
        self.assertEqual(info["version"], "new")
        self.assertEqual((info["atlas_file_id"], info["atlas_path_id"]), (2, 99))
        export_info = exporter.inspect_tmp_font_schema(data, unity_version="2021.3.0f1")
        self.assertEqual(export_info["atlas_path_id"], 99)

    def test_first_negative_atlas_path_id_is_not_skipped(self) -> None:
        data = {
            "m_FaceInfo": {},
            "m_GlyphTable": [{"m_Index": 1}],
            "m_CharacterTable": [{"m_Unicode": 65, "m_GlyphIndex": 1}],
            "m_AtlasTextures": [
                {"m_FileID": 0, "m_PathID": -6690135977439950194},
                {"m_FileID": 0, "m_PathID": 4044705090734623374},
            ],
        }

        info = core.inspect_tmp_font_schema(data, unity_version="2022.3.20f1")
        export_info = exporter.inspect_tmp_font_schema(
            data,
            unity_version="2022.3.20f1",
        )

        self.assertEqual(info["atlas_path_id"], -6690135977439950194)
        self.assertEqual(export_info["atlas_path_id"], -6690135977439950194)

    def test_tmp_detection_requires_a_coherent_font_asset_shape(self) -> None:
        for accidental_shape in (
            {"m_FaceInfo": {}},
            {"atlas": {"m_FileID": 0, "m_PathID": 7}},
            {"m_GlyphTable": [{"m_Index": 1}]},
        ):
            with self.subTest(accidental_shape=accidental_shape):
                self.assertFalse(
                    core.inspect_tmp_font_schema(accidental_shape)["is_tmp"]
                )
                self.assertFalse(
                    exporter.inspect_tmp_font_schema(accidental_shape)["is_tmp"]
                )

        empty_new = {
            "m_FaceInfo": {},
            "m_GlyphTable": [],
            "m_CharacterTable": [],
            "m_AtlasTextures": [{"m_FileID": 0, "m_PathID": 7}],
        }
        empty_old = {
            "m_fontInfo": {},
            "m_glyphInfoList": [],
            "atlas": {"m_FileID": 0, "m_PathID": 8},
            "material": {"m_FileID": 0, "m_PathID": 9},
        }
        self.assertTrue(core.inspect_tmp_font_schema(empty_new)["is_tmp"])
        self.assertTrue(core.inspect_tmp_font_schema(empty_old)["is_tmp"])

    def test_all_atlas_refs_are_collected_before_single_atlas_collapse(self) -> None:
        data = {
            "m_AtlasTextures": [
                {"m_FileID": 0, "m_PathID": -7},
                {"m_FileID": 1, "m_PathID": 8},
            ],
            "m_AtlasTexture": {"m_FileID": 0, "m_PathID": -7},
            "atlas": {"m_FileID": 2, "m_PathID": 9},
        }

        self.assertEqual(
            [core._atlas_ref_ids(ref) for ref in core._all_valid_atlas_refs(data)],
            [(0, -7), (1, 8), (2, 9)],
        )

    def test_shared_atlas_owner_validation_rejects_partial_or_conflicting_edits(
        self,
    ) -> None:
        base_records = [
            {
                "atlas_identity": "outer|CAB-tex|-7",
                "owner_identity": "outer|CAB-a|1",
                "owner_label": "Font A",
                "lookup_key": ("SDF", "font.bundle", "CAB-a", 1),
                "replacement_font": "NanumGothic",
            },
            {
                "atlas_identity": "outer|CAB-tex|-7",
                "owner_identity": "outer|CAB-a|2",
                "owner_label": "Font B",
                "lookup_key": ("SDF", "font.bundle", "CAB-a", 2),
                "replacement_font": "",
            },
        ]

        with self.assertRaisesRegex(ValueError, "Unsafe partial replacement"):
            core._validate_shared_atlas_owner_records(base_records)

        base_records[1]["replacement_font"] = "NanumGothic"
        core._validate_shared_atlas_owner_records(base_records)

        base_records[1]["replacement_font"] = "Mulmaru"
        with self.assertRaisesRegex(ValueError, "different fonts"):
            core._validate_shared_atlas_owner_records(base_records)

    def test_shared_atlas_preflight_only_parses_tmp_fontasset_payloads(
        self,
    ) -> None:
        def make_object(namespace: str, class_name: str) -> SimpleNamespace:
            script = SimpleNamespace(
                m_Namespace=namespace,
                m_ClassName=class_name,
                m_AssemblyName="Unity.TextMeshPro",
            )
            script_ref = SimpleNamespace(m_PathID=7, read=lambda: script)
            assets_file = SimpleNamespace(
                name="CAB-test",
                unity_version="2022.3.62f2",
            )
            return SimpleNamespace(
                type=SimpleNamespace(name="MonoBehaviour"),
                assets_file=assets_file,
                path_id=11,
                parse_monobehaviour_head=lambda: SimpleNamespace(
                    m_Script=script_ref
                ),
            )

        replacement_lookup = {
            ("SDF", "game.assets", "CAB-test", 99): "NanumGothic"
        }
        unrelated = make_object("UnityEngine.Localization", "Locale")
        unrelated_env = SimpleNamespace(objects=[unrelated])
        with (
            patch.object(core, "_read_bundle_signature", return_value=None),
            patch.object(core, "load_unitypy", return_value=unrelated_env),
            patch.object(core, "close_unitypy_env"),
            patch.object(
                core,
                "_safe_parse_as_dict",
                side_effect=AssertionError("unrelated payload was parsed"),
            ) as parse_payload,
        ):
            core._preflight_shared_atlas_owners(
                ["game.assets"],
                replacement_lookup,
                None,
                {},
            )
        parse_payload.assert_not_called()

        tmp_object = make_object("TMPro", "TMP_FontAsset")
        tmp_env = SimpleNamespace(objects=[tmp_object])
        with (
            patch.object(core, "_read_bundle_signature", return_value=None),
            patch.object(core, "load_unitypy", return_value=tmp_env),
            patch.object(core, "close_unitypy_env"),
            patch.object(
                core,
                "_safe_parse_as_dict",
                side_effect=RuntimeError("payload unavailable"),
            ) as parse_payload,
        ):
            with self.assertRaisesRegex(ValueError, "TMP payload"):
                core._preflight_shared_atlas_owners(
                    ["game.assets"],
                    replacement_lookup,
                    None,
                    {},
                )
        parse_payload.assert_called_once_with(tmp_object)

        self.assertTrue(
            core._is_tmp_fontasset_script_identity(
                (
                    "UnityEngine.TextCore.Text",
                    "FontAsset",
                    "UnityEngine.TextCoreTextEngineModule",
                )
            )
        )

        null_script_object = make_object("TMPro", "TMP_FontAsset")
        null_script_object.parse_monobehaviour_head = lambda: SimpleNamespace(
            m_Script=SimpleNamespace(m_PathID=0)
        )
        with self.assertRaisesRegex(ValueError, "reference is null"):
            core._read_monobehaviour_script_identity(null_script_object)

    def test_monoscript_identity_resolves_an_external_addressables_cab(
        self,
    ) -> None:
        script = SimpleNamespace(
            m_Namespace="TMPro",
            m_ClassName="TMP_FontAsset",
            m_AssemblyName="Unity.TextMeshPro.dll",
        )
        external_script_object = SimpleNamespace(
            type=SimpleNamespace(name="MonoScript"),
            path_id=77,
            assets_file=SimpleNamespace(name="CAB-font"),
            read=lambda: script,
        )
        external_env = SimpleNamespace(objects=[external_script_object])
        source_assets_file = SimpleNamespace(name="CAB-prefab")
        direct_reads: list[bool] = []

        def read_ambiguous_external() -> SimpleNamespace:
            direct_reads.append(True)
            return SimpleNamespace(
                m_Namespace="Wrong.Namespace",
                m_ClassName="WrongFontAsset",
                m_AssemblyName="Wrong.Assembly",
            )

        script_ref = SimpleNamespace(
            m_FileID=1,
            m_PathID=77,
            read=read_ambiguous_external,
        )
        font_object = SimpleNamespace(
            assets_file=source_assets_file,
            parse_monobehaviour_head=lambda: SimpleNamespace(
                m_Script=script_ref
            ),
        )
        target_key = core._normalize_asset_file_key("font.bundle")
        assert target_key is not None
        asset_index = {
            "path_by_key": {target_key: "font.bundle"},
        }
        identity_cache: dict[
            tuple[str, str, int], tuple[str, str, str]
        ] = {}

        with (
            patch.object(
                core,
                "_resolve_target_assets_name",
                return_value="CAB-font",
            ),
            patch.object(
                core,
                "_resolve_target_outer_file_key",
                return_value=target_key,
            ),
            patch.object(
                core,
                "load_unitypy",
                return_value=external_env,
            ) as load_env,
            patch.object(core, "close_unitypy_env") as close_env,
        ):
            identity = core._read_monobehaviour_script_identity(
                font_object,
                current_outer_key="prefab.bundle",
                source_bundle_signature="UnityFS",
                asset_file_index=asset_index,
                identity_cache=identity_cache,
            )
            cached_identity = core._read_monobehaviour_script_identity(
                font_object,
                current_outer_key="prefab.bundle",
                source_bundle_signature="UnityFS",
                asset_file_index=asset_index,
                identity_cache=identity_cache,
            )

        self.assertEqual(
            identity,
            ("TMPro", "TMP_FontAsset", "Unity.TextMeshPro.dll"),
        )
        self.assertEqual(cached_identity, identity)
        self.assertEqual(len(identity_cache), 1)
        self.assertEqual(direct_reads, [])
        load_env.assert_called_once_with("font.bundle")
        close_env.assert_called_once_with(external_env)

        broken_script_object = SimpleNamespace(
            type=SimpleNamespace(name="MonoScript"),
            path_id=77,
            assets_file=SimpleNamespace(name="CAB-font"),
            read=lambda: (_ for _ in ()).throw(
                ValueError("broken MonoScript")
            ),
        )
        broken_env = SimpleNamespace(objects=[broken_script_object])
        with (
            patch.object(
                core,
                "_resolve_target_assets_name",
                return_value="CAB-font",
            ),
            patch.object(
                core,
                "_resolve_target_outer_file_key",
                return_value=target_key,
            ),
            patch.object(core, "load_unitypy", return_value=broken_env),
            patch.object(core, "close_unitypy_env") as close_broken_env,
        ):
            with self.assertRaisesRegex(ValueError, "broken MonoScript"):
                core._read_monobehaviour_script_identity(
                    font_object,
                    current_outer_key="prefab.bundle",
                    source_bundle_signature="UnityFS",
                    asset_file_index=asset_index,
                    identity_cache={},
                )
        close_broken_env.assert_called_once_with(broken_env)

    def test_new_schema_fields_override_old_unity_hint(self) -> None:
        data = {"m_GlyphTable": [], "m_CharacterTable": [], "m_AtlasWidth": 64}
        self.assertEqual(core.detect_tmp_version(data, "2018.3.14f1"), "new")
        self.assertEqual(exporter.detect_tmp_version(data, "2018.3.14f1"), "new")

    def test_modern_glyph_class_definition_is_preserved(self) -> None:
        data = {
            "m_GlyphTable": [
                {
                    "m_Index": "7",
                    "m_AtlasIndex": "0",
                    "m_ClassDefinitionType": "3",
                }
            ],
            "m_CharacterTable": [],
            "m_AtlasWidth": 64,
        }

        normalized = core.normalize_sdf_data(data)

        self.assertEqual(normalized["m_GlyphTable"][0]["m_ClassDefinitionType"], 3)
        self.assertEqual(data["m_GlyphTable"][0]["m_ClassDefinitionType"], "3")

    def test_cross_version_nested_typetree_defaults_are_filled(self) -> None:
        data = {
            "m_FaceInfo": {"m_PointSize": "16"},
            "m_GlyphTable": [
                {
                    "m_Index": "7",
                    "m_AtlasIndex": "0",
                    "m_GlyphRect": {
                        "m_X": "1",
                        "m_Y": "2",
                        "m_Width": "3",
                        "m_Height": "4",
                    },
                }
            ],
            "m_CharacterTable": [
                {"m_ElementType": "1", "m_Unicode": "65", "m_GlyphIndex": "7"}
            ],
            "m_AtlasWidth": 64,
            "m_FontFeatureTable": {
                "m_GlyphPairAdjustmentRecords": [
                    {
                        "m_FirstAdjustmentRecord": {
                            "m_GlyphIndex": "7",
                            "m_GlyphValueRecord": {"m_XAdvance": -1.25},
                        },
                        "m_SecondAdjustmentRecord": {
                            "m_GlyphIndex": "9",
                            "m_GlyphValueRecord": {},
                        },
                    }
                ]
            },
        }

        normalized = core.normalize_sdf_data(data)

        self.assertEqual(normalized["m_FaceInfo"]["m_FaceIndex"], 0)
        self.assertEqual(normalized["m_FaceInfo"]["m_UnitsPerEM"], 0)
        self.assertEqual(normalized["m_GlyphTable"][0]["m_ClassDefinitionType"], 0)
        pair = normalized["m_FontFeatureTable"][
            "m_GlyphPairAdjustmentRecords"
        ][0]
        self.assertEqual(pair["m_FeatureLookupFlags"], 0)
        self.assertEqual(pair["m_FirstAdjustmentRecord"]["m_GlyphIndex"], 7)
        self.assertEqual(
            pair["m_FirstAdjustmentRecord"]["m_GlyphValueRecord"],
            {
                "m_XPlacement": 0.0,
                "m_YPlacement": 0.0,
                "m_XAdvance": -1.25,
                "m_YAdvance": 0.0,
            },
        )

        numeric_face = core.normalize_sdf_data(
            {
                "m_FaceInfo": {"m_FaceIndex": "2", "m_UnitsPerEM": "2048"},
                "m_GlyphTable": [],
                "m_CharacterTable": [],
                "m_AtlasWidth": 64,
            }
        )["m_FaceInfo"]
        self.assertEqual(numeric_face["m_FaceIndex"], 2)
        self.assertEqual(numeric_face["m_UnitsPerEM"], 2048)

    def test_legacy_kerning_is_canonicalized_and_migrated(self) -> None:
        data = {
            "m_FaceInfo": {},
            "m_GlyphTable": [
                {"m_Index": 7, "m_AtlasIndex": 0},
                {"m_Index": 9, "m_AtlasIndex": 0},
            ],
            "m_CharacterTable": [
                {"m_Unicode": 65, "m_GlyphIndex": 7},
                {"m_Unicode": 86, "m_GlyphIndex": 9},
            ],
            "m_AtlasWidth": 64,
            "m_KerningTable": {
                "kerningPairs": [
                    {
                        "AscII_Left": "65",
                        "AscII_Right": 86,
                        "XadvanceOffset": "-1.5",
                        "m_IgnoreSpacingAdjustments": "true",
                    }
                ]
            },
            "m_FontFeatureTable": {"m_GlyphPairAdjustmentRecords": []},
        }

        normalized = core.normalize_sdf_data(data)

        legacy = normalized["m_KerningTable"]["kerningPairs"][0]
        self.assertEqual(
            normalized["m_kerningInfo"]["kerningPairs"],
            normalized["m_KerningTable"]["kerningPairs"],
        )
        self.assertIsNot(
            normalized["m_kerningInfo"],
            normalized["m_KerningTable"],
        )
        self.assertEqual((legacy["AscII_Left"], legacy["m_FirstGlyph"]), (65, 65))
        self.assertEqual((legacy["AscII_Right"], legacy["m_SecondGlyph"]), (86, 86))
        self.assertEqual(legacy["XadvanceOffset"], -1.5)
        self.assertEqual(legacy["xOffset"], -1.5)
        self.assertEqual(legacy["m_FirstGlyphAdjustments"]["xAdvance"], -1.5)
        self.assertTrue(legacy["m_IgnoreSpacingAdjustments"])

        modern = normalized["m_FontFeatureTable"][
            "m_GlyphPairAdjustmentRecords"
        ][0]
        self.assertEqual(
            modern["m_FirstAdjustmentRecord"]["m_GlyphIndex"],
            7,
        )
        self.assertEqual(
            modern["m_SecondAdjustmentRecord"]["m_GlyphIndex"],
            9,
        )
        self.assertEqual(
            modern["m_FirstAdjustmentRecord"]["m_GlyphValueRecord"][
                "m_XAdvance"
            ],
            -1.5,
        )
        self.assertEqual(modern["m_FeatureLookupFlags"], 0x100)

        conflicting = json.loads(json.dumps(data))
        conflicting["m_KerningTable"]["kerningPairs"][0][
            "m_FirstGlyph"
        ] = 66
        with self.assertRaisesRegex(ValueError, "Conflicting TMP kerning glyph"):
            core.normalize_sdf_data(conflicting)

        inverse = json.loads(json.dumps(data))
        inverse["m_kerningInfo"] = inverse.pop("m_KerningTable")
        inverse_normalized = core.normalize_sdf_data(inverse)
        self.assertEqual(
            inverse_normalized["m_KerningTable"]["kerningPairs"],
            inverse_normalized["m_kerningInfo"]["kerningPairs"],
        )

    def test_sdf_defaults_and_baked_assets_never_use_a_bitmap_render_mode(
        self,
    ) -> None:
        normalized = core.normalize_sdf_data(
            {
                "m_fontInfo": {
                    "AtlasWidth": 64,
                    "AtlasHeight": 64,
                    "Padding": 5,
                },
                "m_glyphInfoList": [{"id": 65}],
                "atlas": {"m_FileID": 0, "m_PathID": 1},
            }
        )
        self.assertEqual(normalized["m_AtlasRenderMode"], 4169)

        for asset_path in (ROOT / "KR_ASSETS").glob("**/Mulmaru SDF.json"):
            with self.subTest(asset_path=asset_path):
                asset = json.loads(asset_path.read_text(encoding="utf-8"))
                self.assertEqual(asset["m_AtlasRenderMode"], 4169)
                self.assertEqual(asset["m_CreationSettings"]["renderMode"], 4169)

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

    def test_old_to_new_matches_tmp_migration_rounding(self) -> None:
        glyphs, chars = core.convert_glyphs_old_to_new(
            [
                {
                    "id": 65,
                    "x": 1.9,
                    "y": 1.0,
                    "width": 1.5,
                    "height": 1.5,
                    "xOffset": 0,
                    "yOffset": 0,
                    "xAdvance": 2,
                    "scale": 1,
                }
            ],
            atlas_height=64,
        )

        self.assertEqual(
            glyphs[0]["m_GlyphRect"],
            {"m_X": 1, "m_Y": 61, "m_Width": 2, "m_Height": 2},
        )
        self.assertEqual(chars[0]["m_Unicode"], 65)

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

    def test_legacy_font_creation_settings_font_size_is_synchronized(self) -> None:
        settings = {
            "fontSize": 12,
            "fontPadding": 3,
            "fontAtlasWidth": 512,
            "fontAtlasHeight": 512,
            "fontRenderMode": 22,
        }

        core._sync_creation_settings_payload(
            settings,
            2048,
            1024,
            7,
            90,
        )

        self.assertEqual(
            settings,
            {
                "fontSize": 90,
                "fontPadding": 7,
                "fontAtlasWidth": 2048,
                "fontAtlasHeight": 1024,
                "fontRenderMode": 22,
            },
        )

        self.assertEqual(
            core.extract_tmp_atlas_padding(
                {"fontCreationSettings": {"fontPadding": 15}}
            ),
            15.0,
        )

        modern_settings = {"renderMode": 22}
        core._sync_creation_settings_payload(
            modern_settings,
            2048,
            1024,
            7,
            90,
            render_mode=4118,
        )
        self.assertEqual(modern_settings["renderMode"], 4118)

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
        legacy_kerning = {"kerningPairs": [{"old": 3}]}
        core._sync_existing_record_table(legacy_kerning, None)
        self.assertEqual(legacy_kerning, {"kerningPairs": []})

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
            "m_AtlasPopulationMode": 0,
            "InternalDynamicOS": False,
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

    def test_partial_typetree_edit_requires_byte_stable_prefix(self) -> None:
        class FakeObject:
            byte_size = 10
            reader = SimpleNamespace(endian="<")

            def get_raw_data(self) -> bytes:
                return b"prefixTAIL"

            def save_typetree(self, value, writer) -> None:
                writer.write_bytes(value)

        obj = FakeObject()
        core._verify_typetree_prefix_roundtrip(obj, b"prefix", 6)
        with self.assertRaisesRegex(ValueError, "not byte-stable"):
            core._verify_typetree_prefix_roundtrip(obj, b"PREFIX", 6)

    def test_changed_object_manifest_uses_exact_cab_signed_path_and_bytes(
        self,
    ) -> None:
        changed = SimpleNamespace(
            assets_file=SimpleNamespace(name="CAB-font"),
            path_id=-77,
            data=b"patched-object",
        )
        manifest = core._collect_changed_object_manifest(
            SimpleNamespace(objects=[changed])
        )

        saved = SimpleNamespace(
            assets_file=SimpleNamespace(name="CAB-font"),
            path_id=-77,
            data=b"patched-object",
        )
        core._validate_object_manifest(SimpleNamespace(objects=[saved]), manifest)

        saved.data = b"corrupt-object"
        with self.assertRaisesRegex(ValueError, "saved object bytes differ"):
            core._validate_object_manifest(
                SimpleNamespace(objects=[saved]),
                manifest,
            )

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

        def read_scalar(child, reader, config):
            return reader.read_int()

        obj = FakeObject()
        with patch(
            "UnityPy.helpers.TypeTreeHelper.read_value",
            side_effect=read_scalar,
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

    def test_binary_texture_fallback_honors_endian_and_requires_all_offsets(
        self,
    ) -> None:
        children = [
            SimpleNamespace(m_Name="m_Width", m_Type="int"),
            SimpleNamespace(m_Name="m_Height", m_Type="int"),
            SimpleNamespace(m_Name="m_CompleteImageSize", m_Type="unsigned int"),
            SimpleNamespace(m_Name="image data", m_Type="TypelessData"),
        ]
        original = (
            struct.pack(">iii", 2, 2, 4)
            + struct.pack(">i", 4)
            + b"OLD!"
            + (b"TAIL" * 10)
        )

        class FakeObject:
            reader = SimpleNamespace(endian=">")
            assets_file = SimpleNamespace(mark_changed=lambda: None)
            path_id = 100

            def __init__(self, root_children) -> None:
                self.root_children = root_children
                self.data = None

            def get_raw_data(self) -> bytes:
                return original

            def _get_typetree_node(self):
                return SimpleNamespace(m_Children=self.root_children)

            def set_raw_data(self, data) -> None:
                self.data = data

        def read_scalar(child, reader, config):
            return reader.read_int()

        with patch(
            "UnityPy.helpers.TypeTreeHelper.read_value",
            side_effect=read_scalar,
        ):
            obj = FakeObject(children)
            self.assertTrue(
                core._binary_patch_texture2d(
                    obj,
                    image_data=b"ABCDEF",
                    width=7,
                    height=8,
                    lang="en",
                )
            )
            saved = b"".join(obj.data.iter_chunks())
            self.assertEqual(struct.unpack_from(">iii", saved, 0), (7, 8, 6))
            self.assertEqual(struct.unpack_from(">i", saved, 12)[0], 6)
            obj.data.cleanup()

            missing_height = [child for child in children if child.m_Name != "m_Height"]
            self.assertFalse(
                core._binary_patch_texture2d(
                    FakeObject(missing_height),
                    image_data=b"ABCDEF",
                    width=7,
                    height=8,
                    lang="en",
                )
            )

            unsafe_suffix = [
                *children,
                SimpleNamespace(m_Name="m_FutureField", m_Type="int"),
            ]
            self.assertFalse(
                core._binary_patch_texture2d(
                    FakeObject(unsafe_suffix),
                    image_data=b"ABCDEF",
                    width=7,
                    height=8,
                    lang="en",
                )
            )

    def test_static_font_cache_keeps_path_not_decoded_atlas(self) -> None:
        core._load_font_assets_cached.cache_clear()
        cached = core._load_font_assets_cached(str(ROOT), "NanumGothic", False, None)
        self.assertNotIn("sdf_atlas", cached)
        self.assertTrue(Path(cached["sdf_atlas_path"]).is_file())
        loaded = core.load_font_assets("NanumGothic", generate_sdf=False)
        self.assertIsInstance(loaded["sdf_atlas"], Image.Image)
        loaded["sdf_atlas"].close()

    def test_builtin_padding_variant_never_rounds_down_when_one_fits(self) -> None:
        self.assertEqual(
            core._select_builtin_bulk_padding_variant("NanumGothic", 9),
            15,
        )
        self.assertEqual(
            core._select_builtin_bulk_padding_variant("Mulmaru", 6),
            7,
        )
        self.assertEqual(
            core._select_builtin_bulk_padding_variant("NanumGothic", 20),
            None,
        )
        self.assertEqual(
            core.select_replacement_asset_padding("NanumGothic", 20, None),
            20,
        )
        self.assertEqual(
            core.select_replacement_asset_padding(
                "NanumGothic",
                20,
                None,
                prefer_raster=True,
            ),
            5,
        )

    def test_missing_padding_variant_regenerates_instead_of_using_root_sdf(
        self,
    ) -> None:
        core._load_font_assets_cached.cache_clear()
        cached = core._load_font_assets_cached(
            str(ROOT),
            "NanumGothic",
            False,
            20,
        )
        self.assertIsNotNone(cached["ttf_data"])
        self.assertIsNone(cached["sdf_data"])
        self.assertIsNone(cached["sdf_atlas_path"])

        with tempfile.TemporaryDirectory() as temp_dir:
            atlas_path = Path(temp_dir) / "atlas.png"
            Image.new("L", (2, 2), 255).save(atlas_path)
            generated = {
                "ttf_data": cached["ttf_data"],
                "sdf_data": {"m_AtlasPadding": 20},
                "sdf_data_normalized": {"m_AtlasPadding": 20},
                "sdf_atlas_path": str(atlas_path),
                "sdf_materials": None,
                "sdf_swizzle": False,
                "sdf_process_swizzle": False,
                "padding_variant": 20,
            }
            with patch.object(
                core,
                "_load_generated_font_assets_cached",
                return_value=generated,
            ) as generate:
                loaded = core.load_font_assets(
                    "NanumGothic",
                    padding_variant=20,
                )

            self.assertEqual(generate.call_args.args[3], 20)
            self.assertEqual(loaded["sdf_data"]["m_AtlasPadding"], 20)
            self.assertEqual(loaded["padding_variant"], 20)
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
            streamed_resource = data_path / "sharedassets0.assets.resS"
            managed_resource = data_path / "resources.assets.resource"
            backup = data_path / "old.bundle.bak"
            for path in (
                ignored_temp,
                kept_nested,
                ignored_rollback,
                regular,
                streamed_resource,
                managed_resource,
                backup,
            ):
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
