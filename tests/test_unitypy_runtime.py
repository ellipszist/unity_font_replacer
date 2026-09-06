from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import unitypy_runtime as runtime
import unity_font_replacer_core as core
from unitypy_runtime import (
    UnityPy,
    cleanup_unitypy_environments,
    close_unitypy_env,
    load_unitypy,
    missing_low_memory_features,
)


ROOT = Path(__file__).resolve().parents[1]
UNITYPY_ROOT = ROOT.parent / "UnityPy"
ACTIVE_UNITYPY_ROOT = Path(UnityPy.__file__).resolve().parents[1]
SAMPLE_BUNDLE = ACTIVE_UNITYPY_ROOT / "tests" / "samples" / "atlas_test"


class UnityPyRuntimeTests(unittest.TestCase):
    def test_bundled_il2cpp_dumper_has_local_runtime(self) -> None:
        folder = ROOT / "Il2CppDumper"
        for name in (
            "Il2CppDumper.exe", "Il2CppDumper.dll", "Mono.Cecil.dll",
            "coreclr.dll", "hostfxr.dll", "hostpolicy.dll", "System.Private.CoreLib.dll",
            "Il2CppDumper.deps.json", "LICENSE", "LICENSE.TXT", "THIRD-PARTY-NOTICES.TXT",
            "Mono.Cecil.LICENSE.txt",
        ):
            with self.subTest(file=name):
                self.assertTrue((folder / name).is_file(), name)
                self.assertGreater((folder / name).stat().st_size, 0)
        config = json.loads((folder / "config.json").read_text(encoding="utf-8-sig"))
        self.assertFalse(config["RequireAnyKey"])
        self.assertTrue(config["GenerateDummyDll"])
        self.assertFalse(config["StringsOnly"])
        self.assertFalse(config["RestoreExplicitInterfaces"])
        runtime_options = json.loads(
            (folder / "Il2CppDumper.runtimeconfig.json").read_text(encoding="utf-8-sig")
        )["runtimeOptions"]
        self.assertNotIn("framework", runtime_options)
        self.assertNotIn("frameworks", runtime_options)
        self.assertTrue(any(
            framework["name"] == "Microsoft.NETCore.App"
            for framework in runtime_options["includedFrameworks"]
        ))

    def test_explicit_close_removes_environment_from_scoped_tracking(self) -> None:
        class FakeEnvironment:
            file = None
            files: dict[str, object] = {}
            cabs: dict[str, object] = {}

        observed_lengths: list[int] = []

        @cleanup_unitypy_environments
        def load_then_close() -> None:
            environment = load_unitypy(object())
            active = runtime._ACTIVE_ENVIRONMENTS.get()
            observed_lengths.append(len(active or []))
            close_unitypy_env(environment)
            observed_lengths.append(len(active or []))

        with patch.object(runtime.UnityPy, "load", return_value=FakeEnvironment()):
            load_then_close()

        self.assertEqual(observed_lengths, [1, 0])

    def test_source_run_prefers_current_sibling_unitypy(self) -> None:
        version = tuple(int(part) for part in UnityPy.__version__.split(".")[:3])
        self.assertGreaterEqual(version, (1, 25, 2))
        if (UNITYPY_ROOT / "UnityPy" / "__init__.py").is_file():
            self.assertTrue(
                Path(UnityPy.__file__).resolve().is_relative_to(UNITYPY_ROOT.resolve())
            )
        self.assertEqual(missing_low_memory_features(), [])

    @unittest.skipUnless(SAMPLE_BUNDLE.is_file(), "UnityPy sample bundle unavailable")
    def test_close_releases_bundle_mmap_and_serialized_spill(self) -> None:
        environment = load_unitypy(str(SAMPLE_BUNDLE))
        bundle = environment.file
        bundle_temp = Path(bundle._blocks_tmp_path)
        serialized = next(
            child
            for child in bundle.files.values()
            if hasattr(child, "get_spill_store")
        )
        spill = serialized.get_spill_store()
        spill.append_bytes(b"test")
        spill_path = Path(spill.path)
        self.assertTrue(bundle_temp.exists())
        self.assertTrue(spill_path.exists())

        close_unitypy_env(environment)

        self.assertFalse(bundle_temp.exists())
        self.assertFalse(spill_path.exists())
        self.assertEqual(environment.files, {})
        self.assertIsNone(environment.file)

    @unittest.skipUnless(SAMPLE_BUNDLE.is_file(), "UnityPy sample bundle unavailable")
    def test_scoped_cleanup_runs_when_processing_raises(self) -> None:
        captured: dict[str, Path] = {}

        @cleanup_unitypy_environments
        def fail_after_load() -> None:
            environment = load_unitypy(str(SAMPLE_BUNDLE))
            captured["temp"] = Path(environment.file._blocks_tmp_path)
            raise RuntimeError("expected")

        with self.assertRaisesRegex(RuntimeError, "expected"):
            fail_after_load()
        self.assertFalse(captured["temp"].exists())

    @unittest.skipUnless(SAMPLE_BUNDLE.is_file(), "UnityPy sample bundle unavailable")
    def test_save_to_roundtrip_reopens_modified_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "atlas_test.saved"
            environment = load_unitypy(str(SAMPLE_BUNDLE))
            bundle = environment.file
            texture = next(obj for obj in environment.objects if obj.type.name == "Texture2D")
            path_id = texture.path_id
            parsed = texture.parse_as_object()
            new_name = f"{parsed.m_Name}_runtime_test"
            parsed.m_Name = new_name
            parsed.save()
            bundle.save_to(str(output), packer="lz4")
            close_unitypy_env(environment)

            reloaded = load_unitypy(str(output))
            try:
                saved = next(obj for obj in reloaded.objects if obj.path_id == path_id)
                self.assertEqual(saved.peek_name(), new_name)
            finally:
                close_unitypy_env(reloaded)

    @unittest.skipUnless(SAMPLE_BUNDLE.is_file(), "UnityPy sample bundle unavailable")
    def test_segmented_binary_texture_patch_streams_and_strictly_reopens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "segmented.saved"
            environment = load_unitypy(str(SAMPLE_BUNDLE))
            texture = next(
                obj for obj in environment.objects if obj.type.name == "Texture2D"
            )
            path_id = texture.path_id
            parsed = texture.parse_as_object()
            source_image_data = bytes(parsed.get_image_data())
            self.assertTrue(
                core._binary_patch_texture2d(
                    texture,
                    image_data=source_image_data,
                    width=int(parsed.m_Width),
                    height=int(parsed.m_Height),
                    lang="en",
                )
            )
            with patch.object(
                core._SegmentedBytesReplacer,
                "read_bytes",
                side_effect=AssertionError("save_to must stream replacer chunks"),
            ):
                environment.file.save_to(str(output), packer="lz4")
            close_unitypy_env(environment)

            reloaded = load_unitypy(str(output))
            try:
                saved = next(obj for obj in reloaded.objects if obj.path_id == path_id)
                strict = saved.parse_as_object()
                self.assertEqual(int(strict.m_Width), int(parsed.m_Width))
                self.assertEqual(int(strict.m_Height), int(parsed.m_Height))
                self.assertEqual(bytes(strict.get_image_data()), source_image_data)
            finally:
                close_unitypy_env(reloaded)

    @unittest.skipUnless(SAMPLE_BUNDLE.is_file(), "UnityPy sample bundle unavailable")
    def test_split_file_path_keeps_unitypy_split_merge_behavior(self) -> None:
        source = SAMPLE_BUNDLE.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "atlas.bundle"
            midpoint = len(source) // 2
            Path(f"{base}.split0").write_bytes(source[:midpoint])
            Path(f"{base}.split1").write_bytes(source[midpoint:])
            environment = load_unitypy(f"{base}.split0")
            try:
                self.assertTrue(environment.objects)
                self.assertIsNone(
                    getattr(environment, "_unity_font_replacer_source_streams", None)
                )
            finally:
                close_unitypy_env(environment)


if __name__ == "__main__":
    unittest.main()
