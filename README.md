[> for English verison of README.md](README_EN.md)

# Unity Font Replacer

Unity 게임의 폰트를 한글 폰트로 교체하는 도구입니다. TTF 폰트와 TextMeshPro SDF 폰트를 모두 지원합니다.

## 빠른 시작 (EXE 기준)

릴리즈 ZIP을 풀면 보통 아래처럼 구성됩니다.

```
release/
├── unity_font_replacer.exe
├── export_fonts.exe
├── KR_ASSETS/
├── Il2CppDumper/
└── README.md
```

권장 실행 방식:

```bat
cd release
unity_font_replacer.exe
```

- `unity_font_replacer.exe`: 폰트 교체 도구 (한국어 UI)
- `unity_font_replacer_en.exe`: 폰트 교체 도구 (영문 UI)
- `export_fonts.exe`: TMP SDF 폰트 추출 도구 (한국어 UI)
- `export_fonts_en.exe`: TMP SDF 폰트 추출 도구 (영문 UI)

## 폰트 교체 (unity_font_replacer.exe)

### 기본 사용법

```bat
:: 대화형 모드 (게임 경로 입력)
unity_font_replacer.exe

:: 게임 경로 지정 + Mulmaru 일괄 교체
unity_font_replacer.exe --gamepath "D:\Games\Muck" --mulmaru
```

### 명령줄 옵션

| 옵션 | 설명 |
|------|------|
| `--gamepath <경로>` | 게임 루트 경로 또는 `_Data` 폴더 경로 |
| `--parse` | 게임 폰트 정보를 JSON 파일로 출력 |
| `--mulmaru` | 모든 폰트를 Mulmaru로 일괄 교체 |
| `--nanumgothic` | 모든 폰트를 NanumGothic으로 일괄 교체 |
| `--sdfonly` | SDF 폰트만 교체 |
| `--ttfonly` | TTF 폰트만 교체 |
| `--list <JSON파일>` | JSON 파일 기준 개별 폰트 교체 |

### 사용 예시

```bat
:: 폰트 정보 파싱 (Muck.json 생성)
unity_font_replacer.exe --gamepath "D:\Games\Muck" --parse

:: Mulmaru로 전체 교체
unity_font_replacer.exe --gamepath "D:\Games\Muck" --mulmaru

:: NanumGothic으로 SDF만 교체
unity_font_replacer.exe --gamepath "D:\Games\Muck" --nanumgothic --sdfonly

:: JSON 기반 개별 교체
unity_font_replacer.exe --gamepath "D:\Games\Muck" --list Muck.json
```

## 개별 폰트 교체 (--list)

1. `--parse`로 폰트 정보 JSON 생성
2. JSON의 `Replace_to` 필드에 원하는 폰트 이름 입력
3. `--list`로 교체 실행

JSON 예시:

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

- `Replace_to`가 비어 있으면 해당 항목은 교체하지 않습니다.
- `Replace_to` 예시:
  - `Mulmaru` 또는 `Mulmaru.ttf`
  - `NanumGothic` 또는 `NanumGothic.ttf`
  - `Mulmaru SDF` 또는 `Mulmaru SDF.json` 또는 `Mulmaru SDF Atlas.png`

## 폰트 추출 (export_fonts.exe)

TextMeshPro SDF 폰트를 추출하는 도구입니다.

```bat
:: 경로 인자 방식 (권장)
export_fonts.exe "D:\MyGame"

:: 또는 _Data 직접 지정
export_fonts.exe "D:\MyGame\MyGame_Data"

:: 인자 생략 시 대화형 프롬프트
export_fonts.exe
```

실행 후 현재 작업 디렉터리에 다음 파일이 생성됩니다.
- `TMP_FontAsset이름.json`
- `TMP_FontAsset이름 SDF Atlas.png`
- (있는 경우) `Material_*.json`

## 지원 폰트

| 폰트 이름 | 설명 |
|-----------|------|
| Mulmaru | 물마루체 |
| NanumGothic | 나눔고딕 |

## 커스텀 폰트 추가

`KR_ASSETS` 폴더에 아래 파일을 추가하면 됩니다.

- `폰트이름.ttf`
- `폰트이름 SDF.json`
- `폰트이름 SDF Atlas.png`

SDF 데이터는 `export_fonts.exe`로 추출할 수 있습니다.

## 소스 실행 (선택)

EXE 대신 Python 소스로 실행하려면:

### 요구 사항

- Python 3.12 권장
- 패키지: `UnityPy`, `TypeTreeGeneratorAPI`, `Pillow`

```bash
pip install UnityPy TypeTreeGeneratorAPI Pillow
```

### 실행 예시

```bash
python unity_font_replacer.py --gamepath "D:\Games\Muck" --mulmaru
python export_fonts.py "D:\MyGame"
```

## 주의 사항

- 저장 시 원본 압축 방식 유지를 시도하며, 실패 시 `lz4 -> safe-none` 순으로 폴백합니다.
- TMP(FontAsset) 파싱/교체를 위해 `TypeTreeGeneratorAPI`가 필요합니다.
- 게임 파일 수정 전 백업을 권장합니다.
- 일부 게임은 무결성 검사로 수정 파일이 원복될 수 있습니다.
- 온라인 게임 사용 시 이용 약관을 확인하세요.

## Special Thanks

- [UnityPy](https://github.com/K0lb3/UnityPy) by K0lb3
- [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) by Perfare
- [나눔고딕](https://hangeul.naver.com/font) by NAVER | [License](https://help.naver.com/service/30016/contents/18088?osType=PC&lang=ko)
- [물마루](https://github.com/mushsooni/mulmaru) by mushsooni | [License](https://github.com/mushsooni/mulmaru/blob/main/LICENSE_ko)

## 라이선스

MIT License
