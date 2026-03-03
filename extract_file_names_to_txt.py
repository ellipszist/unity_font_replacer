import json
import sys
from pathlib import Path
from typing import Any, Iterator


def iter_file_values(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "File" and isinstance(value, str):
                yield value
            yield from iter_file_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_file_values(item)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: drag-and-drop a JSON file onto this script.")
        print("Example: python extract_file_names_to_txt.py your_file.json")
        return

    input_path = Path(sys.argv[1])
    output_path = input_path.with_suffix(".txt")

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)

    files = list(iter_file_values(data))

    unique_files = list(dict.fromkeys(files))
    output_path.write_text(",".join(unique_files), encoding="utf-8")

    print(f"Saved {len(unique_files)} unique names to: {output_path}")


if __name__ == "__main__":
    main()
