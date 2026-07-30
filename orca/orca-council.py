#!/usr/bin/env python3
"""Artifact ledger for Orca Plan Councils and blind Races.

Orca orchestration is the sole owner of task/dispatch/worker lifecycle. This
ledger never calls Orca or copies its mutable status. It seals inputs and
outputs, records opaque Orca references, audits multi-backbone provenance and
research overlap, recomputes judge scores, and records the user's decision.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse


SCHEMA_VERSION = 3
WEIGHTS = {"D1": 3, "D2": 3, "D3": 2, "D4": 1, "D5": 1}
LABELS = ("X", "Y", "Z")
BACKBONES = ("fable", "gpt-sol")
MAX_INPUT_BYTES = 1_000_000
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,80}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
TASK_RE = re.compile(r"^task_[A-Za-z0-9]+$")
DISPATCH_RE = re.compile(r"^ctx_[A-Za-z0-9]+$")
TERMINAL_RE = re.compile(r"^term_[A-Za-z0-9-]+$")


class CouncilError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (value or "council")[:40]


def default_state_root() -> Path:
    configured = os.environ.get("ORCA_COUNCIL_STATE")
    if configured:
        return Path(configured).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    return Path(xdg).expanduser() / "orca-council" if xdg else Path.home() / ".local/state/orca-council"


def state_root(args: argparse.Namespace) -> Path:
    return Path(args.state_root).expanduser() if args.state_root else default_state_root()


def run_dir(args: argparse.Namespace, run_id: str | None = None) -> Path:
    chosen = run_id or getattr(args, "run", None)
    if not chosen or not RUN_ID_RE.fullmatch(chosen):
        raise CouncilError(f"invalid run id: {chosen!r}")
    return state_root(args) / chosen


def read_limited(path: Path) -> bytes:
    if not path.is_file():
        raise CouncilError(f"file not found: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise CouncilError(f"file is empty: {path}")
    if size > MAX_INPUT_BYTES:
        raise CouncilError(f"file exceeds {MAX_INPUT_BYTES} bytes: {path}")
    return path.read_bytes()


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{secrets.token_hex(3)}")
    try:
        with tmp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def file_record(relative_path: str, data: bytes) -> dict[str, Any]:
    return {"path": relative_path, "sha256": sha256(data), "bytes": len(data)}


def event(manifest: dict[str, Any], kind: str, **details: Any) -> None:
    manifest.setdefault("events", []).append({"at": utc_now(), "kind": kind, **details})


@contextlib.contextmanager
def locked(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / ".lock").open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def load_manifest(directory: Path) -> dict[str, Any]:
    path = directory / "manifest.json"
    if not path.is_file():
        raise CouncilError(f"run does not exist: {directory.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CouncilError(f"invalid manifest for {directory.name}: {exc}") from exc
    if value.get("schema_version") != SCHEMA_VERSION:
        raise CouncilError(f"unsupported schema version: {value.get('schema_version')}")
    return value


def save_manifest(directory: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now()
    write_json(directory / "manifest.json", manifest)


def verify_record(directory: Path, record: dict[str, Any], label: str) -> None:
    data = read_limited(directory / record["path"])
    if len(data) != record["bytes"] or sha256(data) != record["sha256"]:
        raise CouncilError(f"{label} integrity check failed")


def parse_json_file(path: str, label: str) -> Any:
    try:
        return json.loads(read_limited(Path(path).expanduser()))
    except json.JSONDecodeError as exc:
        raise CouncilError(f"{label} is not valid JSON: {exc}") from exc


def parse_deps(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise CouncilError(f"deps must be a JSON array: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) or not TASK_RE.fullmatch(item) for item in value):
        raise CouncilError("deps must be a JSON array of Orca task IDs")
    if len(value) != len(set(value)):
        raise CouncilError("deps must not contain duplicates")
    return sorted(value)


def model_backbone(model_id: str) -> str:
    if model_id == "gpt-5.6-sol":
        return "gpt-sol"
    if "fable" in model_id.casefold():
        return "fable"
    return "other"


def reference_record(args: argparse.Namespace) -> dict[str, Any]:
    if not TASK_RE.fullmatch(args.task_id):
        raise CouncilError(f"invalid Orca task id: {args.task_id!r}")
    if not DISPATCH_RE.fullmatch(args.dispatch_id):
        raise CouncilError(f"invalid Orca dispatch id: {args.dispatch_id!r}")
    if not TERMINAL_RE.fullmatch(args.terminal_handle):
        raise CouncilError(f"invalid Orca terminal handle: {args.terminal_handle!r}")
    model_id = str(args.model_id or "").strip()
    session_id = str(args.session_id or "").strip()
    parent_task_id = str(args.parent_task_id or "").strip() or None
    if not model_id or not session_id:
        raise CouncilError("model-id and session-id are required")
    if parent_task_id is not None and not TASK_RE.fullmatch(parent_task_id):
        raise CouncilError(f"invalid parent task id: {parent_task_id!r}")
    deps = parse_deps(args.deps_json)
    attestation = parse_json_file(args.attestation, "dispatch attestation")
    expected = {
        "task_id": args.task_id,
        "dispatch_id": args.dispatch_id,
        "terminal_handle": args.terminal_handle,
        "model_id": model_id,
        "session_id": session_id,
        "parent_task_id": parent_task_id,
        "deps": deps,
    }
    if not isinstance(attestation, dict) or any(attestation.get(key) != value for key, value in expected.items()):
        raise CouncilError("dispatch attestation does not exactly match task/dispatch/model/session/topology arguments")
    attestation_data = read_limited(Path(args.attestation).expanduser())
    return {
        **expected,
        "attestation": {
            "sha256": sha256(attestation_data),
            "bytes": len(attestation_data),
        },
        "_attestation_data": attestation_data,
        "recorded_at": utc_now(),
        "authority": "orca-orchestration",
        "verification_level": "controller-attested",
        "status_copied": False,
    }


def all_references(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    root = manifest["orca_refs"].get("root")
    if root:
        refs.append(root)
    for slot in manifest["candidates"].values():
        if slot.get("orca_ref"):
            refs.append(slot["orca_ref"])
        for contributor in slot.get("contributors", {}).values():
            if contributor:
                refs.append(contributor["orca_ref"])
    for key in ("refuter", "synthesis"):
        if manifest["orca_refs"].get(key):
            refs.append(manifest["orca_refs"][key])
    refs.extend(manifest["orca_refs"].get("judges", {}).values())
    return refs


def ensure_unique_reference(manifest: dict[str, Any], record: dict[str, Any]) -> None:
    for existing in all_references(manifest):
        for key in ("task_id", "dispatch_id", "terminal_handle", "session_id"):
            if existing[key] == record[key]:
                raise CouncilError(f"Orca provenance {key} must be unique: {record[key]}")


def seal_reference_attestation(directory: Path, role: str, record: dict[str, Any]) -> None:
    data = record.pop("_attestation_data")
    relative = f"sealed/provenance/{slugify(role)}-{record['task_id']}.json"
    atomic_write(directory / relative, data)
    record["attestation"] = file_record(relative, data)


def candidate_names(mode: str, profile: str, count: int) -> list[str]:
    if mode == "plan" and profile == "dual-backbone-v3":
        if count != 3:
            raise CouncilError("dual-backbone-v3 requires exactly 3 lanes")
        return ["lane-A", "lane-B", "lane-C"]
    return [f"candidate-{index}" for index in range(1, count + 1)]


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode == "race":
        profile = "race"
        if not args.base_sha or not SHA_RE.fullmatch(args.base_sha.lower()):
            raise CouncilError("race mode requires --base-sha")
    else:
        profile = args.profile
    if args.candidates not in (2, 3):
        raise CouncilError("candidate count must be 2 or 3")

    brief = read_limited(Path(args.brief).expanduser())
    rubric = read_limited(Path(args.rubric).expanduser())
    generated = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{slugify(args.slug)}-{secrets.token_hex(2)}"
    run_id = args.run_id or generated
    if not RUN_ID_RE.fullmatch(run_id):
        raise CouncilError(f"invalid run id: {run_id!r}")
    directory = state_root(args) / run_id
    if directory.exists():
        raise CouncilError(f"run already exists: {run_id}")
    directory.mkdir(parents=True, mode=0o700)

    names = candidate_names(args.mode, profile, args.candidates)
    anonymous = list(LABELS[: len(names)])
    secrets.SystemRandom().shuffle(anonymous)
    slots: dict[str, Any] = {}
    for name, label in zip(names, anonymous):
        slots[name] = {
            "anonymous_id": label,
            "status": "pending",
            "submission": None,
            "child_agents": [],
            "contributors": {backbone: None for backbone in BACKBONES}
            if profile == "dual-backbone-v3"
            else {},
            "diversity_audit": None,
            "orca_ref": None,
            "claims_ingested": False,
            "race_proof": None,
        }

    atomic_write(directory / "sealed/brief.md", brief)
    atomic_write(directory / "sealed/rubric.md", rubric)
    created = utc_now()
    min_judges = 2 if profile in {"dual-backbone-v3", "race"} else 1
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "mode": args.mode,
        "profile": profile,
        "state": "FRAMED",
        "created_at": created,
        "updated_at": created,
        "base_sha": args.base_sha.lower() if args.base_sha else None,
        "inputs": {
            "brief": file_record("sealed/brief.md", brief),
            "rubric": file_record("sealed/rubric.md", rubric),
        },
        "policy": {
            "candidate_count": len(names),
            "minimum_judges": min_judges,
            "max_children_per_candidate": 2 if profile == "lightweight" else 0,
            "advocate_is_not_judge": True,
            "user_is_final_judge": True,
            "orca_is_lifecycle_authority": True,
            "artifact_ledger_copies_orca_status": False,
        },
        "candidates": slots,
        "claims": {},
        "spec_seed": None,
        "judge_bundle": None,
        "orca_refs": {"root": None, "refuter": None, "judges": {}, "synthesis": None},
        "judgment": None,
        "decision": None,
        "events": [],
    }
    event(manifest, "run_initialized", mode=args.mode, profile=profile)
    save_manifest(directory, manifest)
    return {
        "ok": True,
        "run_id": run_id,
        "state": "FRAMED",
        "profile": profile,
        "path": str(directory),
        "candidate_slots": names,
        "brief_sha256": manifest["inputs"]["brief"]["sha256"],
        "rubric_sha256": manifest["inputs"]["rubric"]["sha256"],
    }


def cmd_bind(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    record = reference_record(args)
    with locked(directory):
        manifest = load_manifest(directory)
        ensure_unique_reference(manifest, record)
        root = manifest["orca_refs"]["root"]
        if args.role == "root":
            if record["parent_task_id"] is not None or record["deps"]:
                raise CouncilError("root requires parent=null and deps=[]")
        else:
            if root is None:
                raise CouncilError("bind root before child roles")
            if record["parent_task_id"] != root["task_id"]:
                raise CouncilError("child parent-task-id must match the bound root task")
        if args.role in manifest["candidates"]:
            slot = manifest["candidates"][args.role]
            if slot["orca_ref"] is not None:
                raise CouncilError(f"{args.role} already has an Orca reference")
            if manifest["profile"] == "dual-backbone-v3":
                if not all(
                    all(value is not None for value in candidate["contributors"].values())
                    for candidate in manifest["candidates"].values()
                ):
                    raise CouncilError("lane synthesis cannot bind before the six-worker global barrier")
                expected = sorted(
                    contributor["orca_ref"]["task_id"]
                    for candidate in manifest["candidates"].values()
                    for contributor in candidate["contributors"].values()
                )
                if record["deps"] != expected:
                    raise CouncilError("each lane synthesis deps must be exactly all six contributor task IDs")
            elif manifest["profile"] == "race" and record["deps"]:
                raise CouncilError("race candidates must start independently with deps=[]")
            slot["orca_ref"] = record
        elif args.role.startswith("judge-"):
            if args.role in manifest["orca_refs"]["judges"]:
                raise CouncilError(f"{args.role} already has an Orca reference")
            if len(manifest["orca_refs"]["judges"]) >= manifest["policy"]["minimum_judges"]:
                raise CouncilError("judge reference count is already complete")
            backbone = model_backbone(record["model_id"])
            if backbone not in BACKBONES:
                raise CouncilError("judge model must identify Fable or exact gpt-5.6-sol")
            if any(model_backbone(item["model_id"]) == backbone for item in manifest["orca_refs"]["judges"].values()):
                raise CouncilError("judge backbones must be one Fable and one gpt-5.6-sol")
            if manifest["judge_bundle"] is None:
                raise CouncilError("seal the judge bundle before binding judges")
            if manifest["profile"] == "dual-backbone-v3":
                refuter = manifest["orca_refs"]["refuter"]
                if refuter is None or record["deps"] != [refuter["task_id"]]:
                    raise CouncilError("plan judges must depend exactly on the refuter task")
            else:
                if any(slot["orca_ref"] is None for slot in manifest["candidates"].values()):
                    raise CouncilError("bind all race candidates before judges")
                expected = sorted(slot["orca_ref"]["task_id"] for slot in manifest["candidates"].values())
                if record["deps"] != expected:
                    raise CouncilError("race judges must depend exactly on all candidate tasks")
            manifest["orca_refs"]["judges"][args.role] = record
        elif args.role == "refuter":
            if manifest["mode"] != "plan" or not all(slot["claims_ingested"] for slot in manifest["candidates"].values()):
                raise CouncilError("refuter requires claims from all three sealed lanes")
            if any(slot["orca_ref"] is None for slot in manifest["candidates"].values()):
                raise CouncilError("bind all lane synthesis tasks before refuter")
            expected = sorted(slot["orca_ref"]["task_id"] for slot in manifest["candidates"].values())
            if record["deps"] != expected:
                raise CouncilError("refuter deps must be exactly all lane synthesis task IDs")
            if manifest["orca_refs"]["refuter"] is not None:
                raise CouncilError("refuter already has an Orca reference")
            manifest["orca_refs"]["refuter"] = record
            manifest["state"] = "HARDENING"
        elif args.role == "synthesis":
            if manifest["mode"] != "plan" or manifest["state"] != "JUDGED":
                raise CouncilError("final synthesis binds only after plan judgment")
            expected = sorted(item["task_id"] for item in manifest["orca_refs"]["judges"].values())
            if len(expected) != manifest["policy"]["minimum_judges"] or record["deps"] != expected:
                raise CouncilError("final synthesis deps must be exactly all judge task IDs")
            if manifest["orca_refs"]["synthesis"] is not None:
                raise CouncilError("synthesis already has an Orca reference")
            manifest["orca_refs"]["synthesis"] = record
        elif args.role == "root":
            if manifest["orca_refs"][args.role] is not None:
                raise CouncilError(f"{args.role} already has an Orca reference")
            manifest["orca_refs"][args.role] = record
        else:
            raise CouncilError(f"unknown role: {args.role}")
        seal_reference_attestation(directory, args.role, record)
        event(manifest, "orca_reference_recorded", role=args.role, task_id=args.task_id, dispatch_id=args.dispatch_id)
        save_manifest(directory, manifest)
    return {"ok": True, "run_id": manifest["run_id"], "role": args.role}


def normalize_research_log(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        raise CouncilError("research log must be a non-empty JSON array")
    normalized = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CouncilError(f"research log[{index}] must be an object")
        query = str(item.get("query") or "").strip()
        url = str(item.get("url") or "").strip()
        evidence_root = str(item.get("evidence_root") or "").strip()
        if not query and not url:
            raise CouncilError(f"research log[{index}] needs query or url")
        if not evidence_root:
            raise CouncilError(f"research log[{index}] needs an explicit evidence_root")
        normalized.append(
            {
                "query": query[:2000],
                "url": url[:4000],
                "tool": str(item.get("tool") or "unknown")[:200],
                "source_class": str(item.get("source_class") or "unknown")[:200],
                "community": str(item.get("community") or "unknown")[:200],
                "language": str(item.get("language") or "unknown")[:80],
                "evidence_root": evidence_root[:4000],
                "polarity": str(item.get("polarity") or "neutral")[:40],
            }
        )
    return normalized


def cmd_contributor_submit(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    artifact = read_limited(Path(args.artifact).expanduser())
    research = normalize_research_log(parse_json_file(args.research_log, "research log"))
    record = reference_record(args)
    backbone = args.backbone
    model_id = args.model_id.strip()
    session_id = args.session_id.strip()
    if backbone == "gpt-sol" and model_id != "gpt-5.6-sol":
        raise CouncilError("gpt-sol contributor requires model-id gpt-5.6-sol")
    if backbone == "fable" and "fable" not in model_id.lower():
        raise CouncilError("fable contributor model-id must identify Fable")
    if not session_id:
        raise CouncilError("session-id is required")

    with locked(directory):
        manifest = load_manifest(directory)
        if manifest["profile"] != "dual-backbone-v3":
            raise CouncilError("contributor-submit requires dual-backbone-v3")
        root = manifest["orca_refs"]["root"]
        if root is None:
            raise CouncilError("bind root before contributor submissions")
        if record["parent_task_id"] != root["task_id"] or record["deps"]:
            raise CouncilError("contributors require the bound root as parent and deps=[]")
        if args.candidate not in manifest["candidates"]:
            raise CouncilError(f"unknown lane: {args.candidate}")
        slot = manifest["candidates"][args.candidate]
        if slot["contributors"][backbone] is not None:
            raise CouncilError(f"{args.candidate}/{backbone} is already sealed")
        ensure_unique_reference(manifest, record)

        base = f"sealed/workers/{args.candidate}/{backbone}"
        atomic_write(directory / f"{base}.md", artifact)
        write_json(directory / f"{base}-research.json", research)
        seal_reference_attestation(directory, f"{args.candidate}-{backbone}", record)
        contributor = {
            "backbone": backbone,
            "model_id": model_id,
            "session_id": session_id[:200],
            "artifact": file_record(f"{base}.md", artifact),
            "research_log": file_record(f"{base}-research.json", (directory / f"{base}-research.json").read_bytes()),
            "orca_ref": record,
            "sealed_at": utc_now(),
        }
        slot["contributors"][backbone] = contributor
        slot["status"] = "workers-partial"
        if all(value is not None for value in slot["contributors"].values()):
            slot["status"] = "workers-sealed"
        if all(
            all(value is not None for value in candidate["contributors"].values())
            for candidate in manifest["candidates"].values()
        ):
            manifest["state"] = "WORKERS_SEALED"
        else:
            manifest["state"] = "DIVERGING"
        event(manifest, "contributor_sealed", lane=args.candidate, backbone=backbone, model_id=model_id)
        save_manifest(directory, manifest)
    return {
        "ok": True,
        "run_id": manifest["run_id"],
        "candidate": args.candidate,
        "backbone": backbone,
        "state": manifest["state"],
        "sha256": contributor["artifact"]["sha256"],
    }


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return 0.0 if not union else len(left & right) / len(union)


_WORD_RE = re.compile(r"[0-9a-z가-힣]+")
_QUERY_STOP = {"the", "a", "an", "of", "for", "in", "on", "to", "and", "or", "vs", "how", "what", "best"}


def norm_query(q: str) -> str:
    """검색어를 정렬된 토큰 집합으로 정규화.

    왜 (2026-07-29 2백본 감사): casefold 완전일치 비교라 어순·불용어·대소문자만 바꾼
    *같은 검색*이 overlap 0으로 독립성 게이트를 통과했다. 표현이 아니라 내용으로 비교한다.
    """
    toks = [t for t in _WORD_RE.findall(q.casefold()) if t not in _QUERY_STOP]
    return " ".join(sorted(set(toks)))


def norm_root(r: str) -> str:
    """evidence root canonicalization — URL이면 host+path(www·쿼리·프래그먼트·trailing slash 제거).

    같은 원증거를 `https://www.x.org/a/?utm=1`·`http://x.org/a`처럼 달리 적으면 서로 다른
    root로 세어지던 구멍을 막는다.
    """
    s = r.strip()
    if "://" in s:
        u = urlparse(s)
        host = u.netloc.casefold()
        host = host[4:] if host.startswith("www.") else host
        return f"{host}{u.path.rstrip('/').casefold()}"
    return norm_query(s)


def log_sets(directory: Path, record: dict[str, Any]) -> dict[str, set[str]]:
    raw = json.loads(read_limited(directory / record["research_log"]["path"]))
    return {
        "queries": {norm_query(item["query"]) for item in raw if item["query"]},
        "urls": {item["url"].split("#", 1)[0] for item in raw if item["url"]},
        "domains": {urlparse(item["url"]).netloc.casefold() for item in raw if item["url"]},
        "evidence_roots": {norm_root(item["evidence_root"]) for item in raw if item["evidence_root"]},
        "tools": {item["tool"].casefold() for item in raw if item["tool"]},
        "classes": {item["source_class"].casefold() for item in raw if item["source_class"]},
        "communities": {item["community"].casefold() for item in raw if item["community"]},
        "languages": {item["language"].casefold() for item in raw if item["language"]},
        "polarities": {item["polarity"].casefold() for item in raw if item["polarity"]},
    }


def cmd_audit_diversity(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    with locked(directory):
        manifest = load_manifest(directory)
        if manifest["profile"] != "dual-backbone-v3":
            raise CouncilError("diversity audit requires dual-backbone-v3")
        if not all(
            all(value is not None for value in candidate["contributors"].values())
            for candidate in manifest["candidates"].values()
        ):
            raise CouncilError("diversity audit opens only after all six research logs are sealed")
        if args.candidate not in manifest["candidates"]:
            raise CouncilError(f"unknown lane: {args.candidate}")
        slot = manifest["candidates"][args.candidate]
        if any(value is None for value in slot["contributors"].values()):
            raise CouncilError("both backbone artifacts must be sealed before diversity audit")
        left = log_sets(directory, slot["contributors"]["fable"])
        right = log_sets(directory, slot["contributors"]["gpt-sol"])
        other_sets = [
            log_sets(directory, contributor)
            for lane, candidate in manifest["candidates"].items()
            if lane != args.candidate
            for contributor in candidate["contributors"].values()
        ]
        cross_lane_max = {
            key: round(max((jaccard(left[key], other[key]) for other in other_sets), default=0.0), 4)
            for key in ("queries", "urls", "evidence_roots")
        }
        cross_right = {
            key: round(max((jaccard(right[key], other[key]) for other in other_sets), default=0.0), 4)
            for key in ("queries", "urls", "evidence_roots")
        }
        overlap = {
            key: round(jaccard(left[key], right[key]), 4)
            for key in ("queries", "urls", "domains", "evidence_roots")
        }
        audit = {
            "lane": args.candidate,
            "overlap": overlap,
            "cross_lane_max": {"fable": cross_lane_max, "gpt-sol": cross_right},
            "portfolios": {
                key: {"fable": sorted(left[key]), "gpt-sol": sorted(right[key])}
                for key in ("tools", "classes", "communities", "languages", "polarities")
            },
            "independence_warning": (
                overlap["queries"] > 0.6
                or overlap["evidence_roots"] > 0.4
                or overlap["urls"] > 0.4
                or any(value > 0.6 for value in cross_lane_max.values())
                or any(value > 0.6 for value in cross_right.values())
            ),
            "audited_at": utc_now(),
        }
        slot["diversity_audit"] = audit
        event(manifest, "diversity_audited", lane=args.candidate, warning=audit["independence_warning"])
        save_manifest(directory, manifest)
    return {"ok": True, "run_id": manifest["run_id"], "audit": audit}


def parse_trace(path: str | None, max_children: int) -> list[dict[str, Any]]:
    if path is None:
        return []
    raw = parse_json_file(path, "trace")
    if not isinstance(raw, list) or len(raw) > max_children:
        raise CouncilError(f"trace must be an array with at most {max_children} items")
    output = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or item.get("depth") != 1 or item.get("read_only") is not True:
            raise CouncilError(f"trace[{index}] requires depth=1 and read_only=true")
        output.append({"role": str(item.get("role") or "")[:80], "finding": str(item.get("finding") or "")[:2000]})
    return output


def normalize_race_proof(raw: Any, manifest: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CouncilError("race attestation must be an object")
    commit_sha = str(raw.get("commit_sha") or "").lower()
    base_sha = str(raw.get("base_sha") or "").lower()
    values = {
        "worktree_id": str(raw.get("worktree_id") or "").strip(),
        "home_id": str(raw.get("home_id") or "").strip(),
        "xdg_id": str(raw.get("xdg_id") or "").strip(),
        "session_id": str(raw.get("session_id") or "").strip(),
    }
    if base_sha != manifest["base_sha"]:
        raise CouncilError("race attestation base_sha must match the sealed base")
    if not SHA_RE.fullmatch(commit_sha) or commit_sha == base_sha:
        raise CouncilError("race attestation requires a distinct valid candidate commit_sha")
    if any(not value for value in values.values()):
        raise CouncilError("race attestation requires worktree_id, home_id, xdg_id, and session_id")
    if values["session_id"] != slot["orca_ref"]["session_id"]:
        raise CouncilError("race attestation session_id must match the bound candidate session")
    if raw.get("child_agent_count") != 0 or raw.get("sibling_access") is not False:
        raise CouncilError("race candidates require child_agent_count=0 and sibling_access=false")
    if raw.get("test_exit_code") != 0 or not str(raw.get("test_command") or "").strip():
        raise CouncilError("race attestation requires a named test command with exit code 0")
    return {
        "base_sha": base_sha,
        "commit_sha": commit_sha,
        **values,
        "child_agent_count": 0,
        "sibling_access": False,
        "test_command": str(raw["test_command"])[:4000],
        "test_exit_code": 0,
        "verification_level": "controller-attested",
    }


def cmd_submit(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    artifact = read_limited(Path(args.artifact).expanduser())
    with locked(directory):
        manifest = load_manifest(directory)
        if args.candidate not in manifest["candidates"]:
            raise CouncilError(f"unknown candidate: {args.candidate}")
        slot = manifest["candidates"][args.candidate]
        if slot["submission"] is not None:
            raise CouncilError(f"{args.candidate} is already sealed")
        if manifest["profile"] == "dual-backbone-v3":
            if not all(
                all(value is not None for value in candidate["contributors"].values())
                for candidate in manifest["candidates"].values()
            ):
                raise CouncilError("global blind barrier requires all six backbone drafts before any lane synthesis")
            if any(value is None for value in slot["contributors"].values()):
                raise CouncilError("both backbone drafts must be sealed first")
            if slot["diversity_audit"] is None:
                raise CouncilError("run diversity audit before lane synthesis submission")
            if slot["diversity_audit"]["independence_warning"]:
                raise CouncilError("research overlap warning must be resolved in a fresh downgraded/retry run")
            if slot["orca_ref"] is None:
                raise CouncilError("bind the lane synthesis Orca dispatch before submission")
            trace = []
        elif manifest["profile"] == "race":
            if slot["orca_ref"] is None:
                raise CouncilError("bind the race candidate Orca dispatch before submission")
            proof_path = getattr(args, "race_attestation", None)
            test_path = getattr(args, "test_report", None)
            if not proof_path or not test_path:
                raise CouncilError("race submission requires --race-attestation and --test-report")
            proof_raw = parse_json_file(proof_path, "race attestation")
            proof = normalize_race_proof(proof_raw, manifest, slot)
            for other in manifest["candidates"].values():
                if other["race_proof"] is None:
                    continue
                for key in ("commit_sha", "worktree_id", "home_id", "xdg_id", "session_id"):
                    if other["race_proof"][key] == proof[key]:
                        raise CouncilError(f"race isolation {key} must be unique across candidates")
            proof_data = read_limited(Path(proof_path).expanduser())
            test_data = read_limited(Path(test_path).expanduser())
            proof_relative = f"sealed/race/{args.candidate}-attestation.json"
            test_relative = f"sealed/race/{args.candidate}-test.txt"
            atomic_write(directory / proof_relative, proof_data)
            atomic_write(directory / test_relative, test_data)
            slot["race_proof"] = proof | {
                "attestation": file_record(proof_relative, proof_data),
                "test_report": file_record(test_relative, test_data),
            }
            trace = []
        else:
            trace = parse_trace(args.trace, manifest["policy"]["max_children_per_candidate"])
        label = slot["anonymous_id"]
        relative = f"sealed/candidates/{label}.md"
        atomic_write(directory / relative, artifact)
        slot["submission"] = file_record(relative, artifact)
        slot["child_agents"] = trace
        slot["status"] = "sealed"
        if all(item["submission"] is not None for item in manifest["candidates"].values()):
            manifest["state"] = "CANDIDATES_SEALED"
        event(manifest, "candidate_sealed", candidate=args.candidate, anonymous_id=label)
        save_manifest(directory, manifest)
    return {
        "ok": True,
        "run_id": manifest["run_id"],
        "candidate": args.candidate,
        "anonymous_id": label,
        "sha256": slot["submission"]["sha256"],
        "state": manifest["state"],
    }


def normalize_claim(candidate: str, value: Any, existing: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CouncilError("each claim must be an object")
    local_id = str(value.get("id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,50}", local_id):
        raise CouncilError(f"invalid claim id: {local_id!r}")
    claim_id = f"{candidate}:{local_id}"
    if claim_id in existing:
        raise CouncilError(f"duplicate claim id: {claim_id}")
    kind = str(value.get("kind") or "").strip().lower()
    allowed = {"problem", "assumption", "approach", "constraint", "metric", "nongoal", "edge"}
    if kind not in allowed:
        raise CouncilError(f"{claim_id}.kind must be one of {sorted(allowed)}")
    text = str(value.get("text") or "").strip()
    kill = str(value.get("killCondition") or value.get("kill_condition") or "").strip()
    if not text or not kill:
        raise CouncilError(f"{claim_id} requires text and killCondition")
    evidence = value.get("evidence") or []
    if not isinstance(evidence, list):
        raise CouncilError(f"{claim_id}.evidence must be an array")
    return {
        "id": claim_id,
        "kind": kind,
        "text": text[:8000],
        "origin": candidate,
        "kill_condition": kill[:8000],
        "evidence": evidence[:30],
        "verdicts": [],
        "status": "undecided",
        "created_at": utc_now(),
    }


def cmd_ingest_claims(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    raw = parse_json_file(args.claims, "claims")
    if not isinstance(raw, list) or not raw:
        raise CouncilError("claims must be a non-empty JSON array")
    with locked(directory):
        manifest = load_manifest(directory)
        if manifest["mode"] != "plan":
            raise CouncilError("claim ledger is plan-only")
        if args.candidate not in manifest["candidates"]:
            raise CouncilError(f"unknown candidate: {args.candidate}")
        if not all(slot["submission"] is not None for slot in manifest["candidates"].values()):
            raise CouncilError("Claim Barrier opens only after all three lane syntheses are sealed")
        slot = manifest["candidates"][args.candidate]
        if slot["claims_ingested"]:
            raise CouncilError(f"claims already ingested for {args.candidate}")
        existing = set(manifest["claims"])
        additions = [normalize_claim(args.candidate, value, existing) for value in raw]
        for claim in additions:
            manifest["claims"][claim["id"]] = claim
            existing.add(claim["id"])
        slot["claims_ingested"] = True
        manifest["state"] = (
            "CLAIMS_SEALED"
            if all(candidate["claims_ingested"] for candidate in manifest["candidates"].values())
            else "CLAIMS_INGESTING"
        )
        event(manifest, "claims_ingested", candidate=args.candidate, count=len(additions))
        save_manifest(directory, manifest)
    return {"ok": True, "run_id": manifest["run_id"], "added": [item["id"] for item in additions]}


def cmd_verdict(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    with locked(directory):
        manifest = load_manifest(directory)
        if not all(slot["claims_ingested"] for slot in manifest["candidates"].values()):
            raise CouncilError("all lane claims must be sealed before refutation")
        if manifest["orca_refs"]["refuter"] is None:
            raise CouncilError("bind the fresh refuter Orca dispatch before verdicts")
        claim = manifest["claims"].get(args.claim_id)
        if claim is None:
            raise CouncilError(f"unknown claim: {args.claim_id}")
        if args.author_role != "refuter":
            raise CouncilError("claim verdicts must come from the bound refuter role")
        if args.author_role == claim["origin"]:
            raise CouncilError("a claim author cannot judge their own claim")
        # undecided는 1회 재판정 허용 — 봉인하면 HARDENED(undecided 0 요구)에 영구 도달 불가
        # (2026-07-29 실전 데드락). 확정 판정(refuted/survives)은 불변.
        if claim["verdicts"] and claim["status"] != "undecided":
            raise CouncilError("claim verdict is immutable once resolved")
        claim["verdicts"].append(
            {
                "author_role": args.author_role,
                "result": args.result,
                "why": args.why[:8000],
                "at": utc_now(),
            }
        )
        claim["status"] = args.result
        if all(item["status"] != "undecided" for item in manifest["claims"].values()):
            manifest["state"] = "HARDENED"
        event(manifest, "claim_verdict", claim_id=args.claim_id, result=args.result)
        save_manifest(directory, manifest)
    return {"ok": True, "run_id": manifest["run_id"], "claim_id": args.claim_id, "status": args.result}


def cmd_judge_bundle(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    with locked(directory):
        manifest = load_manifest(directory)
        if manifest["judge_bundle"] is not None:
            raise CouncilError("judge bundle is already sealed")
        expected_state = "HARDENED" if manifest["mode"] == "plan" else "CANDIDATES_SEALED"
        if manifest["state"] != expected_state:
            raise CouncilError(f"judge bundle requires state {expected_state}")
        if not all(slot["submission"] is not None for slot in manifest["candidates"].values()):
            raise CouncilError("all candidates must be sealed before judging")
        if manifest["mode"] == "plan":
            if not all(slot["claims_ingested"] for slot in manifest["candidates"].values()):
                raise CouncilError("all lane claims must be sealed before judging")
            if manifest["orca_refs"]["refuter"] is None:
                raise CouncilError("bind the refuter before judging")
            unresolved = sorted(key for key, claim in manifest["claims"].items() if claim["status"] == "undecided")
            if unresolved:
                raise CouncilError(f"all claims must be hardened before judging: {unresolved}")
        candidates = {}
        for lane, slot in manifest["candidates"].items():
            verify_record(directory, slot["submission"], slot["anonymous_id"])
            data = read_limited(directory / slot["submission"]["path"])
            candidates[slot["anonymous_id"]] = {
                "sha256": slot["submission"]["sha256"],
                "content": data.decode("utf-8", errors="replace"),
            }
            if manifest["mode"] == "plan":
                candidates[slot["anonymous_id"]]["hardened_claims"] = [
                    {
                        "kind": claim["kind"],
                        "text": claim["text"],
                        "kill_condition": claim["kill_condition"],
                        "evidence": claim["evidence"],
                        "status": claim["status"],
                        "refutation": claim["verdicts"][-1],
                    }
                    for claim in manifest["claims"].values()
                    if claim["origin"] == lane
                ]
            elif manifest["mode"] == "race":
                proof = slot["race_proof"]
                if proof is None:
                    raise CouncilError("all race candidates require sealed commit/test/isolation proof")
                verify_record(directory, proof["attestation"], f"{lane} race attestation")
                verify_record(directory, proof["test_report"], f"{lane} test report")
                test_data = read_limited(directory / proof["test_report"]["path"])
                candidates[slot["anonymous_id"]]["execution_proof"] = {
                    "base_sha": proof["base_sha"],
                    "commit_sha": proof["commit_sha"],
                    "test_command": proof["test_command"],
                    "test_report_sha256": proof["test_report"]["sha256"],
                    "test_report": test_data.decode("utf-8", errors="replace"),
                    "isolation": {
                        "worktree_id": proof["worktree_id"],
                        "home_id": proof["home_id"],
                        "xdg_id": proof["xdg_id"],
                        "session_id": proof["session_id"],
                    },
                    "verification_level": proof["verification_level"],
                }
        brief = read_limited(directory / manifest["inputs"]["brief"]["path"])
        rubric = read_limited(directory / manifest["inputs"]["rubric"]["path"])
        bundle = {
            "schema_version": SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "brief": {"sha256": sha256(brief), "content": brief.decode(errors="replace")},
            "rubric": {"sha256": sha256(rubric), "content": rubric.decode(errors="replace")},
            "candidates": dict(sorted(candidates.items())),
            "scoring": {
                "weights": WEIGHTS,
                "score_range": [0, 5],
                "evidence_gate": "D1 and D2 must both be non-zero",
                "draw_margin": 8,
                "minimum_judges": manifest["policy"]["minimum_judges"],
            },
        }
        path = directory / "sealed/judge-bundle.json"
        write_json(path, bundle)
        manifest["judge_bundle"] = file_record("sealed/judge-bundle.json", path.read_bytes())
        manifest["state"] = "JUDGING"
        event(manifest, "judge_bundle_sealed", sha256=sha256(path.read_bytes()))
        save_manifest(directory, manifest)
    return {"ok": True, "run_id": manifest["run_id"], "bundle": str(path), "anonymous_candidates": sorted(candidates)}


def normalize_dimension(candidate: str, name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CouncilError(f"{candidate}.{name} must be an object")
    score = value.get("score")
    evidence = str(value.get("evidence") or "").strip()
    if not isinstance(score, int) or not 0 <= score <= 5 or not evidence:
        raise CouncilError(f"{candidate}.{name} requires score 0..5 and evidence")
    return {"score": score, "evidence": evidence[:4000], "weighted": score * WEIGHTS[name]}


def compute_judgment(raw: Any, expected: list[str], default_id: str) -> tuple[str, dict[str, Any]]:
    received = raw.get("candidates") if isinstance(raw, dict) else None
    if not isinstance(received, dict) or sorted(received) != expected:
        raise CouncilError(f"judgment candidates must be exactly {expected}")
    judge_id = str(raw.get("judgeId") or raw.get("judge_id") or default_id).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", judge_id):
        raise CouncilError(f"invalid judge id: {judge_id!r}")
    computed = {}
    for label in expected:
        item = received[label]
        dimensions = item.get("dimensions") if isinstance(item, dict) else None
        if not isinstance(dimensions, dict) or set(dimensions) != set(WEIGHTS):
            raise CouncilError(f"candidate {label} requires dimensions {sorted(WEIGHTS)}")
        dims = {name: normalize_dimension(label, name, dimensions[name]) for name in WEIGHTS}
        concessions = item.get("concessions")
        counters = item.get("counters")
        if not isinstance(concessions, list) or not concessions or not isinstance(counters, list) or not counters:
            raise CouncilError(f"candidate {label} requires concession and counter")
        blockers = [str(value)[:2000] for value in (item.get("blockers") or [])]
        computed[label] = {
            "dimensions": dims,
            "total": sum(value["weighted"] for value in dims.values()),
            "eligible": dims["D1"]["score"] > 0 and dims["D2"]["score"] > 0 and not blockers,
            "concessions": concessions,
            "counters": counters,
            "blockers": blockers,
        }
    ranked = sorted(
        ((label, item["total"]) for label, item in computed.items() if item["eligible"]),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return judge_id, {"candidates": computed, "top_choice": ranked[0][0] if ranked else "DRAW"}


def cmd_score(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    raw = [parse_json_file(path, "judgment") for path in args.judgment]
    with locked(directory):
        manifest = load_manifest(directory)
        if manifest["state"] != "JUDGING":
            raise CouncilError("seal judge bundle first")
        if manifest["judgment"] is not None:
            raise CouncilError("judgment is immutable; create a new run to rescore")
        if manifest["judge_bundle"] is None:
            raise CouncilError("sealed judge bundle record is missing")
        verify_record(directory, manifest["judge_bundle"], "judge bundle")
        required = manifest["policy"]["minimum_judges"]
        if len(raw) != required:
            raise CouncilError(f"exactly {required} independent judgments required")
        judge_refs = manifest["orca_refs"]["judges"]
        if len(judge_refs) != required:
            raise CouncilError(f"bind exactly {required} fresh Orca judge dispatches before scoring")
        backbones = sorted(model_backbone(item["model_id"]) for item in judge_refs.values())
        if manifest["profile"] in {"dual-backbone-v3", "race"} and backbones != ["fable", "gpt-sol"]:
            raise CouncilError("judges must be one fresh Fable and one fresh gpt-5.6-sol")
        expected = sorted(slot["anonymous_id"] for slot in manifest["candidates"].values())
        judges = {}
        for index, value in enumerate(raw, 1):
            judge_id, computed = compute_judgment(value, expected, f"judge-{index}")
            if judge_id in judges:
                raise CouncilError(f"duplicate judge id: {judge_id}")
            judges[judge_id] = computed
        if set(judges) != set(judge_refs):
            raise CouncilError("judgment judgeId values must exactly match bound Orca judge roles")
        aggregate = {}
        for label in expected:
            totals = [judge["candidates"][label]["total"] for judge in judges.values()]
            aggregate[label] = {
                "average_total": sum(totals) / len(totals),
                "judge_totals": totals,
                "eligible": all(judge["candidates"][label]["eligible"] for judge in judges.values()),
            }
        eligible = sorted(
            ((label, item["average_total"]) for label, item in aggregate.items() if item["eligible"]),
            key=lambda pair: (-pair[1], pair[0]),
        )
        tops = {judge["top_choice"] for judge in judges.values()}
        unanimous = len(tops) == 1
        margin = eligible[0][1] - eligible[1][1] if len(eligible) >= 2 else None
        verdict = "DRAW"
        if eligible and unanimous and all(judge["top_choice"] == eligible[0][0] for judge in judges.values()):
            if len(eligible) == 1 or (margin is not None and margin >= 8):
                verdict = eligible[0][0]
        sealed = {
            "schema_version": SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "computed_verdict": verdict,
            "margin": margin,
            "aggregate": aggregate,
            "judges": judges,
            "recorded_at": utc_now(),
        }
        path = directory / "sealed/judgment.json"
        write_json(path, sealed)
        manifest["judgment"] = file_record("sealed/judgment.json", path.read_bytes()) | {
            "computed_verdict": verdict,
            "margin": margin,
            "judge_count": len(judges),
        }
        manifest["state"] = "JUDGED"
        event(manifest, "judgment_scored", verdict=verdict, margin=margin)
        save_manifest(directory, manifest)
    return {"ok": True, "run_id": manifest["run_id"], "computed_verdict": verdict, "margin": margin}


def validate_spec_seed(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CouncilError("spec seed must be an object")
    non_goals = value.get("nonGoals") or value.get("non_goals")
    metrics = value.get("metrics")
    if not isinstance(non_goals, list) or not non_goals or not isinstance(metrics, list) or not metrics:
        raise CouncilError("spec seed requires non-goals and metrics")
    return {
        "problem": str(value.get("problem") or "")[:8000],
        "chosen": [str(item)[:3000] for item in (value.get("chosen") or [])],
        "rejected": [str(item)[:3000] for item in (value.get("rejected") or [])],
        "deferred": [str(item)[:3000] for item in (value.get("deferred") or [])],
        "disagreements": [str(item)[:3000] for item in (value.get("disagreements") or [])],
        "non_goals": [str(item)[:2000] for item in non_goals],
        "metrics": metrics,
    }


def cmd_spec_seed(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    normalized = validate_spec_seed(parse_json_file(args.spec_seed, "spec seed"))
    with locked(directory):
        manifest = load_manifest(directory)
        if manifest["mode"] != "plan" or manifest["state"] != "JUDGED":
            raise CouncilError("plan must be JUDGED before sealing spec seed")
        if manifest["orca_refs"]["synthesis"] is None:
            raise CouncilError("bind the fresh non-advocate synthesis dispatch before sealing spec seed")
        if manifest["spec_seed"] is not None:
            raise CouncilError("spec seed is already sealed")
        path = directory / "sealed/spec-seed.json"
        write_json(path, normalized)
        manifest["spec_seed"] = file_record("sealed/spec-seed.json", path.read_bytes())
        event(manifest, "spec_seed_sealed")
        save_manifest(directory, manifest)
    return {"ok": True, "run_id": manifest["run_id"], "sha256": manifest["spec_seed"]["sha256"]}


def plan_readiness(manifest: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    unresolved = sorted(key for key, claim in manifest["claims"].items() if claim["status"] == "undecided")
    surviving = {claim["kind"] for claim in manifest["claims"].values() if claim["status"] == "survives"}
    missing = sorted({"problem", "assumption", "metric", "nongoal"} - surviving)
    ready = bool(manifest["claims"]) and not unresolved and not missing and manifest["spec_seed"] is not None and manifest["judgment"] is not None
    return ready, unresolved, missing


def cmd_readiness(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(run_dir(args))
    if manifest["mode"] != "plan":
        raise CouncilError("readiness is plan-only")
    ready, unresolved, missing = plan_readiness(manifest)
    return {"ok": True, "run_id": manifest["run_id"], "ready_for_user_gate": ready, "unresolved_claims": unresolved, "missing_claim_kinds": missing}


def cmd_decide(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    with locked(directory):
        manifest = load_manifest(directory)
        if manifest["decision"] is not None:
            raise CouncilError("user decision is immutable; create a new run to change it")
        if manifest["mode"] != "race" or manifest["state"] != "JUDGED":
            raise CouncilError("race must be JUDGED before decision")
        allowed = {slot["anonymous_id"] for slot in manifest["candidates"].values()} | {"DRAW", "STOP"}
        choice = args.choice.upper()
        if choice not in allowed:
            raise CouncilError(f"choice must be one of {sorted(allowed)}")
        computed = manifest["judgment"]["computed_verdict"]
        if choice != computed and not args.reason:
            raise CouncilError("overriding computed verdict requires --reason")
        manifest["decision"] = {"choice": choice, "by": "user", "reason": args.reason or "", "decided_at": utc_now()}
        manifest["state"] = "CANCELLED" if choice == "STOP" else "DECIDED"
        event(manifest, "user_decision", choice=choice)
        save_manifest(directory, manifest)
    return {"ok": True, "run_id": manifest["run_id"], "state": manifest["state"], "decision": manifest["decision"]}


def cmd_plan_decide(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    with locked(directory):
        manifest = load_manifest(directory)
        if manifest["mode"] != "plan":
            raise CouncilError("plan-decide is plan-only")
        if manifest["decision"] is not None:
            raise CouncilError("user decision is immutable; create a new run to change it")
        ready, unresolved, missing = plan_readiness(manifest)
        if args.choice == "ADOPT" and not ready:
            raise CouncilError(f"plan not ready: unresolved={unresolved}, missing={missing}")
        if args.choice == "PIVOT" and not args.reason:
            raise CouncilError("PIVOT requires a framing-change reason")
        manifest["decision"] = {"choice": args.choice, "by": "user", "reason": args.reason or "", "decided_at": utc_now()}
        manifest["state"] = {"ADOPT": "DECIDED", "PIVOT": "PIVOT_REQUIRED", "STOP": "CANCELLED"}[args.choice]
        event(manifest, "plan_user_gate", choice=args.choice)
        save_manifest(directory, manifest)
    return {"ok": True, "run_id": manifest["run_id"], "state": manifest["state"], "decision": manifest["decision"]}


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    directory = run_dir(args)
    manifest = load_manifest(directory)
    verify_record(directory, manifest["inputs"]["brief"], "brief")
    verify_record(directory, manifest["inputs"]["rubric"], "rubric")
    for name, slot in manifest["candidates"].items():
        for backbone, contributor in slot["contributors"].items():
            if contributor:
                verify_record(directory, contributor["artifact"], f"{name}/{backbone} artifact")
                verify_record(directory, contributor["research_log"], f"{name}/{backbone} research")
        if slot["submission"]:
            verify_record(directory, slot["submission"], name)
        if slot["orca_ref"]:
            verify_record(directory, slot["orca_ref"]["attestation"], f"{name} Orca attestation")
        if slot["race_proof"]:
            verify_record(directory, slot["race_proof"]["attestation"], f"{name} race attestation")
            verify_record(directory, slot["race_proof"]["test_report"], f"{name} race test")
    for reference in all_references(manifest):
        verify_record(directory, reference["attestation"], f"{reference['task_id']} Orca attestation")
    if manifest["judge_bundle"]:
        verify_record(directory, manifest["judge_bundle"], "judge bundle")
    if manifest["judgment"]:
        verify_record(directory, manifest["judgment"], "judgment")
    if manifest["spec_seed"]:
        verify_record(directory, manifest["spec_seed"], "spec seed")
    return {"ok": True, "run_id": manifest["run_id"], "integrity": "PASS", "state": manifest["state"]}


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(run_dir(args))
    return {
        "ok": True,
        "run_id": manifest["run_id"],
        "mode": manifest["mode"],
        "profile": manifest["profile"],
        "state": manifest["state"],
        "lifecycle_authority": "orca-orchestration",
        "artifact_ledger_copies_orca_status": False,
        "candidates": {
            name: {
                "status": slot["status"],
                "anonymous_id": slot["anonymous_id"] if args.reveal_mapping else "<sealed>",
                "backbones_sealed": sorted(backbone for backbone, value in slot["contributors"].items() if value),
                "diversity_warning": (slot["diversity_audit"] or {}).get("independence_warning"),
                "submission_sha256": (slot["submission"] or {}).get("sha256"),
                "orca_ref_recorded": slot["orca_ref"] is not None,
            }
            for name, slot in manifest["candidates"].items()
        },
        "claim_count": len(manifest["claims"]),
        "judgment": manifest["judgment"],
        "spec_seed_sealed": manifest["spec_seed"] is not None,
        "decision": manifest["decision"],
    }


def add_reference_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--dispatch-id", required=True)
    parser.add_argument("--terminal-handle", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--parent-task-id")
    parser.add_argument("--deps-json", default="[]")
    parser.add_argument("--attestation", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--mode", choices=("plan", "race"), required=True)
    init.add_argument("--profile", choices=("lightweight", "dual-backbone-v3"), default="dual-backbone-v3")
    init.add_argument("--slug", required=True)
    init.add_argument("--brief", required=True)
    init.add_argument("--rubric", required=True)
    init.add_argument("--candidates", type=int, default=3)
    init.add_argument("--base-sha")
    init.add_argument("--run-id")
    init.set_defaults(func=cmd_init)

    bind = sub.add_parser("bind", help="record opaque Orca provenance; never copies task status")
    bind.add_argument("--run", required=True)
    bind.add_argument("--role", required=True)
    add_reference_args(bind)
    bind.set_defaults(func=cmd_bind)

    contributor = sub.add_parser("contributor-submit", help="seal one Fable/GPT lane worker artifact")
    contributor.add_argument("--run", required=True)
    contributor.add_argument("--candidate", required=True)
    contributor.add_argument("--backbone", choices=BACKBONES, required=True)
    contributor.add_argument("--artifact", required=True)
    contributor.add_argument("--research-log", required=True)
    add_reference_args(contributor)
    contributor.set_defaults(func=cmd_contributor_submit)

    audit = sub.add_parser("audit-diversity")
    audit.add_argument("--run", required=True)
    audit.add_argument("--candidate", required=True)
    audit.set_defaults(func=cmd_audit_diversity)

    submit = sub.add_parser("submit", help="seal lane synthesis or race candidate")
    submit.add_argument("--run", required=True)
    submit.add_argument("--candidate", required=True)
    submit.add_argument("--artifact", required=True)
    submit.add_argument("--trace")
    submit.add_argument("--race-attestation")
    submit.add_argument("--test-report")
    submit.set_defaults(func=cmd_submit)

    claims = sub.add_parser("ingest-claims")
    claims.add_argument("--run", required=True)
    claims.add_argument("--candidate", required=True)
    claims.add_argument("--claims", required=True)
    claims.set_defaults(func=cmd_ingest_claims)

    verdict = sub.add_parser("verdict")
    verdict.add_argument("--run", required=True)
    verdict.add_argument("--claim-id", required=True)
    verdict.add_argument("--author-role", required=True)
    verdict.add_argument("--result", choices=("refuted", "survives", "undecided"), required=True)
    verdict.add_argument("--why", required=True)
    verdict.set_defaults(func=cmd_verdict)

    bundle = sub.add_parser("judge-bundle")
    bundle.add_argument("--run", required=True)
    bundle.set_defaults(func=cmd_judge_bundle)

    score = sub.add_parser("score")
    score.add_argument("--run", required=True)
    score.add_argument("--judgment", action="append", required=True)
    score.set_defaults(func=cmd_score)

    seed = sub.add_parser("spec-seed")
    seed.add_argument("--run", required=True)
    seed.add_argument("--spec-seed", required=True)
    seed.set_defaults(func=cmd_spec_seed)

    readiness = sub.add_parser("readiness")
    readiness.add_argument("--run", required=True)
    readiness.set_defaults(func=cmd_readiness)

    decide = sub.add_parser("decide")
    decide.add_argument("--run", required=True)
    decide.add_argument("--choice", required=True)
    decide.add_argument("--reason")
    decide.set_defaults(func=cmd_decide)

    plan_decide = sub.add_parser("plan-decide")
    plan_decide.add_argument("--run", required=True)
    plan_decide.add_argument("--choice", choices=("ADOPT", "PIVOT", "STOP"), required=True)
    plan_decide.add_argument("--reason")
    plan_decide.set_defaults(func=cmd_plan_decide)

    verify = sub.add_parser("verify")
    verify.add_argument("--run", required=True)
    verify.set_defaults(func=cmd_verify)

    status = sub.add_parser("status")
    status.add_argument("--run", required=True)
    status.add_argument("--reveal-mapping", action="store_true")
    status.set_defaults(func=cmd_status)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = args.func(args)
    except CouncilError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"unexpected: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
