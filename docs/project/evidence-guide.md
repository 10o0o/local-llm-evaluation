# 프로젝트 평가 근거 안내

실험 목적에서 모델 선정까지 이어지는 근거를 정리했다. 각 문서의 실행 조건, 원본 기록, 실패 사례와 한계를 함께 확인한다.

| 확인할 내용 | 이 저장소의 근거 |
| --- | --- |
| 어떤 문제를 해결하려 했는가 | [사용 사례와 선정 기준](requirements.md) |
| 왜 이 후보를 비교했는가 | [후보 조사와 제외 이력](model-candidates.md) |
| 무엇을 어떤 환경에서 실행했는가 | [실행 환경](../operations/environment.md), [로컬 실행](../operations/local-runbook.md), [Cloud 실행](../operations/cloud-runbook.md) |
| 비교 입력과 평가 조건은 무엇인가 | [평가 질문 10개](evaluation-questions.md), [평가 절차](../operations/evaluation.md) |
| 실패와 측정 누락을 어떻게 다뤘는가 | [기록 구현과 한계](../operations/recording.md), [결과 파일 안내](../../results/README.md) |
| 실측이 어떤 판단으로 이어졌는가 | [Local–Cloud 비교](local-cloud-comparison.md), [최종 선정 보고서](model-selection-report.md) |
| 다른 환경에서 어떻게 확인하는가 | [README](../../README.md), [재현 안내](../operations/reproduction-guide.md) |

## 결과를 읽을 때의 기준

- 모델별 시도 수는 20회로 유지하고, 정상 응답·실패·코드 미생성을 나누어 확인한다
- 공식 1배 시간 제한의 AC와 프로젝트 정책 AC를 구분한다. 수정본의 통과는 원본 정답률에 더하지 않는다
- 설명 점수와 응답 시간은 각각의 집계 대상 수와 함께 읽는다. 미측정 값이나 확인하지 못한 비용을 0으로 간주하지 않는다
- 평가 조건을 생성 도중 확정한 경과, 모델별 생성 설정 차이, 워밍업 파일 증빙 부재는 관련 문서의 한계 설명에 포함한다
- 모의 테스트와 합성 예제는 구현 동작을 확인하는 수단이다. 실제 모델 품질이나 새로운 실험 성과로 계산하지 않는다
