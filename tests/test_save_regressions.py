from __future__ import annotations

import errno
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import unity_font_replacer_core as core


class SaveRegressionTests(unittest.TestCase):
    def _run_mock_split_failure(
        self,
        root: Path,
        target: Path,
        *,
        output_only: Path | None = None,
    ) -> list[list[str]]:
        data_path = target.parent
        replacements = {
            "a": {
                "File": target.name,
                "assets_name": "CAB",
                "Path_ID": 1,
                "Type": "SDF",
                "Replace_to": "NanumGothic",
                "Name": "A",
            },
            "b": {
                "File": target.name,
                "assets_name": "CAB",
                "Path_ID": 2,
                "Type": "SDF",
                "Replace_to": "NanumGothic",
                "Name": "B",
            },
        }
        calls: list[list[str]] = []

        def fake_replace(*args, **kwargs):
            calls.append(list(args[3]))
            outcome = kwargs["operation_outcome"]
            transaction = kwargs["deferred_transaction"]
            path = Path(args[2])
            if len(calls) == 1:
                transaction.backup(str(path))
                path.write_bytes(b"BATCH1")
                outcome.update(
                    requested_targets=1,
                    satisfied_targets=1,
                    modified=True,
                    save_success=True,
                    already_satisfied=False,
                )
                return True
            outcome.update(
                requested_targets=1,
                satisfied_targets=0,
                modified=False,
                save_success=False,
                already_satisfied=False,
            )
            return False

        argv = [
            "prog",
            "--gamepath",
            str(root),
            "--nanumgothic",
            "--split-save-force",
        ]
        if output_only is not None:
            argv.extend(["--output-only", str(output_only)])
        with (
            patch.object(sys, "argv", argv),
            patch.object(
                core,
                "resolve_game_path",
                return_value=(str(root), str(data_path)),
            ),
            patch.object(core, "get_compile_method", return_value="Mono"),
            patch.object(core, "get_unity_version", return_value="2021.3.0f1"),
            patch.object(
                core,
                "create_batch_replacements",
                return_value=replacements,
            ),
            patch.object(core, "_ensure_custom_unitypy_streaming_save"),
            patch.object(core, "_create_generator", return_value=object()),
            patch.object(core, "find_assets_files", return_value=[str(target)]),
            patch.object(core, "replace_fonts_in_file", side_effect=fake_replace),
            patch.object(core, "_pause_before_exit"),
        ):
            with self.assertRaises(core.DeferredPatchAtomicityError):
                core.main_cli(lang="en")
        return calls

    def test_main_split_terminal_failure_rolls_back_first_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Game"
            data_path = root / "Game_Data"
            data_path.mkdir(parents=True)
            target = data_path / "sharedassets0.assets"
            target.write_bytes(b"ORIGINAL")

            calls = self._run_mock_split_failure(root, target)

            self.assertEqual(calls, [["a"], ["b"]])
            self.assertEqual(target.read_bytes(), b"ORIGINAL")

    def test_main_output_only_split_failure_restores_new_and_existing_outputs(self) -> None:
        for preexisting in (None, b"PREEXIST"):
            with self.subTest(preexisting=preexisting):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir) / "Game"
                    data_path = root / "Game_Data"
                    data_path.mkdir(parents=True)
                    target = data_path / "sharedassets0.assets"
                    target.write_bytes(b"ORIGINAL")
                    output = Path(temp_dir) / "output"
                    output_target = output / target.name
                    if preexisting is not None:
                        output.mkdir()
                        output_target.write_bytes(preexisting)

                    calls = self._run_mock_split_failure(
                        root,
                        target,
                        output_only=output,
                    )

                    self.assertEqual(calls, [["a"], ["b"]])
                    self.assertEqual(target.read_bytes(), b"ORIGINAL")
                    if preexisting is None:
                        self.assertFalse(output_target.exists())
                    else:
                        self.assertEqual(output_target.read_bytes(), preexisting)

    def test_preview_success_is_not_a_replacement_failure_but_exception_is_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Game"
            data_path = root / "Game_Data"
            data_path.mkdir(parents=True)
            target = data_path / "sharedassets0.assets"
            target.write_bytes(b"ORIGINAL")
            replacements = {
                "preview": {
                    "File": target.name,
                    "assets_name": "CAB",
                    "Path_ID": 1,
                    "Type": "SDF",
                    "Replace_to": "",
                    "Name": "Preview",
                }
            }

            for should_raise in (False, True):
                with self.subTest(should_raise=should_raise):
                    calls = 0

                    def fake_preview(*args, **kwargs):
                        nonlocal calls
                        calls += 1
                        if should_raise:
                            raise RuntimeError("preview failed")
                        kwargs["operation_outcome"].update(
                            requested_targets=0,
                            satisfied_targets=0,
                            modified=False,
                            save_success=False,
                            already_satisfied=False,
                        )
                        return False

                    argv = ["prog", "--gamepath", str(root), "--preview-export"]
                    with (
                        patch.object(sys, "argv", argv),
                        patch.object(
                            core,
                            "resolve_game_path",
                            return_value=(str(root), str(data_path)),
                        ),
                        patch.object(core, "get_compile_method", return_value="Mono"),
                        patch.object(
                            core, "get_unity_version", return_value="2021.3.0f1"
                        ),
                        patch.object(
                            core,
                            "create_preview_export_targets",
                            return_value=replacements,
                        ),
                        patch.object(core, "_create_generator", return_value=object()),
                        patch.object(
                            core, "find_assets_files", return_value=[str(target)]
                        ),
                        patch.object(
                            core, "replace_fonts_in_file", side_effect=fake_preview
                        ),
                        patch.object(core, "_pause_before_exit"),
                    ):
                        if should_raise:
                            with self.assertRaisesRegex(RuntimeError, "preview"):
                                core.main_cli(lang="en")
                        else:
                            core.main_cli(lang="en")
                    self.assertEqual(calls, 1)

    def test_replace_exception_removes_only_its_spill_directory(self) -> None:
        captured: list[Path] = []

        @core._cleanup_replace_call_resources
        def fail_with_spill(
            game_path: str,
            temp_root_dir: str | None = None,
            _deferred_payload_dir: str | None = None,
        ) -> bool:
            spill_dir = Path(str(_deferred_payload_dir))
            captured.append(spill_dir)
            (spill_dir / "atlas.png").write_bytes(b"large-spill")
            raise RuntimeError("expected")

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(RuntimeError, "expected"):
                fail_with_spill("unused", temp_root_dir=temp_dir)

        self.assertEqual(len(captured), 1)
        self.assertFalse(captured[0].exists())

    def test_consuming_one_payload_preserves_unmatched_payload_and_spill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "asset"
            consumed_spill = root / "consumed.png"
            remaining_spill = root / "remaining.png"
            consumed_spill.write_bytes(b"consumed")
            remaining_spill.write_bytes(b"remaining")
            consumed = {"source_atlas_path": str(consumed_spill)}
            remaining = {"source_atlas_path": str(remaining_spill)}
            bucket: dict[str, object] = {}
            core._store_patch_value(bucket, "CAB|1", consumed)
            core._store_patch_value(bucket, "CAB|2", remaining)
            file_key = core._normalize_asset_file_key(str(target))
            patch_map = {file_key: bucket}

            removed = core._consume_deferred_patch_payloads(
                patch_map,
                file_key,
                {id(consumed)},
            )

            self.assertEqual(removed, 1)
            self.assertIsNone(core._lookup_patch_value(patch_map[file_key], "CAB|1"))
            self.assertIs(
                core._lookup_patch_value(patch_map[file_key], "CAB|2"), remaining
            )
            self.assertFalse(consumed_spill.exists())
            self.assertTrue(remaining_spill.exists())

    def test_case_alias_and_same_target_duplicates_reuse_one_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_spill = root / "first.png"
            duplicate_spill = root / "duplicate.png"
            first_spill.write_bytes(b"same-atlas")
            duplicate_spill.write_bytes(b"same-atlas")
            first = {"source_atlas_path": str(first_spill), "metadata_width": 64}
            duplicate = {
                "source_atlas_path": str(duplicate_spill),
                "metadata_width": 64,
            }
            transaction = core._DeferredPatchTransaction()
            patch_map: dict[str, dict[str, object]] = {}
            pending: set[str] = set()
            target_key = str(root / "target")

            self.assertTrue(
                core._register_deferred_patch(
                    patch_map,
                    target_key,
                    "CAB-X|1",
                    first,
                    pending_files=pending,
                    patch_kind="texture",
                    transaction=transaction,
                )
            )
            self.assertTrue(
                core._register_deferred_patch(
                    patch_map,
                    target_key,
                    "cab-x|1",
                    duplicate,
                    pending_files=pending,
                    patch_kind="texture",
                    transaction=transaction,
                )
            )

            file_key = core._normalize_asset_file_key(target_key)
            bucket = patch_map[file_key]
            self.assertEqual(core._patch_payload_ids(bucket), {id(first)})
            self.assertIs(core._lookup_patch_value(bucket, "CAB-X|1"), first)
            self.assertIs(core._lookup_patch_value(bucket, "cab-x|1"), first)
            self.assertTrue(first_spill.exists())
            self.assertFalse(duplicate_spill.exists())

            second_duplicate = root / "second-duplicate.png"
            second_duplicate.write_bytes(b"same-atlas")
            stored, inserted = core._store_consistent_patch_value(
                bucket,
                "Cab-X|1",
                {
                    "source_atlas_path": str(second_duplicate),
                    "metadata_width": 64,
                },
                patch_kind="texture",
                target_file_key=file_key,
                transaction=transaction,
            )
            self.assertIs(stored, first)
            self.assertFalse(inserted)
            self.assertEqual(core._patch_payload_ids(bucket), {id(first)})
            self.assertFalse(second_duplicate.exists())

            conflicting_spill = root / "conflicting.png"
            conflicting_spill.write_bytes(b"different-atlas")
            self.assertFalse(
                core._register_deferred_patch(
                    patch_map,
                    target_key,
                    "CAB-X|1",
                    {
                        "source_atlas_path": str(conflicting_spill),
                        "metadata_width": 64,
                    },
                    pending_files=pending,
                    patch_kind="texture",
                    transaction=transaction,
                )
            )
            self.assertTrue(transaction.has_failures)
            self.assertIs(core._lookup_patch_value(bucket, "CAB-X|1"), first)
            core._cleanup_deferred_patch_bucket(
                {"conflict": {"source_atlas_path": str(conflicting_spill)}}
            )
            self.assertTrue(transaction.rollback())

    def test_transaction_restores_existing_and_removes_new_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            existing = root / "existing"
            created = root / "created"
            existing.write_bytes(b"before")
            transaction = core._DeferredPatchTransaction()
            transaction.backup(str(existing))
            transaction.backup(str(created), allow_missing=True)
            existing.write_bytes(b"after-first-batch")
            transaction.backup(str(existing))
            existing.write_bytes(b"after-second-batch")
            created.write_bytes(b"new")

            self.assertTrue(transaction.rollback())
            self.assertEqual(existing.read_bytes(), b"before")
            self.assertFalse(created.exists())

    def test_failed_rollback_keeps_backup_for_a_later_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target"
            target.write_bytes(b"before")
            transaction = core._DeferredPatchTransaction()
            transaction.backup(str(target))
            backup_directory = Path(transaction.backup_directory)
            target.write_bytes(b"after")

            with patch.object(
                core,
                "_atomic_replace_validated_file",
                side_effect=OSError("restore blocked"),
            ):
                self.assertFalse(transaction.rollback())

            self.assertTrue(transaction.is_active)
            self.assertTrue(backup_directory.is_dir())
            self.assertTrue(any(backup_directory.iterdir()))
            self.assertEqual(target.read_bytes(), b"after")

            self.assertTrue(transaction.rollback())
            self.assertEqual(target.read_bytes(), b"before")
            self.assertFalse(backup_directory.exists())

    def test_output_only_dependency_copy_is_removed_on_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_path = root / "Game_Data"
            output_path = root / "output"
            data_path.mkdir()
            (data_path / "globalgamemanagers").write_bytes(b"dependency")
            transaction = core._DeferredPatchTransaction()

            core.prepare_output_only_dependencies(
                str(data_path),
                str(output_path),
                lang="en",
                transaction=transaction,
            )

            copied = output_path / "globalgamemanagers"
            self.assertEqual(copied.read_bytes(), b"dependency")
            self.assertTrue(transaction.rollback())
            self.assertFalse(copied.exists())

    def test_cli_guard_rolls_back_immediately_when_caller_catches_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "asset"
            target.write_bytes(b"before")

            @core._rollback_deferred_transaction_on_exit
            def fail_after_change() -> None:
                transaction = core._DeferredPatchTransaction()
                core._ACTIVE_DEFERRED_TRANSACTION.set(transaction)
                transaction.backup(str(target))
                target.write_bytes(b"after")
                raise RuntimeError("expected")

            with self.assertRaisesRegex(RuntimeError, "expected"):
                fail_after_change()
            self.assertEqual(target.read_bytes(), b"before")

    def test_transaction_rejects_conflicting_consumed_target_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_atlas = root / "first.png"
            same_atlas = root / "same.png"
            different_atlas = root / "different.png"
            first_atlas.write_bytes(b"atlas-a")
            same_atlas.write_bytes(b"atlas-a")
            different_atlas.write_bytes(b"atlas-b")
            transaction = core._DeferredPatchTransaction()
            first = {
                "source_atlas_path": str(first_atlas),
                "metadata_width": 64,
                "font_name": "First Name",
                "replacement_font": "First Font",
            }
            same = {
                "source_atlas_path": str(same_atlas),
                "metadata_width": 64,
                "font_name": "Second Name",
                "replacement_font": "Second Font",
            }
            different = {
                "source_atlas_path": str(different_atlas),
                "metadata_width": 64,
            }

            self.assertTrue(
                transaction.register_plan("texture", str(root / "target"), "CAB|1", first)
            )
            self.assertTrue(
                transaction.register_plan("texture", str(root / "target"), "cab|1", same)
            )
            self.assertFalse(
                transaction.register_plan(
                    "texture", str(root / "target"), "CAB|1", different
                )
            )
            self.assertTrue(transaction.has_conflicts)
            self.assertTrue(transaction.rollback())

    def test_cross_volume_install_stages_next_to_destination_then_replaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source" / "validated"
            destination = root / "destination" / "asset"
            source.parent.mkdir()
            destination.parent.mkdir()
            source.write_bytes(b"validated-new")
            destination.write_bytes(b"original")
            real_replace = core.os.replace
            calls = 0

            def replace_with_first_exdev(src, dst):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError(errno.EXDEV, "simulated cross-volume move")
                return real_replace(src, dst)

            with patch.object(core.os, "replace", side_effect=replace_with_first_exdev):
                core._atomic_replace_validated_file(str(source), str(destination))

            self.assertEqual(destination.read_bytes(), b"validated-new")
            self.assertFalse(source.exists())
            self.assertEqual(calls, 2)
            self.assertEqual(
                list(destination.parent.glob("*.validated.tmp")),
                [],
            )

    def test_cross_volume_copy_failure_preserves_original(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "validated"
            destination = root / "asset"
            source.write_bytes(b"new")
            destination.write_bytes(b"original")
            with (
                patch.object(
                    core.os,
                    "replace",
                    side_effect=OSError(errno.EXDEV, "simulated cross-volume move"),
                ),
                patch.object(
                    core.shutil,
                    "copyfileobj",
                    side_effect=OSError("simulated copy failure"),
                ),
            ):
                with self.assertRaisesRegex(OSError, "copy failure"):
                    core._atomic_replace_validated_file(
                        str(source),
                        str(destination),
                    )
            self.assertEqual(destination.read_bytes(), b"original")
            self.assertTrue(source.exists())
            self.assertFalse(
                any(destination.parent.glob("*.validated.tmp"))
            )

    def test_ttf_only_replace_does_not_build_typetree_generator(self) -> None:
        class FakeFile:
            pass

        class FakeEnv:
            file = FakeFile()
            files = {"asset": file}
            objects: list[object] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_path = root / "Game"
            data_path = game_path / "Game_Data"
            data_path.mkdir(parents=True)
            target = data_path / "asset"
            target.write_bytes(b"asset")
            with (
                patch.object(core, "load_unitypy", return_value=FakeEnv()),
                patch.object(core, "_ensure_custom_unitypy_streaming_save"),
                patch.object(
                    core,
                    "_create_generator",
                    side_effect=AssertionError("TTF-only replacement needs no TypeTree"),
                ),
            ):
                result = core.replace_fonts_in_file(
                    "2021.3.0f1",
                    str(game_path),
                    str(target),
                    {},
                    replace_ttf=True,
                    replace_sdf=False,
                    generator=None,
                    replacement_lookup={},
                    lang="en",
                )
            self.assertFalse(result)

    def test_deferred_material_only_uses_save_to_and_closes_environment(self) -> None:
        class FakeType:
            name = "Material"

        class FakeAssetsFile:
            name = "CAB-test"
            is_changed = False

            def mark_changed(self) -> None:
                self.is_changed = True

        class FakeObject:
            type = FakeType()
            assets_file = FakeAssetsFile()
            path_id = 7

            def peek_name(self) -> str:
                return "mat"

        class FakeFile:
            dataflags = None

            def save_to(self, path: str, packer=None) -> int:
                Path(path).write_bytes(b"SAVED")
                return 5

            def save(self, packer=None):
                raise AssertionError("legacy save() must not be called")

        class FakeEnv:
            file = FakeFile()
            objects = [FakeObject()]
            files = {"bundle": file}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_path = root / "Game"
            data_path = game_path / "Game_Data"
            data_path.mkdir(parents=True)
            target = data_path / "bundle"
            target.write_bytes(b"notbundle")
            file_key = core._normalize_asset_file_key(str(target))
            object_key = core._make_assets_object_key("CAB-test", 7)
            deferred_material_plans = {
                file_key: {object_key: {"replacement_font": "TestFont"}}
            }
            environment = FakeEnv()
            close_calls: list[object] = []

            with (
                patch.object(core, "load_unitypy", return_value=environment),
                patch.object(core, "_safe_parse_as_object", return_value=object()),
                patch.object(
                    core,
                    "_apply_material_replacement_to_object",
                    return_value=True,
                ),
                patch.object(
                    core,
                    "_safe_save",
                    side_effect=lambda obj, parsed: obj.assets_file.mark_changed(),
                ),
                patch.object(core, "close_unitypy_env", side_effect=close_calls.append),
                patch.object(core, "_ensure_custom_unitypy_streaming_save"),
                patch.object(
                    core.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
                ),
            ):
                result = core.replace_fonts_in_file(
                    "2021.3.0f1",
                    str(game_path),
                    str(target),
                    {},
                    replace_ttf=False,
                    replace_sdf=False,
                    temp_root_dir=str(root / "scratch"),
                    generator=object(),
                    replacement_lookup={},
                    deferred_material_plans=deferred_material_plans,
                    lang="en",
                )

            self.assertTrue(result)
            self.assertTrue(FakeObject.assets_file.is_changed)
            self.assertEqual(target.read_bytes(), b"SAVED")
            self.assertEqual(close_calls, [environment])

    def test_partial_required_material_bucket_refuses_save_and_preserves_plans(self) -> None:
        class FakeType:
            name = "Material"

        class FakeAssetsFile:
            name = "CAB-test"

        class FakeObject:
            type = FakeType()
            assets_file = FakeAssetsFile()
            path_id = 7

        class FakeFile:
            dataflags = None

            def save_to(self, path: str, packer=None) -> int:
                raise AssertionError("partial deferred target must not be saved")

        class FakeEnv:
            file = FakeFile()
            objects = [FakeObject()]
            files = {"bundle": file}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_path = root / "Game"
            data_path = game_path / "Game_Data"
            data_path.mkdir(parents=True)
            target = data_path / "bundle"
            target.write_bytes(b"original")
            file_key = core._normalize_asset_file_key(str(target))
            first_key = core._make_assets_object_key("CAB-test", 7)
            missing_key = core._make_assets_object_key("CAB-test", 8)
            first_payload = {"replacement_font": "First"}
            missing_payload = {"replacement_font": "Missing"}
            deferred_material_plans = {
                file_key: {
                    first_key: first_payload,
                    missing_key: missing_payload,
                }
            }
            transaction = core._DeferredPatchTransaction()

            with (
                patch.object(core, "load_unitypy", return_value=FakeEnv()),
                patch.object(core, "_safe_parse_as_object", return_value=object()),
                patch.object(
                    core,
                    "_apply_material_replacement_to_object",
                    return_value=True,
                ),
                patch.object(core, "_safe_save"),
                patch.object(core, "_ensure_custom_unitypy_streaming_save"),
            ):
                result = core.replace_fonts_in_file(
                    "2021.3.0f1",
                    str(game_path),
                    str(target),
                    {},
                    replace_ttf=False,
                    replace_sdf=False,
                    temp_root_dir=str(root / "scratch"),
                    generator=object(),
                    replacement_lookup={},
                    deferred_material_plans=deferred_material_plans,
                    deferred_transaction=transaction,
                    lang="en",
                )

            self.assertFalse(result)
            self.assertEqual(target.read_bytes(), b"original")
            self.assertIs(
                deferred_material_plans[file_key][first_key], first_payload
            )
            self.assertIs(
                deferred_material_plans[file_key][missing_key], missing_payload
            )
            self.assertTrue(transaction.has_failures)
            self.assertTrue(transaction.rollback())

    def test_strict_validation_failure_never_replaces_original(self) -> None:
        class FakeType:
            name = "Material"

        class FakeAssetsFile:
            name = "CAB-test"

        class FakeObject:
            type = FakeType()
            assets_file = FakeAssetsFile()
            path_id = 7

        class FakeFile:
            dataflags = None

            def save_to(self, path: str, packer=None) -> int:
                Path(path).write_bytes(b"invalid-saved-output")
                return 20

        class FakeEnv:
            file = FakeFile()
            objects = [FakeObject()]
            files = {"bundle": file}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_path = root / "Game"
            data_path = game_path / "Game_Data"
            data_path.mkdir(parents=True)
            target = data_path / "bundle"
            target.write_bytes(b"original")
            file_key = core._normalize_asset_file_key(str(target))
            object_key = core._make_assets_object_key("CAB-test", 7)
            payload = {"replacement_font": "TestFont"}
            deferred_material_plans = {file_key: {object_key: payload}}

            with (
                patch.object(core, "load_unitypy", return_value=FakeEnv()),
                patch.object(core, "_safe_parse_as_object", return_value=object()),
                patch.object(
                    core,
                    "_apply_material_replacement_to_object",
                    return_value=True,
                ),
                patch.object(core, "_safe_save"),
                patch.object(core, "_ensure_custom_unitypy_streaming_save"),
                patch.object(
                    core.subprocess,
                    "run",
                    return_value=SimpleNamespace(
                        returncode=9,
                        stdout="invalid bundle",
                        stderr="",
                    ),
                ),
            ):
                result = core.replace_fonts_in_file(
                    "2021.3.0f1",
                    str(game_path),
                    str(target),
                    {},
                    replace_ttf=False,
                    replace_sdf=False,
                    temp_root_dir=str(root / "scratch"),
                    generator=object(),
                    replacement_lookup={},
                    deferred_material_plans=deferred_material_plans,
                    lang="en",
                )

            self.assertFalse(result)
            self.assertEqual(target.read_bytes(), b"original")
            self.assertIs(deferred_material_plans[file_key][object_key], payload)

    def test_requested_ttf_save_failure_is_not_reported_as_already_satisfied(self) -> None:
        class FakeType:
            name = "Font"

        class FakeAssetsFile:
            name = "CAB-test"

        class FakeObject:
            type = FakeType()
            assets_file = FakeAssetsFile()
            path_id = 7

        class FakeFont:
            m_FontData = b"old-font"
            m_FontNames = ["Old"]
            m_Ascent = 1.0
            m_Descent = -1.0
            m_LineSpacing = 2.0
            m_Name = "Old"

        class FakeFile:
            dataflags = None

            def save_to(self, path: str, packer=None) -> int:
                Path(path).write_bytes(b"invalid")
                return 7

        class FakeEnv:
            file = FakeFile()
            objects = [FakeObject()]
            files = {"bundle": file}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_path = root / "Game"
            data_path = game_path / "Game_Data"
            data_path.mkdir(parents=True)
            target = data_path / "bundle"
            target.write_bytes(b"original")
            outcome: dict[str, object] = {}
            lookup = {("TTF", "bundle", "CAB-test", 7): "NewFont"}

            with (
                patch.object(core, "load_unitypy", return_value=FakeEnv()),
                patch.object(core, "_safe_parse_as_object", return_value=FakeFont()),
                patch.object(
                    core,
                    "load_font_assets",
                    return_value={"ttf_data": b"new-font"},
                ),
                patch.object(
                    core,
                    "apply_ttf_metadata_to_font",
                    return_value={
                        "font_names": ["New"],
                        "ascent": 1.0,
                        "descent": -1.0,
                        "line_spacing": 2.0,
                    },
                ),
                patch.object(core, "_safe_save"),
                patch.object(core, "_ensure_custom_unitypy_streaming_save"),
                patch.object(
                    core.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=9, stdout="bad", stderr=""),
                ),
            ):
                result = core.replace_fonts_in_file(
                    "2021.3.0f1",
                    str(game_path),
                    str(target),
                    {},
                    replace_ttf=True,
                    replace_sdf=False,
                    temp_root_dir=str(root / "scratch"),
                    generator=None,
                    replacement_lookup=lookup,
                    operation_outcome=outcome,
                    lang="en",
                )

            self.assertFalse(result)
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual(outcome["requested_targets"], 1)
            self.assertEqual(outcome["satisfied_targets"], 1)
            self.assertTrue(outcome["modified"])
            self.assertFalse(outcome["save_success"])
            self.assertFalse(outcome["already_satisfied"])


if __name__ == "__main__":
    unittest.main()
