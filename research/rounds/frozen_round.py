"""A scored round's frozen registration, written once before any paid call and verified before every run
and every scoring.

The round's question file, sampler, library commit, Python version and case ids are registered in code
(`registered_rounds.py`). `manifest.json` in the round folder, whose hash `FROZEN.txt` binds, records: the
registered case ids; the sha256 of every source file in
this repository at a clean commit; the exact question file and its hash; the cases file hash; the
jev-navigator commit and the Python version the run must use; the gitleaks receipt with its version,
command and input hash (no findings allowed); the prior-label manifest hash; the frozen copy of the rule
(`compose.py` copied to `<round>/compose_frozen.py`) that the scorer uses instead of the live one; and the
verifier report the freeze answers. `verify` fails closed on any difference, and also rebuilds every case
record in full with the round's sampler.
usage: uv run python frozen_round.py freeze <round name> <verifier report>
       uv run python frozen_round.py verify <round name>
"""

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from comment_tool.config import DATA
from comment_tool.questions import path as questions_path
from research.rounds.registered_rounds import ROUNDS, Registration

REPOSITORY = Path(__file__).resolve().parents[2]  # the repository root, two levels above experiments/rounds/
SOURCE_SUFFIXES = (".py", ".mjs", ".json", ".toml")
FROZEN_RULE = "compose_frozen.py"
GITLEAKS_RECEIPT = "secret-scan.gitleaks.json"
PRIOR_LABELS = "prior-labels.json"


MANIFEST_LINE = "manifest.json sha256: "
"""The line in `FROZEN.txt` that binds the manifest; `freeze` writes it."""


class FrozenRoundError(RuntimeError):
    """The round's files, code or runtime differ from its registration."""


class RunNotCompleteError(FrozenRoundError):
    """The run's result file is missing, or a newer run is still writing its partial file."""


@dataclass(frozen=True)
class Manifest:
    round_dir: Path
    fields: dict
    registration: Registration

    @property
    def case_ids(self) -> list[str]:
        return list(self.registration.case_ids)

    @property
    def questions_path(self) -> Path:
        return questions_path(Path(self.registration.questions).name)

    def questions(self) -> dict:
        return json.loads(self.questions_path.read_text())


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def completed_rows(round_dir: Path, name: str, case_ids: list[str]) -> dict[str, dict]:
    """`rows_exactly` for a finished run only: refused while `<name>.partial` exists or when `<name>` is missing."""
    if (round_dir / f"{name}.partial").exists() or not (round_dir / name).exists():
        raise RunNotCompleteError(f"{round_dir.name}/{name}: the run is not complete")
    return rows_exactly(round_dir / name, case_ids)


def rows_exactly(path: Path, case_ids: list[str]) -> dict[str, dict]:
    """The rows of a JSONL file by case id, only when they are exactly the registered ids: no duplicate,
    missing or extra id. A partial file is invalid, never a smaller round."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    found = [row["case_id"] for row in rows]
    duplicates = sorted({cid for cid in found if found.count(cid) > 1})
    missing, extra = sorted(set(case_ids) - set(found)), sorted(set(found) - set(case_ids))
    if duplicates or missing or extra:
        raise FrozenRoundError(f"{path.name}: duplicates {duplicates}, missing {missing}, extra {extra}")
    return {row["case_id"]: row for row in rows}


def source_hashes() -> dict[str, str]:
    """Every source file tracked in this repository, by path."""
    tracked = subprocess.run(["git", "ls-files"], cwd=REPOSITORY, capture_output=True, text=True, check=True).stdout.split()
    return {path: sha256_of(REPOSITORY / path) for path in sorted(tracked) if path.endswith(SOURCE_SUFFIXES)}


def library_commit() -> str:
    direct = json.loads(importlib.metadata.distribution("jev-navigator").read_text("direct_url.json"))
    return direct["vcs_info"]["commit_id"]


def python_version() -> str:
    return ".".join(platform.python_version_tuple()[:2])


def freeze(round_dir: Path, verifier_report: Path) -> Manifest:
    _require_clean_repository()
    registration = ROUNDS[round_dir.name]
    cases = round_dir / "cases.jsonl"
    shutil.copyfile(REPOSITORY / "compose.py", round_dir / FROZEN_RULE)
    fields = {
        "case_ids": list(registration.case_ids),
        "repository_commit": _git("rev-parse", "HEAD"),
        "sources": source_hashes(),
        "questions": {"path": registration.questions, "sha256": sha256_of(questions_path(Path(registration.questions).name))},
        "cases_sha256": sha256_of(cases),
        "sampler": registration.sampler,
        "library_commit": library_commit(),
        "python": python_version(),
        "gitleaks": _secret_scan(round_dir, cases),
        "prior_labels_sha256": sha256_of(round_dir / PRIOR_LABELS),
        "frozen_rule_sha256": sha256_of(round_dir / FROZEN_RULE),
        "verifier_report": {"path": str(verifier_report), "sha256": sha256_of(verifier_report)},
    }
    (round_dir / "manifest.json").write_text(json.dumps(fields, indent=1) + "\n")
    _bind_manifest(round_dir)
    return verify(round_dir)


def registered_manifest(round_dir: Path, registration: Registration) -> Manifest:
    """The manifest, only when its hash is the one `FROZEN.txt` binds and it agrees with the code registration."""
    bound = [line.removeprefix(MANIFEST_LINE) for line in (round_dir / "FROZEN.txt").read_text().splitlines()
             if line.startswith(MANIFEST_LINE)]
    _same("manifest (bound in FROZEN.txt)", [sha256_of(round_dir / "manifest.json")], bound)
    fields = json.loads((round_dir / "manifest.json").read_text())
    _same("case ids", fields["case_ids"], list(registration.case_ids))
    _same("question file", fields["questions"]["path"], registration.questions)
    _same("sampler", fields["sampler"], registration.sampler)
    _same("registered library commit", fields["library_commit"], registration.library_commit)
    _same("registered python", fields["python"], registration.python)
    return Manifest(round_dir, fields, registration)


def verify(round_dir: Path) -> Manifest:
    """The round's manifest, after every registered fact was checked again; raises on any difference."""
    manifest = registered_manifest(round_dir, ROUNDS[round_dir.name])
    fields = manifest.fields
    _same("repository commit (run and score from a checkout at the registered commit)", _git("rev-parse", "HEAD"),
          fields["repository_commit"])
    _same("sources (run and score from a checkout at the registered repository commit)", source_hashes(), fields["sources"])
    _same("questions", sha256_of(manifest.questions_path), fields["questions"]["sha256"])
    _same("cases", sha256_of(round_dir / "cases.jsonl"), fields["cases_sha256"])
    _same("library commit", library_commit(), fields["library_commit"])
    _same("python", python_version(), fields["python"])
    _same("gitleaks receipt", sha256_of(round_dir / GITLEAKS_RECEIPT), fields["gitleaks"]["receipt_sha256"])
    _same("gitleaks input", fields["gitleaks"]["input_sha256"], fields["cases_sha256"])
    _same("prior labels", sha256_of(round_dir / PRIOR_LABELS), fields["prior_labels_sha256"])
    _same("frozen rule", sha256_of(round_dir / FROZEN_RULE), fields["frozen_rule_sha256"])
    _same("verifier report", sha256_of(Path(fields["verifier_report"]["path"])), fields["verifier_report"]["sha256"])
    _same_case_records(round_dir, manifest)
    return manifest


def frozen_rule(manifest: Manifest):
    """The rule as frozen with the round, loaded from its hashed copy, never the live `compose.py`."""
    path = manifest.round_dir / FROZEN_RULE
    _same("frozen rule", sha256_of(path), manifest.fields["frozen_rule_sha256"])
    spec = importlib.util.spec_from_file_location(f"{manifest.round_dir.name}_compose_frozen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _same_case_records(round_dir: Path, manifest: Manifest) -> None:
    sampler = importlib.import_module(f"research.rounds.{manifest.registration.sampler}")
    cases = rows_exactly(round_dir / "cases.jsonl", manifest.case_ids)
    differing = [cid for cid, raw in cases.items() if sampler.rebuilt_case(raw) != raw]
    if differing:
        raise FrozenRoundError(f"case records differ when rebuilt: {differing}")


def _same(what: str, found, registered) -> None:
    if found != registered:
        raise FrozenRoundError(f"{what} differs from the registration")


def _bind_manifest(round_dir: Path) -> None:
    frozen = round_dir / "FROZEN.txt"
    kept = [line for line in frozen.read_text().splitlines() if not line.startswith(MANIFEST_LINE)] if frozen.exists() else []
    frozen.write_text("\n".join([*kept, MANIFEST_LINE + sha256_of(round_dir / "manifest.json")]) + "\n")


def _secret_scan(round_dir: Path, cases: Path) -> dict:
    receipt = round_dir / GITLEAKS_RECEIPT
    command = ["gitleaks", "detect", "--no-git", "--source", str(cases), "--report-path", str(receipt), "--report-format", "json"]
    subprocess.run(command, capture_output=True, check=True)
    if json.loads(receipt.read_text()):
        raise FrozenRoundError(f"gitleaks found secrets in {cases}")
    version = subprocess.run(["gitleaks", "version"], capture_output=True, text=True, check=True).stdout.strip()
    return {"version": version, "command": " ".join(command), "input_sha256": sha256_of(cases), "receipt_sha256": sha256_of(receipt)}


def _require_clean_repository() -> None:
    if _git("status", "--porcelain"):
        raise FrozenRoundError("commit the code before freezing: the repository has uncommitted changes")


def _git(*arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=REPOSITORY, capture_output=True, text=True, check=True).stdout.strip()


def main() -> None:
    action, round_dir = sys.argv[1], DATA / sys.argv[2]
    manifest = freeze(round_dir, Path(sys.argv[3])) if action == "freeze" else verify(round_dir)
    print(f"{round_dir.name}: {len(manifest.case_ids)} cases verified against the registration "
          f"(library {manifest.fields['library_commit'][:8]}, Python {manifest.fields['python']})")


if __name__ == "__main__":
    main()
