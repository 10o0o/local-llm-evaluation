# 로컬·클라우드 LLM 코딩 평가

코딩 문제 풀이에 쓸 로컬 LLM을 고르기 위한 비교·평가 프로젝트입니다. llama.cpp로 Qwen3.6과 Gemma4를 구동하고, GPU 레이어·스레드·context 등의 설정을 바꿔 보면서 클라우드 모델 Luna·Motif-3와 비교했습니다.

COCI 공개 문제 10개를 모델마다 두 번씩 풀게 했습니다. 답변에서 Python 코드를 추출해 공식 테스트 데이터로 실행하고, 정답 여부와 설명 품질을 따로 평가했습니다. 요청 설정, 원본 응답, 오류, 채점 결과는 저장소에서 확인할 수 있습니다.

## 빠르게 실행해 보기

Linux 또는 WSL에서 실행합니다. [uv](https://docs.astral.sh/uv/getting-started/installation/)를 설치한 뒤 아래 명령을 실행하면 Python 3.12.14와 고정된 의존성을 준비합니다.

```bash
git clone https://github.com/10o0o/local-llm-evaluation.git
cd local-llm-evaluation
uv sync --locked

uv run --offline llm-eval demo offline --output /tmp/llm-eval-demo
cat /tmp/llm-eval-demo/report.md
```

GPU나 API 키 없이 코드 추출부터 채점까지 확인하는 **합성 예제**입니다. 예상 결과는 `AC 1 / WA 1 / NO_CODE 1`이며 실제 모델의 평가 점수와는 별개입니다. 다시 실행할 때는 다른 출력 폴더를 지정하거나 `--output`을 생략하세요.

## 실제 테스트 데이터 준비

문제문과 모델 응답은 저장소에 있습니다. 저장된 코드를 재채점하려면 COCI 2025/2026의 테스트 입력·출력을 추가로 받아야 합니다. 다운로드는 약 319 MB, 설치 후 데이터는 약 724 MB입니다. 임시 압축 해제 파일을 포함해 여유 공간 3 GB를 권장합니다.

```bash
uv run llm-eval data setup
uv run llm-eval validate
```

`data setup`은 아래 공식 ZIP을 내려받아 SHA-256을 확인하고, 사용한 10문항의 입력·출력만 배치합니다. 설치할 폴더가 이미 있으면 덮어쓰지 않고 중단합니다. 이미 데이터가 있다면 `validate`부터 실행하세요.

| 공식 다운로드 | 사용하는 문항 |
| --- | --- |
| [contest4_testdata.zip](https://hsin.hr/coci/contest4_testdata.zip) | tomahawk |
| [contest5_testdata.zip](https://hsin.hr/coci/contest5_testdata.zip) | skare, struktura, tezina, pet |
| [contest6_testdata.zip](https://hsin.hr/coci/contest6_testdata.zip) | cokolada, dzeparac, prepisivanje, ucionica, skijanje |

설치 후 파일은 다음처럼 놓입니다. 경로를 직접 수정할 필요는 없습니다.

```text
data/coci/
├── problems.json
└── 2025_2026/
    ├── contest4/testdata/tomahawk/tomahawk.in.* · tomahawk.out.*
    ├── contest5/testdata/<문항>/<문항>.in.* · <문항>.out.*
    └── contest6/testdata/<문항>/<문항>.in.* · <문항>.out.*
```

검증이 끝나면 10문항이 `[OK]`로 표시되고 마지막에 `Validation PASSED`가 나옵니다. ZIP과 테스트 데이터는 `.gitignore` 대상입니다.

이미 ZIP을 받아 두었다면 세 파일을 같은 폴더에 두고 실행할 수 있습니다.

```bash
uv run --offline llm-eval data setup --archives-dir /path/to/coci-zips
uv run --offline llm-eval validate
```

공식 다운로드 주소는 시즌이 바뀌면 내용도 바뀔 수 있습니다. [데이터 목록](data/coci/testdata-manifest.json)에 2026-09-30 확인한 2025/2026 ZIP의 해시와 문항 정보를 고정했습니다. 해시가 다르면 설치가 중단되므로, 검사를 건너뛰지 말고 해당 시즌의 원본 ZIP을 확인하세요.

## 저장된 코드 재채점하기

모델이나 API 키 없이 `results/benchmark/`에 저장된 코드를 다시 채점할 수 있습니다. 먼저 Qwen의 Škare 1회차만 실행해 봅니다. 로컬 모델 서버가 켜져 있다면 종료한 뒤 실행하세요.

```bash
uv run --offline llm-eval judge batch \
  --problems coci_2025_2026_c5_skare --models qwen36 --rounds 1
```

실행마다 `results/judging/<세션 ID>/`가 만들어집니다. 방금 실행한 결과는 아래 명령으로 확인할 수 있습니다.

```bash
uv run --offline python - <<'PY'
import json
from pathlib import Path
path = max(Path("results/judging").glob("*/manifest.json"))
session = json.loads(path.read_text())
print(path)
for entry in session["entries"]:
    print(entry["problem_name"], entry["model"], entry["round"], entry["status"])
PY
```

전체 10문항·4모델·2회차를 채점하려면 다음 명령을 사용합니다.

```bash
uv run --offline llm-eval judge batch --problems all --models all --rounds all
```

기존 응답과 이전 채점 세션은 그대로 남습니다. 채점은 공식 1배 시간 제한을 사용하며 장비에 따라 실행 시간과 TLE 판정이 달라질 수 있습니다. Judge는 코드를 실행하므로 신뢰할 수 있는 결과물만 사용하세요.

### 새 응답을 생성하려면

- **로컬:** llama.cpp와 GGUF 모델을 준비하고 `LLAMA_ROOT`, `QWEN36_MODEL_PATH` 또는 `GEMMA4_MODEL_PATH`를 지정합니다. [로컬 실행 안내](docs/operations/local-runbook.md)에 서버 시작·워밍업·생성 명령이 있습니다
- **클라우드:** Luna는 `openai_secret_key`, Motif-3는 `morph_secret_key` 환경 변수를 사용합니다. [클라우드 실행 안내](docs/operations/cloud-runbook.md)에서 요청 설정을 확인하세요. 실제 API 호출에는 비용이 발생합니다

`generate`에서 `--round`를 생략하면 새 응답을 `results/demo/`에 저장합니다. 위의 `demo offline`과 달리 실제 모델을 호출하며, 같은 문항·모델로 다시 실행하면 해당 시연 파일을 갱신합니다.

## 평가 결과

2026-09-17에 80회 시도 중 정상 응답 78건, 호출 실패 2건을 기록했습니다. 호출 실패와 코드 미생성을 포함해 모델당 20회를 분모로 계산했습니다.

| 모델 | 정상 응답 / 시도 | 공식 1배 시간 제한 AC | 프로젝트 정책 AC |
| --- | ---: | ---: | ---: |
| Qwen3.6 · 로컬 | 20 / 20 | 12 / 20 | 14 / 20 |
| Gemma4 · 로컬 | 20 / 20 | 9 / 20 | 9 / 20 |
| Luna · 클라우드 | 20 / 20 | 15 / 20 | 16 / 20 |
| Motif-3 · 클라우드 | 18 / 20 | 13 / 20 | 13 / 20 |

프로젝트 정책은 Težina·Pet·Učionica·Skijanje에 2배 시간 제한을 적용합니다. 수정한 코드의 통과는 위 점수에 합치지 않았습니다. AC는 내려받은 테스트 데이터를 통과했다는 뜻입니다.

이 결과와 설명 평가를 바탕으로 로컬 후보는 Qwen3.6을 선택했습니다. 10개 공개 문제를 사용했고 모델별 생성 설정이 달라, 결과는 이 실험 조건 안에서 비교합니다. 자세한 수치와 실패 사례는 [최종 선정 보고서](docs/project/model-selection-report.md)와 [로컬·클라우드 비교](docs/project/local-cloud-comparison.md)에 있습니다.

## 관련 문서

- [전체 실행 안내](docs/operations/reproduction-guide.md): 생성·재개·채점·평가 명령
- [아키텍처](docs/architecture.md): CLI와 모듈별 역할
- [실행 환경](docs/operations/environment.md): 장비, 서버 설정, 측정 항목
- [평가 절차](docs/operations/evaluation.md) · [결과 파일 안내](results/README.md)
- [평가 질문](docs/project/evaluation-questions.md) · [요구사항](docs/project/requirements.md)
- [비교 실험 범위](docs/project/experiment-scope.md) · [자료 출처](docs/sources/README.md)
- [결정 이력](docs/history/decision-log.md) · [유지보수 이력](docs/history/maintenance-log.md)
