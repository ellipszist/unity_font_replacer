"""UnityPy runtime selection and deterministic resource cleanup.

Source runs prefer the sibling custom UnityPy checkout. Frozen builds use the
UnityPy copy bundled by PyInstaller. Both paths are checked for the low-memory
load/save features required by this project.
"""

from __future__ import annotations

import os
import re
import sys
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


_P = ParamSpec("_P")
_R = TypeVar("_R")
_ACTIVE_ENVIRONMENTS: ContextVar[list[Any] | None] = ContextVar(
    "unitypy_active_environments", default=None
)


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
    "load_unitypy",
    "missing_low_memory_features",
    "require_low_memory_unitypy",
]
