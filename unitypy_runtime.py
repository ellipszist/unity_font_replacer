"""UnityPy runtime selection and deterministic resource cleanup.

Source runs prefer the sibling custom UnityPy checkout. Frozen builds use the
UnityPy copy bundled by PyInstaller. Both paths are checked for the low-memory
load/save features required by this project.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any, Callable, ParamSpec, TypeVar


def _prefer_sibling_unitypy() -> None:
    if getattr(sys, "frozen", False):
        return
    sibling_root = Path(__file__).resolve().parent.parent / "UnityPy"
    if not (sibling_root / "UnityPy" / "__init__.py").is_file():
        return
    sibling_text = str(sibling_root)
    if sibling_text not in sys.path:
        sys.path.insert(0, sibling_text)


_prefer_sibling_unitypy()

import UnityPy as UnityPy  # noqa: E402
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator  # noqa: E402


_P = ParamSpec("_P")
_R = TypeVar("_R")
_ACTIVE_ENVIRONMENTS: ContextVar[list[Any] | None] = ContextVar(
    "unitypy_active_environments", default=None
)

_IL2CPP_CACHE_FORMAT = 1


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while True:
            chunk = source.read(4 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _il2cpp_cache_root(explicit_root: str | None = None) -> str:
    configured = explicit_root or os.environ.get("UFR_IL2CPP_CACHE_ROOT", "")
    base = (
        os.path.abspath(configured)
        if configured
        else os.path.join(tempfile.gettempdir(), "UnityFontReplacer")
    )
    root = os.path.abspath(os.path.join(base, "il2cpp_cache"))
    os.makedirs(root, exist_ok=True)
    return root


def _il2cpp_dumper_path(explicit_path: str | None = None) -> str:
    configured = explicit_path or os.environ.get("UFR_IL2CPP_DUMPER", "")
    if configured:
        candidate = os.path.abspath(configured)
    else:
        base = (
            os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__))
        )
        candidate = os.path.join(base, "Il2CppDumper", "Il2CppDumper.exe")
    if not os.path.isfile(candidate):
        raise FileNotFoundError(
            "Il2CppDumper.exe was not found. Expected it at " f"{candidate}"
        )
    return candidate


def _safe_remove_cache_tree(path: str, cache_root: str) -> None:
    resolved_path = os.path.abspath(path)
    resolved_root = os.path.abspath(cache_root)
    if resolved_path == resolved_root or os.path.commonpath(
        (resolved_path, resolved_root)
    ) != resolved_root:
        raise RuntimeError(f"Refusing to remove unsafe cache path: {resolved_path}")
    if os.path.isdir(resolved_path):
        shutil.rmtree(resolved_path)


def _dummy_cache_is_complete(cache_dir: str, expected_manifest: dict[str, Any]) -> bool:
    manifest_path = os.path.join(cache_dir, "manifest.json")
    dummy_dir = os.path.join(cache_dir, "DummyDll")
    if not os.path.isfile(manifest_path) or not os.path.isdir(dummy_dir):
        return False
    try:
        with open(manifest_path, "r", encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
    except Exception:
        return False
    if manifest != expected_manifest:
        return False
    return any(name.lower().endswith(".dll") for name in os.listdir(dummy_dir))


def _ensure_il2cpp_dummy_dlls(
    unity_version: str,
    game_path: str,
    data_path: str,
    *,
    cache_root: str | None = None,
    dumper_path: str | None = None,
    log: Callable[[str], None] | None = None,
) -> str:
    binary_path = os.path.join(game_path, "GameAssembly.dll")
    metadata_path = os.path.join(
        data_path, "il2cpp_data", "Metadata", "global-metadata.dat"
    )
    if not os.path.isfile(binary_path) or not os.path.isfile(metadata_path):
        raise FileNotFoundError(
            "IL2CPP requires GameAssembly.dll and global-metadata.dat."
        )
    resolved_dumper = _il2cpp_dumper_path(dumper_path)
    resolved_cache_root = _il2cpp_cache_root(cache_root)
    manifest = {
        "format": _IL2CPP_CACHE_FORMAT,
        "unity_version": str(unity_version),
        "game_assembly_sha256": _sha256_file(binary_path),
        "global_metadata_sha256": _sha256_file(metadata_path),
        "dumper_sha256": _sha256_file(resolved_dumper),
    }
    cache_key = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cache_dir = os.path.join(resolved_cache_root, cache_key)
    if _dummy_cache_is_complete(cache_dir, manifest):
        if log:
            log(f"[generator] Reusing external IL2CPP cache: {cache_dir}")
        return os.path.join(cache_dir, "DummyDll")

    lock_path = os.path.join(resolved_cache_root, f"{cache_key}.lock")
    lock_fd: int | None = None
    deadline = time.monotonic() + 900.0
    while lock_fd is None:
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _dummy_cache_is_complete(cache_dir, manifest):
                return os.path.join(cache_dir, "DummyDll")
            try:
                lock_age = time.time() - os.path.getmtime(lock_path)
            except OSError:
                continue
            if lock_age > 1800:
                try:
                    os.unlink(lock_path)
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting for IL2CPP cache lock: {lock_path}"
                )
            time.sleep(0.25)

    work_dir: str | None = None
    try:
        os.write(lock_fd, str(os.getpid()).encode("ascii"))
        if _dummy_cache_is_complete(cache_dir, manifest):
            return os.path.join(cache_dir, "DummyDll")
        work_dir = tempfile.mkdtemp(
            prefix=f"{cache_key}.building.",
            dir=resolved_cache_root,
        )
        command = [
            resolved_dumper,
            os.path.abspath(binary_path),
            os.path.abspath(metadata_path),
            os.path.abspath(work_dir),
        ]
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        if log:
            log(f"[generator] Building external IL2CPP cache: {work_dir}")
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            encoding="utf-8",
            errors="replace",
        )
        if process.returncode != 0:
            details = (process.stderr or process.stdout or "").strip()
            raise RuntimeError(
                f"Il2CppDumper failed with exit code {process.returncode}: "
                f"{details[-4000:]}"
            )
        dummy_dir = os.path.join(work_dir, "DummyDll")
        dll_names = (
            sorted(name for name in os.listdir(dummy_dir) if name.lower().endswith(".dll"))
            if os.path.isdir(dummy_dir)
            else []
        )
        if not dll_names:
            raise RuntimeError("Il2CppDumper completed without producing DummyDll files.")
        with open(os.path.join(work_dir, "manifest.json"), "w", encoding="utf-8") as manifest_file:
            json.dump(manifest, manifest_file, indent=2, sort_keys=True)
        if os.path.isdir(cache_dir):
            _safe_remove_cache_tree(cache_dir, resolved_cache_root)
        os.replace(work_dir, cache_dir)
        work_dir = None
        return os.path.join(cache_dir, "DummyDll")
    finally:
        if work_dir and os.path.isdir(work_dir):
            _safe_remove_cache_tree(work_dir, resolved_cache_root)
        if lock_fd is not None:
            os.close(lock_fd)
        try:
            os.unlink(lock_path)
        except OSError:
            pass


def _load_generator_dll_directory(
    generator: TypeTreeGenerator,
    dll_dir: str,
    *,
    log: Callable[[str], None] | None = None,
) -> int:
    loaded = 0
    failures: list[str] = []
    for name in sorted(os.listdir(dll_dir)):
        if not name.lower().endswith(".dll"):
            continue
        path = os.path.join(dll_dir, name)
        try:
            with open(path, "rb") as dll_file:
                generator.load_dll(dll_file.read())
            loaded += 1
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    if loaded == 0:
        raise RuntimeError(
            f"No type-tree DLL could be loaded from {dll_dir}: {failures[:5]}"
        )
    if failures and log:
        log(
            f"[generator] Loaded {loaded} DLL(s); "
            f"{len(failures)} failed: {failures[:5]}"
        )
    return loaded


def create_type_tree_generator(
    unity_version: str,
    game_path: str,
    data_path: str,
    compile_method: str,
    *,
    cache_root: str | None = None,
    dumper_path: str | None = None,
    log: Callable[[str], None] | None = None,
) -> TypeTreeGenerator:
    """Create a generator without ever placing DummyDll files in the game."""
    generator = TypeTreeGenerator(unity_version)
    if compile_method == "Mono":
        managed_dir = os.path.join(data_path, "Managed")
        if not os.path.isdir(managed_dir):
            raise FileNotFoundError(f"Managed directory not found: {managed_dir}")
        _load_generator_dll_directory(generator, managed_dir, log=log)
        return generator

    dummy_dir = _ensure_il2cpp_dummy_dlls(
        unity_version,
        game_path,
        data_path,
        cache_root=cache_root,
        dumper_path=dumper_path,
        log=log,
    )
    loaded = _load_generator_dll_directory(generator, dummy_dir, log=log)
    if log:
        log(f"[generator] Loaded {loaded} external IL2CPP DummyDll file(s).")
    return generator


def _version_tuple(value: Any) -> tuple[int, int, int]:
    parts: list[int] = []
    for token in str(value or "").split("."):
        digits = ""
        for character in token:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        parts.append(int(digits))
        if len(parts) == 3:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])  # type: ignore[return-value]


def missing_low_memory_features() -> list[str]:
    """Return missing custom-UnityPy capabilities required by the app."""
    missing: list[str] = []
    try:
        from UnityPy.files.BundleFile import BundleFile
        from UnityPy.files.ObjectReader import ObjectReader
        from UnityPy.files.SerializedFile import SerializedFile
        from UnityPy.helpers import CompressionHelper
    except Exception as exc:
        return [f"UnityPy imports ({type(exc).__name__}: {exc})"]

    if _version_tuple(getattr(UnityPy, "__version__", "0")) < (1, 25, 2):
        missing.append("UnityPy>=1.25.2")
    for owner, name, label in (
        (BundleFile, "save_to", "BundleFile.save_to"),
        (BundleFile, "_write_decompressed_block", "BundleFile._write_decompressed_block"),
        (SerializedFile, "save_to", "SerializedFile.save_to"),
        (SerializedFile, "get_spill_store", "SerializedFile.get_spill_store"),
        (
            CompressionHelper,
            "chunk_based_compress_iter_to_file",
            "CompressionHelper.chunk_based_compress_iter_to_file",
        ),
        (
            CompressionHelper,
            "create_lzma_decompressor",
            "CompressionHelper.create_lzma_decompressor",
        ),
    ):
        if not callable(getattr(owner, name, None)):
            missing.append(label)
    try:
        probe = type("_RawDataProbe", (), {"data": b"modified"})()
        if ObjectReader.get_raw_data(probe) != b"modified":
            missing.append("ObjectReader.get_raw_data(modified-bytes)")
    except Exception:
        missing.append("ObjectReader.get_raw_data(modified-bytes)")
    return missing


def require_low_memory_unitypy() -> None:
    """Raise with actionable details if an incompatible UnityPy is loaded."""
    missing = missing_low_memory_features()
    if not missing:
        return
    loaded_from = getattr(UnityPy, "__file__", "unknown")
    version = getattr(UnityPy, "__version__", "unknown")
    raise RuntimeError(
        "The required custom UnityPy low-memory APIs are missing: "
        f"{', '.join(missing)}. Loaded UnityPy {version} from {loaded_from}."
    )


def _safe_call(obj: Any, name: str) -> None:
    fn = getattr(obj, name, None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


def close_unitypy_env(environment: Any) -> None:
    """Release nested readers, spill stores, and bundle mmaps child-first."""
    if environment is None:
        return

    active = _ACTIVE_ENVIRONMENTS.get()
    if active is not None:
        for index in range(len(active) - 1, -1, -1):
            if active[index] is environment:
                active.pop(index)
                break

    roots: list[Any] = []
    files = getattr(environment, "files", None)
    if isinstance(files, dict):
        roots.extend(files.values())
    primary = getattr(environment, "file", None)
    if primary is not None:
        roots.append(primary)

    seen_items: set[int] = set()
    seen_readers: set[int] = set()

    def dispose_reader(reader: Any) -> None:
        if reader is None or id(reader) in seen_readers:
            return
        seen_readers.add(id(reader))
        _safe_call(reader, "dispose")

    def close_item(item: Any) -> None:
        if item is None or id(item) in seen_items:
            return
        seen_items.add(id(item))

        children = getattr(item, "files", None)
        if isinstance(children, dict):
            for child in list(children.values()):
                close_item(child)

        objects = getattr(item, "objects", None)
        if isinstance(objects, dict):
            for obj in list(objects.values()):
                _safe_call(getattr(obj, "data", None), "cleanup")
            objects.clear()

        # SerializedFile.close() releases its append-only spill store.
        _safe_call(item, "close")
        dispose_reader(getattr(item, "reader", None))

        # Bundle child views must be released before the backing mmap.
        dispose_reader(getattr(item, "_blocks_reader", None))
        _safe_call(item, "_cleanup_temp_blocks_storage")

        # Raw EndianBinaryReader entries expose dispose() on the object itself.
        if not hasattr(item, "reader") and not hasattr(item, "files"):
            dispose_reader(item)

        if isinstance(children, dict):
            children.clear()

    for root in roots:
        close_item(root)

    cabs = getattr(environment, "cabs", None)
    if isinstance(cabs, dict):
        for cab in list(cabs.values()):
            close_item(cab)
        cabs.clear()
    if isinstance(files, dict):
        files.clear()
    for source_stream in getattr(
        environment, "_unity_font_replacer_source_streams", []
    ):
        _safe_call(source_stream, "close")
    try:
        environment._unity_font_replacer_source_streams = []
    except Exception:
        pass
    try:
        environment.file = None
    except Exception:
        pass


def load_unitypy(*args: Any, **kwargs: Any) -> Any:
    """Load through UnityPy and register the Environment for scoped cleanup."""
    source_stream = None
    if (
        len(args) == 1
        and isinstance(args[0], (str, os.PathLike))
        and os.path.isfile(os.fspath(args[0]))
        and re.search(r"\.split\d+$", os.fspath(args[0]), flags=re.IGNORECASE)
        is None
        and "fs" not in kwargs
        and "path" not in kwargs
    ):
        source_path = os.path.abspath(os.fspath(args[0]))
        source_stream = open(source_path, "rb")
        try:
            environment = UnityPy.load(
                source_stream,
                path=os.path.dirname(source_path),
            )
        except BaseException:
            source_stream.close()
            raise
        environment._unity_font_replacer_source_streams = [source_stream]
    else:
        environment = UnityPy.load(*args, **kwargs)
    active = _ACTIVE_ENVIRONMENTS.get()
    if active is not None:
        active.append(environment)
    return environment


def cleanup_unitypy_environments(
    func: Callable[_P, _R],
) -> Callable[_P, _R]:
    """Ensure every Environment loaded by ``func`` is closed on all exits."""

    @wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        environments: list[Any] = []
        token = _ACTIVE_ENVIRONMENTS.set(environments)
        try:
            return func(*args, **kwargs)
        finally:
            pending = list(reversed(environments))
            environments.clear()
            for environment in pending:
                close_unitypy_env(environment)
            _ACTIVE_ENVIRONMENTS.reset(token)

    return wrapper


__all__ = [
    "UnityPy",
    "cleanup_unitypy_environments",
    "close_unitypy_env",
    "create_type_tree_generator",
    "load_unitypy",
    "missing_low_memory_features",
    "require_low_memory_unitypy",
]
