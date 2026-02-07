[> for Korean verison of README.md](README.md)

# Unity Font Replacer

A tool to replace Unity game fonts with custom fonts. Supports both TTF fonts and TextMeshPro SDF fonts.

## Requirements

- Python 3.8+
- Dependencies:
  - UnityPy
  - Pillow

```bash
pip install UnityPy Pillow
```

## File Layout

```
Unity_Font_Replacer/
├── unity_font_replacer.py    # Font replacement tool (Korean UI)
├── unity_font_replacer_en.py # Font replacement tool (English UI)
├── export_fonts.py           # Font export tool (Korean UI)
├── export_fonts_en.py        # Font export tool (English UI)
├── KR_ASSETS/                # Korean font assets
│   ├── Mulmaru.ttf
│   ├── Mulmaru SDF.json
│   ├── Mulmaru SDF Atlas.png
│   ├── NanumGothic.ttf
│   ├── NanumGothic SDF.json
│   └── NanumGothic SDF Atlas.png
└── README.md
```

## Usage

Use the *_en.py scripts for English UI.

### Font Replacement (unity_font_replacer.py)

#### Basic Usage

```bash
# Interactive mode (prompt for game path)
python unity_font_replacer.py

# Provide game path
python unity_font_replacer.py --gamepath "D:\Games\Muck" --mulmaru
```

#### Command Line Options

| Option | Description |
|------|------|
| `--gamepath <path>` | Game root path or _Data folder path |
| `--parse` | Export font info to a JSON file |
| `--mulmaru` | Replace all fonts with Mulmaru |
| `--nanumgothic` | Replace all fonts with NanumGothic |
| `--sdfonly` | Replace SDF fonts only (exclude TTF) |
| `--ttfonly` | Replace TTF fonts only (exclude SDF) |
| `--list <JSON>` | Replace fonts based on a JSON file |

#### Examples

```bash
# Parse font info (create Muck.json)
python unity_font_replacer.py --gamepath "D:\Games\Muck" --parse

# Replace all fonts with Mulmaru
python unity_font_replacer.py --gamepath "D:\Games\Muck" --mulmaru

# Replace SDF fonts only with NanumGothic
python unity_font_replacer.py --gamepath "D:\Games\Muck" --nanumgothic --sdfonly

# Replace fonts using a JSON file
python unity_font_replacer.py --gamepath "D:\Games\Muck" --list Muck.json
```

### Per-Font Replacement (--list)

1. Run `--parse` to create a JSON file with font info
2. Set the target font name in the `Replace_to` field
3. Run `--list` to apply replacements

JSON format:
```json
{
    "sharedassets0.assets|sharedassets0.assets|Arial|TTF|123": {
        "File": "sharedassets0.assets",
        "assets_name": "sharedassets0.assets",
        "Path_ID": 123,
        "Type": "TTF",
        "Name": "Arial",
        "Replace_to": "Mulmaru"
    },
    "sharedassets0.assets|sharedassets0.assets|Arial SDF|SDF|456": {
        "File": "sharedassets0.assets",
        "assets_name": "sharedassets0.assets",
        "Path_ID": 456,
        "Type": "SDF",
        "Name": "Arial SDF",
        "Replace_to": ""
    }
}
```

If `Replace_to` is empty, the font will not be replaced.

Valid `Replace_to` formats:
- `Mulmaru` or `Mulmaru.ttf`
- `NanumGothic` or `NanumGothic.ttf`
- `Mulmaru SDF` or `Mulmaru SDF.json` or `Mulmaru SDF Atlas.png`

### Font Export (export_fonts.py)

A tool to export TextMeshPro SDF fonts from your own Unity project/game for build custom SDF font.

```bash
# Run from the game root folder
cd "D:\MyGame"
python C:\path\to\export_fonts.py

# Or run from the _Data folder
cd "D:\MyGame\MyGame_Data"
python C:\path\to\export_fonts.py
```

JSON files, atlas PNG files, and (if present) material JSON files are created in the current working directory.

## Supported Fonts

### Included Fonts

| Font | Description |
|-----------|------|
| Mulmaru | Mulmaru Korean font |
| NanumGothic | NanumGothic Korean font |

### Adding Custom Fonts

Add the following files to `KR_ASSETS`:

- `FontName.ttf` - TTF font file
- `FontName SDF.json` - SDF font data
- `FontName SDF Atlas.png` - SDF atlas texture

SDF font data can be exported with `export_fonts.py`.

## Notes

- Files are saved preserving the original compression when possible, falling back to LZ4 then uncompressed.
- Always back up game files before modifying.
- Some games may fail integrity checks after modification.
- Check Terms of Service before using in online games.

## Special Thanks

- [UnityPy](https://github.com/K0lb3/UnityPy) by K0lb3
- [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) by Perfare
- [NanumGothic](https://hangeul.naver.com/font) by NAVER | [License](https://help.naver.com/service/30016/contents/18088?osType=PC&lang=ko)
- [Mulmaru](https://github.com/mushsooni/mulmaru) by mushsooni | [License](https://github.com/mushsooni/mulmaru/blob/main/LICENSE_ko)

## License

MIT License
