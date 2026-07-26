from __future__ import annotations

import unittest
from unittest.mock import patch

from PIL import Image

import unity_font_replacer_core as core


class Ps5SwizzleRegressionTests(unittest.TestCase):
    def test_process_swizzle_state_reaches_alpha8_encoder_when_detection_is_inconclusive(
        self,
    ) -> None:
        source = Image.new("L", (16, 16), color=31)
        transformed = Image.new("L", (16, 16), color=127)
        texture_plan = {
            "source_atlas": source,
            "source_swizzled": False,
            "replacement_process_swizzle": True,
            "replacement_swizzle_hint": False,
            "asset_process_swizzle": False,
            "metadata_width": 16,
            "metadata_height": 16,
        }

        with (
            patch.object(
                core,
                "_detect_target_texture_swizzle",
                return_value=("inconclusive", "test"),
            ),
            patch.object(
                core,
                "apply_ps5_swizzle_to_image",
                return_value=transformed,
            ) as swizzle,
        ):
            prepared = core._prepare_texture_replacement_for_target(
                texture_plan,
                assets_file_name="sharedassets0.assets",
                target_assets_name="CAB-test",
                target_path_id=101,
                texture_object_lookup={},
                texture_swizzle_state_cache={},
                ps5_swizzle=True,
                preview_export=False,
                preview_root=None,
                lang="en",
            )

        self.assertIsNotNone(prepared)
        assert prepared is not None
        self.assertIs(prepared["replacement_image"], transformed)
        self.assertIs(prepared["target_swizzled_state"], True)
        swizzle.assert_called_once_with(source)

        raw, width, height, mode = core._encode_alpha8_replacement_bytes(
            source,
            ps5_swizzle=True,
            target_swizzled_state=prepared["target_swizzled_state"],
        )
        self.assertEqual((width, height, mode), (16, 16, "swizzled"))
        self.assertEqual(len(raw), 16 * 16)


if __name__ == "__main__":
    unittest.main()
