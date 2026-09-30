"""Install only selected COCI testdata from checksum-pinned official archives.

Never executes a candidate or contacts a model. Archives are validated and
selected files staged before destinations are reserved with exclusive mkdir.
The final copy uses exclusive creation too; existing testdata is never replaced.
"""

import hashlib
import json
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


MANIFEST_PATH = "data/coci/testdata-manifest.json"
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 5000
MAX_COMPRESSION_RATIO = 2000
CHUNK_BYTES = 1024 * 1024


class OfficialRedirectsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        if not new_url.startswith("https://hsin.hr/coci/"):
            raise ValueError(f"공식 HTTPS 경로 밖으로 이동하는 다운로드 거부: {new_url}")
        return super().redirect_request(request, response, code, message, headers, new_url)


def _load_plan(root):
    manifest = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    problems = json.loads((root / "data/coci/problems.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("season") != "2025_2026":
        raise ValueError("지원하지 않는 테스트 데이터 manifest입니다.")
    archives = manifest["archives"]
    expected = {}
    for archive in archives:
        contest = archive["contest"]
        filename = f"contest{contest}_testdata.zip"
        if (contest not in (4, 5, 6) or archive["filename"] != filename
                or archive["url"] != f"https://hsin.hr/coci/{filename}"
                or not re.fullmatch(r"[a-f0-9]{64}", archive["sha256"])
                or not 0 < archive["size_bytes"] <= MAX_ARCHIVE_BYTES):
            raise ValueError("공식 archive manifest의 경로·크기·해시가 잘못됐습니다.")
        for name, counts in archive["selected_problems"].items():
            if (not re.fullmatch(r"[a-z]+", name) or name in expected
                    or counts["cases"] < 1 or counts["samples"] < 0
                    or name not in archive["problem_roots"]):
                raise ValueError("manifest의 문제 매핑이 잘못됐습니다.")
            expected[name] = {
                "id": f"coci_2025_2026_c{contest}_{name}",
                "name": name, "season": "2025_2026", "contest": contest,
                "problem_dir": f"data/coci/2025_2026/contest{contest}/testdata/{name}",
            }
    if (sorted(archive["contest"] for archive in archives) != [4, 5, 6]
            or len(expected) != 10 or len(problems) != 10
            or {p["name"] for p in problems} != set(expected)):
        raise ValueError("공식 고정 자료와 problems.json의 10문항 구성이 다릅니다.")
    for problem in problems:
        if any(problem.get(key) != value for key, value in expected[problem["name"]].items()):
            raise ValueError(f"공식 고정 자료와 문제 경로가 다릅니다: {problem['name']}")
    return archives, expected


def _check_destination(root, destination):
    for path in (destination, *destination.parents):
        if path == root:
            break
        if path.is_symlink():
            raise ValueError(f"심볼릭 링크 경로에는 설치하지 않습니다: {path}")
    if destination.exists():
        raise ValueError(f"테스트 데이터 경로가 이미 있습니다. 덮어쓰지 않습니다: {destination}")


def _download(archive, destination):
    print(f"다운로드: {archive['url']}", flush=True)
    opener = urllib.request.build_opener(OfficialRedirectsOnly())
    request = urllib.request.Request(archive["url"], headers={"User-Agent": "llm-eval-data-setup/1"})
    with opener.open(request, timeout=60) as response, destination.open("xb") as output:
        total = 0
        while block := response.read(CHUNK_BYTES):
            total += len(block)
            if total > archive["size_bytes"] or total > MAX_ARCHIVE_BYTES:
                raise ValueError(f"예상 크기를 초과한 다운로드: {archive['filename']}")
            output.write(block)


def _verify_archive(path, archive):
    if not path.is_file() or path.stat().st_size != archive["size_bytes"]:
        raise ValueError(f"공식 ZIP 크기 불일치 또는 파일 없음: {path}")
    with path.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != archive["sha256"]:
        raise ValueError(
            f"SHA-256 불일치: {path.name}. 공식 현재 시즌 URL의 내용이 바뀌었을 수 있습니다. "
            "해시 검사를 우회하지 말고 2025_2026 원본을 확인하세요."
        )


def _inspect_members(zipped, archive):
    members = zipped.infolist()
    if not members or len(members) > MAX_MEMBERS:
        raise ValueError("ZIP 항목 수 제한을 초과했거나 비어 있습니다.")
    total = 0
    seen = set()
    roots = set()
    selected = {name: [] for name in archive["selected_problems"]}
    for member in members:
        raw = member.orig_filename
        path = PurePosixPath(raw)
        parts = raw.rstrip("/").split("/")
        if (not raw or "\\" in raw or path.is_absolute()
                or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in (".", "..") for part in parts)
                or len(parts) != (1 if member.is_dir() else 2)):
            raise ValueError(f"안전하지 않은 ZIP 경로: {raw!r}")
        normalized = "/".join(parts).casefold()
        if normalized in seen:
            raise ValueError(f"중복 ZIP 경로: {raw}")
        seen.add(normalized)
        roots.add(parts[0])
        kind = stat.S_IFMT(member.external_attr >> 16)
        allowed_kind = stat.S_IFDIR if member.is_dir() else stat.S_IFREG
        if kind not in (0, allowed_kind) or member.flag_bits & 1:
            raise ValueError(f"링크·특수 파일·암호화 ZIP 항목 거부: {raw}")
        if member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError(f"지원하지 않는 ZIP 압축: {raw}")
        total += member.file_size
        if (member.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES
                or member.file_size / max(1, member.compress_size) > MAX_COMPRESSION_RATIO):
            raise ValueError(f"ZIP 크기·압축률 제한 초과: {raw}")
        if not member.is_dir() and parts[0] in selected:
            selected[parts[0]].append(member)
    if roots != set(archive["problem_roots"]):
        raise ValueError("고정한 2025_2026 대회의 문제 폴더 구성과 ZIP이 다릅니다.")
    for name, files in selected.items():
        pairs = {"cases": {"in": set(), "out": set()}, "samples": {"in": set(), "out": set()}}
        for member in files:
            match = re.fullmatch(rf"{name}(\.dummy)?\.(in|out)\.([A-Za-z0-9_-]+)", PurePosixPath(member.filename).name)
            if match is None:
                raise ValueError(f"예상하지 않은 테스트 파일: {member.filename}")
            sample, direction, suffix = match.groups()
            pairs["samples" if sample else "cases"][direction].add(suffix)
        for kind, directions in pairs.items():
            if (directions["in"] != directions["out"]
                    or len(directions["in"]) != archive["selected_problems"][name][kind]):
                raise ValueError(f"테스트 입출력 쌍 또는 개수 불일치: {name} ({kind})")
    return selected


def _stage_archive(path, archive, staging):
    # Never use extract()/extractall(): only validated selected files are written.
    try:
        with zipfile.ZipFile(path) as zipped:
            for name, members in _inspect_members(zipped, archive).items():
                destination = staging / name
                destination.mkdir()
                for member in members:
                    target = destination / PurePosixPath(member.filename).name
                    with zipped.open(member) as source, target.open("xb") as output:
                        total = 0
                        while block := source.read(CHUNK_BYTES):
                            total += len(block)
                            if total > member.file_size or total > MAX_MEMBER_BYTES:
                                raise ValueError(f"ZIP 실제 크기 초과: {member.filename}")
                            output.write(block)
                    if total != member.file_size:
                        raise ValueError(f"ZIP 실제 크기 불일치: {member.filename}")
    except (zipfile.BadZipFile, NotImplementedError) as exc:
        raise ValueError(f"ZIP 검증 실패: {path.name}: {exc}") from exc


def _install(root, plan, staging):
    created_dirs = []
    created_files = []
    try:
        # Reserve every new directory before publishing any file. No rename may
        # replace even an empty existing directory; files use exclusive creation.
        for problem in plan.values():
            destination = root / problem["problem_dir"]
            _check_destination(root, destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _check_destination(root, destination)
            destination.mkdir(exist_ok=False)
            created_dirs.append(destination)
        for name, problem in plan.items():
            destination = root / problem["problem_dir"]
            for source in sorted((staging / name).iterdir()):
                target = destination / source.name
                with target.open("xb") as output:
                    created_files.append(target)
                    with source.open("rb") as input_file:
                        shutil.copyfileobj(input_file, output, CHUNK_BYTES)
    except BaseException:
        # Only remove paths created by this attempt, never pre-existing data.
        for path in reversed(created_files):
            path.unlink()
        for path in reversed(created_dirs):
            path.rmdir()
        raise


def setup_dataset(root: Path, archives_dir: Path | None = None):
    root = Path(root).resolve()
    archives, plan = _load_plan(root)
    for problem in plan.values():
        _check_destination(root, root / problem["problem_dir"])
    with tempfile.TemporaryDirectory(prefix="llm-eval-coci-") as temporary:
        staging = Path(temporary) / "selected"
        staging.mkdir()
        for archive in archives:
            if archives_dir is None:
                path = Path(temporary) / archive["filename"]
                _download(archive, path)
            else:
                path = Path(archives_dir) / archive["filename"]
            _verify_archive(path, archive)
            _stage_archive(path, archive, staging)
        _install(root, plan, staging)
    for archive in archives:
        for name, counts in archive["selected_problems"].items():
            print(f"설치: {name}: tests={counts['cases']}, samples={counts['samples']}")
    print("공식 2025_2026 테스트 데이터 10문항 설치 완료. uv run llm-eval validate로 확인하세요.")
    return [root / problem["problem_dir"] for problem in plan.values()]
