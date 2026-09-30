# 로컬·클라우드 LLM 코딩 평가

개인 알고리즘 학습에 사용할 로컬 LLM을 고르기 위해, 공개 코딩 문제에 대한 **생성 코드의 실행 결과와 설명 품질**을 비교한 프로젝트입니다. 로컬 모델을 직접 구동하고 추론·서빙 파라미터를 바꿔 보며, 외부 LLM API와 같은 문제로 비교했습니다.

Python 평가 도구는 모델 호출부터 원본 기록, 코드 추출, 로컬 채점, 보고서 생성까지 연결합니다. 설정과 원본 응답, 실패 기록을 함께 남겨 결과가 나온 조건을 다시 확인할 수 있게 했습니다.

[설계와 기여 범위](docs/project/portfolio-notes.md) · [실제 평가 결과](docs/project/model-selection-report.md) · [로컬·클라우드 비교](docs/project/local-cloud-comparison.md) · [전체 실행 안내](docs/operations/reproduction-guide.md)

## 한눈에 보기

- 대상: 로컬 Qwen3.6·Gemma4, 클라우드 Luna·Motif-3
- 입력: 공식 테스트 데이터가 공개된 COCI 문제 10개, 모델별 2회 요청
- 완료 범위: **80회 시도 기록, 정상 응답 78건, 호출 실패 2건**과 최종 평가 보고서
- 결과: 이 문제·설정·평가 정책에서는 Qwen3.6을 로컬 후보로 선택
- 기술: Python, llama.cpp, OpenAI SDK, Responses·Chat Completions 호환 API, 파일 기반 실행 기록, 로컬 Judge
- 성격: 개인 실험·평가 도구

## 직접 한 일과 AI 활용

**실험 수행과 설정 조정은 직접 했고, 도구 구현·유지보수에는 AI 지원을 활용했습니다.** 로컬 서버를 띄우고 GPU 레이어 수, CPU MoE 배치, 스레드, context·출력·reasoning 예산 등 추론·서빙 옵션을 조정하며 동작과 성능을 살폈습니다. 외부 API로 클라우드 모델을 호출하고 공개 코딩 문제로 로컬 결과와 비교했습니다.

[Qwen 서버 셸](configs/llama.cpp/qwen36.sh)과 [Gemma 서버 셸](configs/llama.cpp/gemma4.sh)은 **최종 저장 설정**입니다. 당시 탐색한 모든 조합이 기록된 것은 아니므로 실행별 조건과 대조 측정의 범위를 구분합니다.

CLI 통합, API 어댑터 확장, 기록·잠금·Judge 및 평가 도구의 구현·유지보수에는 AI 지원이 포함됐습니다. 해당 작업과 모의 테스트 이력은 [유지보수 기록](docs/history/maintenance-log.md)에 남아 있습니다. 그 과정에서 실험 수행과 도구 유지보수의 범위를 나누어 기록했습니다.

## 평가 흐름과 설계 판단

```text
공개 문제문 + 공식 제한
  → 로컬 서버 / 클라우드 API 호출
  → 요청 설정·원본 응답·오류·추출 코드 보존
  → 생성 종료와 모델 서버 종료 확인
  → 로컬 Judge로 공식 제한 채점
  → 시간 완화·최소 수정·설명 평가는 별도로 기록
  → 모델별 집계와 선정 보고서
```

1. **그럴듯한 답변과 실행 가능한 코드를 구분했습니다.** 공식 테스트를 확보할 수 있는 문제를 골라 코드의 실제 통과 여부를 확인하고, 설명 평가는 별도 항목으로 두었습니다
2. **생성과 채점을 분리했습니다.** 모델 서버와 채점 프로세스의 자원 경합이 시간 초과 판정에 영향을 줄 수 있어, 모든 생성과 서버 종료 후 채점하도록 했습니다
3. **실패와 변경 전 결과를 남겼습니다.** 호출 오류를 분모에서 지우지 않고, 원본과 수정본·완화된 시간 제한 결과를 분리했습니다. 중단·재개 시 기존 기록을 덮어쓰거나 같은 유료 요청을 중복 실행하지 않도록 검사합니다

구현을 읽으려면 [API 어댑터](src/llm_eval/cloud/client.py), [생성·재개](src/llm_eval/cloud/generation.py), [작업 잠금](src/llm_eval/shared/workloads.py), [Judge](src/llm_eval/judging/engine.py), [평가·보고](src/llm_eval/judging/reporting.py)를 보세요. 전체 호출 관계는 [아키텍처](docs/architecture.md)에 있습니다.

## 먼저 체험하기

GPU, 모델 가중치, API 키 없이 **합성 응답을 사용하는 오프라인 데모**로 도구의 흐름을 확인할 수 있습니다. 데모 숫자는 실제 모델 성능이 아닙니다.

### 1. 설치

Linux 또는 WSL 환경의 Python 3.12.14와 [uv](https://docs.astral.sh/uv/getting-started/installation/)가 필요합니다. 최초 설치에는 패키지 다운로드를 위한 네트워크가 필요할 수 있습니다.

```bash
git clone https://github.com/10o0o/local-llm-evaluation.git
cd local-llm-evaluation
uv sync --locked
```

### 2. 오프라인 데모 실행

```bash
uv run --offline llm-eval demo offline --output /tmp/llm-eval-portfolio-demo
```

### 3. 결과 확인

```bash
cat /tmp/llm-eval-portfolio-demo/report.md
```

예상 결과는 **AC 1 / WA 1 / NO_CODE 1**입니다. 보고서와 각 예제의 JSON에서 판정·추출 코드·호출 상태를 확인할 수 있습니다. 지정한 출력 폴더가 이미 있으면 덮어쓰지 않으므로 다시 실행할 때는 새 폴더 이름을 사용하세요.

### 실제 모델로 다시 실험하려면

- 로컬 생성: GGUF 가중치와 llama.cpp 런타임을 준비하고 [로컬 실행 안내](docs/operations/local-runbook.md)를 따릅니다
- 클라우드 생성: 본인 API 키와 과금 확인이 필요합니다. [클라우드 실행 안내](docs/operations/cloud-runbook.md)의 모델별 설정을 확인하세요
- 저장된 응답의 재채점: COCI 공식 테스트 데이터를 별도로 준비해야 합니다
- 기존 `generate`에서 `--round`를 생략하는 시연은 실제 모델/API를 호출합니다. 위 합성 데모와 다릅니다

벤치마크 생성·재개·채점·평가 명령과 파일 위치는 [전체 실행 안내](docs/operations/reproduction-guide.md)에 모았습니다. API 키, 모델 가중치와 개인 환경 파일은 저장소에 추가하지 않습니다.

## 실제 결과

2026-09-17에 완료한 [평가 보고서](results/evaluation/20260917_131133_521417Z_98657c40/reports/20260917_134421_178261Z_7affc20f/report.md)의 집계입니다. 모든 모델의 분모는 20회이며 호출 실패와 코드 미생성도 포함합니다.

| 모델 | 정상 응답 / 시도 | 공식 1배 시간 제한 AC | 프로젝트 정책 AC |
| --- | ---: | ---: | ---: |
| Qwen3.6 · 로컬 | 20 / 20 | 12 / 20 | 14 / 20 |
| Gemma4 · 로컬 | 20 / 20 | 9 / 20 | 9 / 20 |
| Luna · 클라우드 | 20 / 20 | 15 / 20 | 16 / 20 |
| Motif-3 · 클라우드 | 18 / 20 | 13 / 20 | 13 / 20 |

**프로젝트 정책 AC에는 지정한 네 문항의 2배 시간 제한이 반영됩니다.** 공식 제한 AC와 같은 지표가 아니며, 수정한 코드의 통과는 두 열 모두에 합치지 않습니다. 여기서 AC는 보유한 테스트를 통과했다는 뜻으로, 온라인 저지의 공식 제출 판정은 아닙니다.

이 조건에서 Qwen3.6을 로컬 후보로 선택했습니다. 클라우드는 별도 비교 축이며 로컬 선정에 합산하지 않았습니다. 제공자별 생성 설정·토큰 예산이 달라 이 표를 모델의 일반적인 성능 순위로 해석하지 않습니다.

대표 실패도 보존했습니다. 함수 호출 괄호 누락, 설명과 다른 미완성 코드, 출력 한도 소진, 제공자 5xx를 나누어 살폈습니다. [선정 근거와 실패 사례](docs/project/model-selection-report.md), [원본·보조 결과의 구분](results/README.md)을 확인할 수 있습니다.

## 해석의 한계

- **작은 공개 평가셋:** 10문항·한 대의 로컬 장비에 한정됩니다. 공개 문제나 풀이가 모델 학습 데이터에 포함됐을 가능성을 검증하지 않았으므로, 새로운 문제에 대한 일반화 성능으로 단정하지 않습니다
- **독립 요청과 독립 표본의 차이:** 이전 답변을 넘기지 않고 새로 요청했지만 Qwen의 10문항은 두 회차 응답이 바이트 단위로 같았습니다. 20개의 독립적인 품질 관측으로 취급하지 않습니다
- **조건과 정책의 차이:** 로컬·클라우드의 생성 설정이 다르고, 일부 시간 제한 완화 기준은 생성 도중 확정했습니다. 사전등록된 통제 실험이 아닙니다
- **튜닝 이력의 한계:** 서버 옵션을 탐색했지만 모든 조합의 대조 측정을 남기지는 않았습니다. 현재 셸의 값으로 과거 실행 조건이나 튜닝 전후 개선율을 소급하지 않습니다
- **Judge의 범위:** 시간·출력 제한을 적용하지만 메모리 제한 강제, RSS·MLE 판정과 완전한 보안 샌드박스는 구현하지 않았습니다. 출처를 신뢰할 수 없는 코드를 이 도구만 믿고 실행하면 안 됩니다
- **관측과 평가의 한계:** 설명 채점은 1인 평가이며, GPU 값은 장치 전체 관측입니다. 비용 추정은 청구서와 대조한 실결제액이 아닙니다

## 다음 검증 과제

아래는 이번에 완료한 성과가 아니라 후속 과제입니다.

- 서버 빌드·모델 파일 해시와 설정 조합을 실행별로 고정해 파라미터 조정의 효과를 대조 측정
- 평가셋 확대와 공개 문제의 학습 데이터 오염 가능성 점검
- 평가 정책을 실험 전에 확정하고, 반복 응답 중복·설명 평가자 간 차이를 함께 확인
- 생성 코드 실행의 격리와 메모리 제한을 보완

## 문서와 재현 근거

- [설계·직접 수행·AI 지원·설정 탐색](docs/project/portfolio-notes.md)
- [전체 설치·실행·결과 확인](docs/operations/reproduction-guide.md)
- [아키텍처와 파일별 책임](docs/architecture.md)
- [최종 선정 보고서](docs/project/model-selection-report.md) · [로컬·클라우드 비교](docs/project/local-cloud-comparison.md)
- [실행 환경과 측정 범위](docs/operations/environment.md) · [평가 절차](docs/operations/evaluation.md)
- [요구사항](docs/project/requirements.md) · [평가 질문](docs/project/evaluation-questions.md) · [발제 원문](docs/project/assignment.md)
- [결정 이력](docs/history/decision-log.md) · [구현·검증 이력](docs/history/maintenance-log.md)

과거 기록의 수치와 실행 조건은 당시 기준으로 보존합니다. 이번 포트폴리오 정리는 새로운 모델 실험이나 성능 개선 결과를 추가한 것이 아닙니다.
