"""Offline walkthrough using trusted, synthetic fixtures, never model output.

This is separate from the benchmark and its evaluation schema. Only the fixed
programs below may execute; no API client, model, or external dataset is used.
"""

import shlex
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from llm_eval.judging.engine import judge_problem
from llm_eval.judging.reporting import valid_answer
from llm_eval.shared.code_extraction import extract_python_code
from llm_eval.shared.storage import write_json, write_text


NOTICE = "고정 합성 fixture 데모입니다. 실제 모델 호출·성능 평가 결과가 아닙니다."
TIME_LIMIT_SECONDS = 2.0
CASES = (("2 3\n", "5\n"), ("-4 1\n", "-3\n"), ("0 0\n", "0\n"))
FIXTURES = (
    ("correct", "a, b = map(int, input().split())\nprint(a + b)", "AC"),
    ("wrong", "a, b = map(int, input().split())\nprint(a - b)", "WA"),
    ("no_code", None, "NO_CODE"),
)


def reserve_output(root: Path, output: Path | None) -> Path:
    root = root.resolve()
    if output is None:
        run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%fZ") + "_" + uuid4().hex[:8]
        output = root / "results/demo/offline" / run_id
    output = output.resolve()
    # Never allow even new demo files to enter a real data, source, or result tree.
    if output.is_relative_to(root) and not output.is_relative_to(root / "results/demo"):
        raise ValueError("저장소 안의 출력은 results/demo 아래에만 만들 수 있습니다.")
    if output.exists():
        raise ValueError(f"출력 경로가 이미 있습니다. 새 --output 경로를 지정하세요: {output}")
    output.mkdir(parents=True, exist_ok=False)
    return output


def render_report(report: dict) -> str:
    lines = [
        "# 오프라인 합성 데모", "", NOTICE, "",
        "두 정수의 합 문제와 고정 응답으로 코드 추출 → 저장 → 실제 로컬 채점 → 요약을 확인합니다.",
        "모델/API/GPU 호출: 0회. 테스트 입력과 후보 코드는 이 데모에 포함된 고정 예제입니다.",
        "Judge는 보안 샌드박스가 아니며 메모리 제한은 강제하지 않습니다.", "",
        "| 예제 | 호출 상태 | 기대 판정 | 실제 판정 | 통과 테스트 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["entries"]:
        count = "—" if row["total_cases"] is None else f"{row['passed_cases']}/{row['total_cases']}"
        lines.append(f"| {row['fixture']} | not_called | {row['expected_status']} | {row['status']} | {count} |")
    counts = report["verdict_counts"]
    lines += [
        "", f"요약: AC {counts.get('AC', 0)} / WA {counts.get('WA', 0)} / NO_CODE {counts.get('NO_CODE', 0)}",
        f"예상한 데모 판정과 일치: {report['expected_outcomes_matched']}", "",
        "각 예제의 response.json, result.json, judge.json과 추출된 candidate.py를 확인할 수 있습니다.",
        "no_code에는 candidate.py가 없습니다. 이 결과는 benchmark·모델 선정 집계에 포함하지 않습니다.", "",
    ]
    return "\n".join(lines)


def run_offline_demo(root: Path, output: Path | None = None) -> Path:
    output = reserve_output(Path(root), output)
    print(NOTICE)
    data = output / "synthetic-data"
    data.mkdir()
    for number, (input_text, expected) in enumerate(CASES, 1):
        write_text(data / f"sum.in.{number}", input_text)
        write_text(data / f"sum.out.{number}", expected)

    entries = []
    for name, trusted_code, expected_status in FIXTURES:
        folder = output / name
        folder.mkdir()
        content = (
            f"합성 응답: 두 정수를 처리하는 예제입니다.\n```python\n{trusted_code}\n```"
            if trusted_code is not None else "합성 응답: 코드 블록이 없는 경우입니다."
        )
        write_json(folder / "response.json", {"synthetic": True, "content": content})
        code = extract_python_code(content)
        # A broken extractor must not turn this into an arbitrary-code runner.
        if code != trusted_code:
            raise RuntimeError("합성 fixture와 추출 코드가 다릅니다. 실행하지 않았습니다.")
        record = {
            "synthetic": True,
            "experiment": {"type": "offline_demo", "is_model_benchmark": False},
            "fixture": name,
            "call": {"status": "not_called", "reason": "fixed_synthetic_fixture"},
            "generation": {"content": content},
            "extracted_code": code,
        }
        write_json(folder / "result.json", record)
        if code is None:
            judgment = {"status": "NO_CODE", "passed_cases": 0, "total_cases": None}
        else:
            candidate = folder / "candidate.py"
            write_text(candidate, code)
            judgment = judge_problem(candidate, data, "sum", TIME_LIMIT_SECONDS)
        write_json(folder / "judge.json", {"synthetic": True, **judgment})
        entries.append({
            "fixture": name,
            "expected_status": expected_status,
            "status": judgment["status"],
            "passed_cases": judgment["passed_cases"],
            "total_cases": judgment["total_cases"],
            "valid_answer": valid_answer(judgment, TIME_LIMIT_SECONDS),
        })

    report = {
        "schema_version": 1,
        "synthetic": True,
        "is_model_benchmark": False,
        "notice": NOTICE,
        "model_calls": 0,
        "entries": entries,
        "verdict_counts": dict(Counter(row["status"] for row in entries)),
        "expected_outcomes_matched": all(row["status"] == row["expected_status"] for row in entries),
    }
    write_json(output / "report.json", report)
    write_text(output / "report.md", render_report(report))
    print("요약: " + " / ".join(f"{key} {value}" for key, value in report["verdict_counts"].items()))
    print(f"결과: {output}")
    print(f"결과 확인: cat {shlex.quote(str(output / 'report.md'))}")
    if not report["expected_outcomes_matched"]:
        raise RuntimeError("예상한 합성 데모 판정과 다릅니다. 저장된 judge.json을 확인하세요.")
    return output
