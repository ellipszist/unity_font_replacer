from __future__ import annotations

import json
import re
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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
    @staticmethod
    def _pe_header(machine: int, magic: int) -> bytes:
        data = bytearray(90)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 64)
        data[64:68] = b"PE\0\0"
        struct.pack_into("<H", data, 68, machine)
        struct.pack_into("<H", data, 84, 2)
        struct.pack_into("<H", data, 88, magic)
        return bytes(data)

    def test_dumper_selection_matches_game_pe_in_source_and_frozen_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "GameAssembly.dll"
            for frozen in (False, True):
                for architecture, machine, magic in (("x86", 0x14C, 0x10B), ("x64", 0x8664, 0x20B)):
                    with self.subTest(frozen=frozen, architecture=architecture):
                        binary.write_bytes(self._pe_header(machine, magic))
                        base = Path(directory) if frozen else ROOT
                        expected = base / "Il2CppDumper"
                        if architecture == "x86":
                            expected /= "x86"
                        with (
                            patch.dict(runtime.os.environ, {"UFR_IL2CPP_DUMPER": ""}),
                            patch.object(runtime.sys, "frozen", frozen, create=True),
                            patch.object(runtime.sys, "executable", str(Path(directory) / "ufr.exe")),
                            patch.object(runtime.os.path, "isfile", return_value=True),
                        ):
                            self.assertEqual(
                                Path(runtime._il2cpp_dumper_path(binary_path=str(binary))),
                                expected / "Il2CppDumper.exe",
                            )

    def test_dumper_overrides_bypass_automatic_pe_detection(self) -> None:
        with (
            patch.dict(runtime.os.environ, {"UFR_IL2CPP_DUMPER": "environment.exe"}),
            patch.object(runtime.os.path, "isfile", return_value=True),
            patch.object(runtime, "_pe_architecture") as detect,
        ):
            self.assertEqual(Path(runtime._il2cpp_dumper_path(binary_path="missing.dll")).name, "environment.exe")
            self.assertEqual(Path(runtime._il2cpp_dumper_path("explicit.exe", binary_path="missing.dll")).name, "explicit.exe")
            detect.assert_not_called()

    def test_missing_x86_dumper_does_not_fall_back_to_x64(self) -> None:
        with (
            patch.dict(runtime.os.environ, {"UFR_IL2CPP_DUMPER": ""}),
            patch.object(runtime, "_pe_architecture", return_value="x86"),
            patch.object(runtime.os.path, "isfile", side_effect=lambda path: Path(path).parent.name != "x86"),
        ):
            with self.assertRaisesRegex(FileNotFoundError, "x86"):
                runtime._il2cpp_dumper_path(binary_path="GameAssembly.dll")

    def test_pe_detection_rejects_invalid_or_unsupported_headers(self) -> None:
        valid = self._pe_header(0x14C, 0x10B)
        cases = (
            b"", b"not a PE", valid[:63], valid[:89],
            valid[:60] + struct.pack("<I", 0xFFFFFFFF) + valid[64:],
            valid[:60] + bytes(4) + valid[64:],
            valid[:64] + b"NOPE" + valid[68:],
            valid[:84] + bytes(2) + valid[86:],
            self._pe_header(0xAA64, 0x20B),
            self._pe_header(0x14C, 0x20B), self._pe_header(0x8664, 0x10B),
        )
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "GameAssembly.dll"
            for index, data in enumerate(cases):
                with self.subTest(case=index):
                    binary.write_bytes(data)
                    with self.assertRaises(ValueError):
                        runtime._pe_architecture(str(binary))

    def test_dummy_dll_restore_uses_selected_architecture_and_its_companions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "GameAssembly.dll"
            data = root / "Game_Data"
            metadata = data / "il2cpp_data" / "Metadata" / "global-metadata.dat"
            metadata.parent.mkdir(parents=True)
            metadata.write_bytes(b"metadata")
            commands = []

            def fake_run(command, **kwargs):
                commands.append(command)
                dummy = Path(command[3]) / "DummyDll"
                dummy.mkdir()
                (dummy / "Assembly-CSharp.dll").write_bytes(b"dummy")
                return SimpleNamespace(returncode=0, stdout="Done!", stderr="")

            for architecture, machine, magic in (("x86", 0x14C, 0x10B), ("x64", 0x8664, 0x20B)):
                with self.subTest(architecture=architecture):
                    binary.write_bytes(self._pe_header(machine, magic))
                    folder = root / "Il2CppDumper"
                    if architecture == "x86":
                        folder /= "x86"
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / "Il2CppDumper.exe").write_bytes(architecture.encode("ascii"))
                    (folder / "Il2CppDumper.dll").write_bytes(architecture.encode("ascii"))
                    with (
                        patch.dict(runtime.os.environ, {"UFR_IL2CPP_DUMPER": ""}),
                        patch.object(runtime.sys, "frozen", True, create=True),
                        patch.object(runtime.sys, "executable", str(root / "ufr.exe")),
                        patch.object(runtime.subprocess, "run", side_effect=fake_run),
                    ):
                        result = runtime._ensure_il2cpp_dummy_dlls(
                            "2022.3.35f1", str(root), str(data), cache_root=str(root / "cache"),
                        )
                        self.assertEqual(result, runtime._ensure_il2cpp_dummy_dlls(
                            "2022.3.35f1", str(root), str(data), cache_root=str(root / "cache"),
                        ))
                    self.assertEqual(Path(commands[-1][0]), folder / "Il2CppDumper.exe")
                    manifest = json.loads((Path(result).parent / "manifest.json").read_text(encoding="utf-8"))
                    self.assertEqual(manifest["dumper_companions_sha256"], {
                        "Il2CppDumper.dll": runtime._sha256_file(str(folder / "Il2CppDumper.dll")),
                    })
            self.assertEqual(len(commands), 2)
            self.assertNotEqual(commands[0][3], commands[1][3])

    def test_custom_unitypy_install_revisions_match(self) -> None:
        revisions = set()
        for name in ("build.bat", ".github/workflows/release.yml", "README.md", "README_EN.md"):
            with self.subTest(file=name):
                content = (ROOT / name).read_text(encoding="utf-8-sig")
                matches = re.findall(
                    r"git\+https://github\.com/snowyegret23/UnityPy\.git@([0-9a-f]{40})\b",
                    content,
                )
                self.assertEqual(len(matches), 1, name)
                revisions.update(matches)
        self.assertEqual(len(revisions), 1, "Custom UnityPy installation revisions differ")

    def test_bundled_il2cpp_dumper_has_local_runtime(self) -> None:
        bundle = ROOT / "Il2CppDumper"
        provenance = json.loads((bundle / "BUNDLED_RELEASE.json").read_text(encoding="utf-8-sig"))
        self.assertRegex(provenance["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(set(provenance["packages"]), {"x64", "x86"})
        self.assertFalse((bundle / "Il2CppDumper-x86.exe").exists())
        for architecture, relative in (("x64", "."), ("x86", "x86")):
            folder = bundle / relative
            for name in (
                "Il2CppDumper.exe", "Il2CppDumper.dll", "Mono.Cecil.dll",
                "coreclr.dll", "hostfxr.dll", "hostpolicy.dll", "System.Private.CoreLib.dll",
                "Il2CppDumper.deps.json", "LICENSE", "LICENSE.TXT", "THIRD-PARTY-NOTICES.TXT",
                "Mono.Cecil.LICENSE.txt",
            ):
                with self.subTest(architecture=architecture, file=name):
                    self.assertTrue((folder / name).is_file(), name)
                    self.assertGreater((folder / name).stat().st_size, 0)
            with self.subTest(architecture=architecture):
                for name in ("Il2CppDumper.exe", "coreclr.dll", "hostfxr.dll", "hostpolicy.dll"):
                    self.assertEqual(runtime._pe_architecture(str(folder / name)), architecture)
                package = provenance["packages"][architecture]
                self.assertEqual((bundle / package["entry_point"]).resolve(), (folder / "Il2CppDumper.exe").resolve())
                for name, digest in package["files_sha256"].items():
                    self.assertEqual(runtime._sha256_file(str(folder / name)), digest, name)
                self.assertEqual(set(package["files_sha256"]), {"Il2CppDumper.exe", "Il2CppDumper.dll"})
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
