# Unity Font Replacer

Unity 게임의 폰트를 한글 폰트로 교체하는 도구입니다. TTF 폰트와 TextMeshPro SDF 폰트를 모두 지원합니다.

## 요구 사항

- Python 3.8 이상
- 의존성 패키지:
  - UnityPy
  - Pillow

```bash
pip install UnityPy Pillow
```

## 파일 구성

```
Unity_Font_Replacer/
├── unity_font_replacer.py   # 폰트 교체 도구
├── export_fonts.py          # 폰트 추출 도구
├── KR_ASSETS/               # 한글 폰트 에셋
│   ├── Mulmaru.ttf
│   ├── Mulmaru SDF.json
│   ├── Mulmaru SDF Atlas.png
│   ├── NanumGothic.ttf
│   ├── NanumGothic SDF.json
│   └── NanumGothic SDF Atlas.png
└── README.md
```

## 사용법

### 폰트 교체 (unity_font_replacer.py)

#### 기본 사용법

```bash
# 대화형 모드 (게임 경로 입력 프롬프트)
python unity_font_replacer.py

# 게임 경로 지정
python unity_font_replacer.py --gamepath "D:\Games\Muck" --mulmaru
```

#### 명령줄 옵션

| 옵션 | 설명 |
|------|------|
| `--gamepath <경로>` | 게임의 루트 경로 또는 _Data 폴더 경로 |
| `--parse` | 게임의 폰트 정보를 JSON 파일로 출력 |
| `--mulmaru` | 모든 폰트를 Mulmaru 폰트로 일괄 교체 |
| `--nanumgothic` | 모든 폰트를 NanumGothic 폰트로 일괄 교체 |
| `--sdfonly` | SDF 폰트만 교체 (TTF 폰트 제외) |
| `--ttfonly` | TTF 폰트만 교체 (SDF 폰트 제외) |
| `--list <JSON파일>` | JSON 파일을 참조하여 개별 폰트 교체 |

#### 사용 예시

```bash
# 폰트 정보 파싱 (Muck.json 생성)
python unity_font_replacer.py --gamepath "D:\Games\Muck" --parse

# Mulmaru 폰트로 모든 폰트 교체
python unity_font_replacer.py --gamepath "D:\Games\Muck" --mulmaru

# NanumGothic 폰트로 SDF 폰트만 교체
python unity_font_replacer.py --gamepath "D:\Games\Muck" --nanumgothic --sdfonly

# JSON 파일을 사용한 개별 폰트 교체
python unity_font_replacer.py --gamepath "D:\Games\Muck" --list Muck.json
```

### 개별 폰트 교체 (--list 옵션)

1. `--parse` 옵션으로 폰트 정보 JSON 파일 생성
2. JSON 파일에서 교체할 폰트의 `Replace_to` 필드에 원하는 폰트 이름 입력
3. `--list` 옵션으로 교체 실행

JSON 파일 형식:
```json
{
    "sharedassets0.assets|TTF|123": {
        "Name": "Arial",
        "Path_ID": 123,
        "Type": "TTF",
        "File": "sharedassets0.assets",
        "Replace_to": "Mulmaru"
    },
    "sharedassets0.assets|SDF|456": {
        "Name": "Arial SDF",
        "Path_ID": 456,
        "Type": "SDF",
        "File": "sharedassets0.assets",
        "Replace_to": ""
    }
}
```

`Replace_to` 필드가 비어있으면 해당 폰트는 교체되지 않습니다.

`Replace_to`에 사용할 수 있는 폰트 이름 형식:
- `Mulmaru` 또는 `Mulmaru.ttf`
- `NanumGothic` 또는 `NanumGothic.ttf`
- `Mulmaru SDF` 또는 `Mulmaru SDF.json` 또는 `Mulmaru SDF Atlas.png`

### 폰트 추출 (export_fonts.py)

자신이 개발한 Unity 게임에서 SDF 폰트를 추출하는 도구입니다.

```bash
# 게임 루트 폴더에서 실행
cd "D:\MyGame"
python C:\path\to\export_fonts.py

# 또는 _Data 폴더에서 실행
cd "D:\MyGame\MyGame_Data"
python C:\path\to\export_fonts.py
```

현재 작업 디렉토리에 JSON 파일과 Atlas PNG 파일이 생성됩니다.

## 지원하는 폰트

### 기본 제공 폰트

| 폰트 이름 | 설명 |
|-----------|------|
| Mulmaru | 물마루체 |
| NanumGothic | 나눔고딕 |

### 커스텀 폰트 추가

`KR_ASSETS` 폴더에 다음 파일을 추가하면 됩니다:

- `폰트이름.ttf` - TTF 폰트 파일
- `폰트이름 SDF.json` - SDF 폰트 데이터
- `폰트이름 SDF Atlas.png` - SDF Atlas 텍스처

SDF 폰트 데이터는 `export_fonts.py`로 추출할 수 있습니다.

## 주의 사항

- 게임 파일을 수정하기 전에 반드시 백업하세요.
- 일부 게임에서는 무결성 검사로 인해 수정된 파일이 작동하지 않을 수 있습니다.
- 온라인 게임에서 사용 시 이용 약관을 확인하세요.

## Special Thanks

- [UnityPy](https://github.com/K0lb3/UnityPy) by K0lb3
- [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) by Perfare
- [나눔고딕](https://hangeul.naver.com/font) by NAVER | [License](https://help.naver.com/service/30016/contents/18088?osType=PC&lang=ko)
- [물마루](https://github.com/mushsooni/mulmaru) by mushsooni

## 라이선스

MIT License
