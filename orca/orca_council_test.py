#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "system/orca-council.py"
LANES = ("lane-A", "lane-B", "lane-C")


class CouncilCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.brief = self.write("brief.md", "Build a useful system.\n")
        self.rubric = self.write("rubric.md", "D1..D5\n")
        self.counter = 0

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content) if isinstance(content, (dict, list)) else content, encoding="utf-8")
        return path

    def cli(self, *args, ok=True):
        result = subprocess.run(
            ["python3", str(SCRIPT), "--state-root", str(self.state), *map(str, args)],
            text=True, capture_output=True, check=False,
        )
        if ok and result.returncode:
            self.fail(f"failed {args}\nstdout={result.stdout}\nstderr={result.stderr}")
        if not ok:
            self.assertNotEqual(result.returncode, 0)
        return json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def manifest(self, run):
        return json.loads((self.state / run / "manifest.json").read_text(encoding="utf-8"))

    def attestation(self, name, task, dispatch, terminal, model, session, parent=None, deps=None):
        return self.write(f"attest-{name}.json", {
            "task_id": task,
            "dispatch_id": dispatch,
            "terminal_handle": terminal,
            "model_id": model,
            "session_id": session,
            "parent_task_id": parent,
            "deps": sorted(deps or []),
        })

    def ref_args(self, name, task, dispatch, terminal, model, session, parent=None, deps=None):
        attestation = self.attestation(name, task, dispatch, terminal, model, session, parent, deps)
        args = [
            "--task-id", task, "--dispatch-id", dispatch, "--terminal-handle", terminal,
            "--model-id", model, "--session-id", session,
            "--deps-json", json.dumps(sorted(deps or [])), "--attestation", attestation,
        ]
        if parent:
            args += ["--parent-task-id", parent]
        return args

    def init_plan(self, run="plan-v3", bind_root=True):
        result = self.cli(
            "init", "--mode", "plan", "--profile", "dual-backbone-v3",
            "--slug", "test", "--brief", self.brief, "--rubric", self.rubric,
            "--candidates", "3", "--run-id", run,
        )
        if bind_root:
            self.bind(run, "root", "task_ROOT", "ctx_ROOT", "term_root", "coordinator", "session-root")
        return result

    def init_race(self, run="race-v3"):
        self.cli(
            "init", "--mode", "race", "--slug", "race", "--brief", self.brief,
            "--rubric", self.rubric, "--candidates", "2", "--base-sha", "a" * 40, "--run-id", run,
        )
        self.bind(run, "root", "task_RROOT", "ctx_RROOT", "term_rroot", "coordinator", "race-root")

    def bind(self, run, role, task, dispatch, terminal, model, session, parent=None, deps=None, ok=True):
        return self.cli(
            "bind", "--run", run, "--role", role,
            *self.ref_args(f"{run}-{role}", task, dispatch, terminal, model, session, parent, deps),
            ok=ok,
        )

    def contributor(self, run, lane, backbone, entries=None, session=None, task=None, ok=True):
        self.counter += 1
        model = "claude-fable-5" if backbone == "fable" else "gpt-5.6-sol"
        task = task or f"task_W{self.counter}"
        dispatch = f"ctx_W{self.counter}"
        terminal = f"term_w{self.counter}"
        session = session or f"worker-session-{self.counter}"
        artifact = self.write(f"{lane}-{backbone}-{self.counter}.md", f"{lane} {backbone}\n")
        entries = entries if entries is not None else [{
            "query": f"{lane} {backbone} q{self.counter}",
            "url": f"https://{backbone}{self.counter}.example/{lane}",
            "tool": "firecrawl" if backbone == "fable" else "web-search",
            "source_class": "primary",
            "community": backbone,
            "language": "ko" if backbone == "fable" else "en",
            "evidence_root": f"root-{lane}-{backbone}-{self.counter}",
            "polarity": "neutral",
        }]
        log = self.write(f"{lane}-{backbone}-{self.counter}.json", entries)
        return self.cli(
            "contributor-submit", "--run", run, "--candidate", lane, "--backbone", backbone,
            "--artifact", artifact, "--research-log", log,
            *self.ref_args(f"{run}-{lane}-{backbone}-{self.counter}", task, dispatch, terminal, model, session,
                           "task_ROOT", []),
            ok=ok,
        )

    def six_workers(self, run):
        for lane in LANES:
            self.contributor(run, lane, "fable")
            self.contributor(run, lane, "gpt-sol")

    def lane_tasks(self, run):
        return sorted(
            contributor["orca_ref"]["task_id"]
            for slot in self.manifest(run)["candidates"].values()
            for contributor in slot["contributors"].values()
        )

    def seal_lanes(self, run):
        self.six_workers(run)
        deps = self.lane_tasks(run)
        for index, lane in enumerate(LANES, 1):
            self.cli("audit-diversity", "--run", run, "--candidate", lane)
            self.bind(run, lane, f"task_S{index}", f"ctx_S{index}", f"term_s{index}",
                      "synthesis-model", f"synth-session-{index}", "task_ROOT", deps)
            artifact = self.write(f"{lane}-synthesis.md", f"{lane} synthesis\n")
            self.cli("submit", "--run", run, "--candidate", lane, "--artifact", artifact)

    def claims(self, run):
        for lane in LANES:
            path = self.write(f"{lane}-claims.json", [
                {"id": "p", "kind": "problem", "text": f"{lane} problem", "killCondition": "not observed"},
                {"id": "a", "kind": "assumption", "text": f"{lane} assumption", "killCondition": "false"},
                {"id": "m", "kind": "metric", "text": f"{lane} metric", "killCondition": "unmeasurable"},
                {"id": "n", "kind": "nongoal", "text": f"{lane} nongoal", "killCondition": "required"},
            ])
            self.cli("ingest-claims", "--run", run, "--candidate", lane, "--claims", path)
        synth_tasks = sorted(self.manifest(run)["candidates"][lane]["orca_ref"]["task_id"] for lane in LANES)
        self.bind(run, "refuter", "task_REF", "ctx_REF", "term_ref", "refuter-model", "ref-session",
                  "task_ROOT", synth_tasks)
        for claim_id in sorted(self.manifest(run)["claims"]):
            self.cli("verdict", "--run", run, "--claim-id", claim_id, "--author-role", "refuter",
                     "--result", "survives", "--why", "independent evidence")

    def bind_judges(self, run):
        manifest = self.manifest(run)
        deps = [manifest["orca_refs"]["refuter"]["task_id"]] if manifest["mode"] == "plan" else sorted(
            slot["orca_ref"]["task_id"] for slot in manifest["candidates"].values()
        )
        parent = manifest["orca_refs"]["root"]["task_id"]
        self.bind(run, "judge-fable", "task_JF", "ctx_JF", "term_jf", "claude-fable-5", "judge-f-session", parent, deps)
        self.bind(run, "judge-gpt-sol", "task_JG", "ctx_JG", "term_jg", "gpt-5.6-sol", "judge-g-session", parent, deps)

    def judgment_files(self, run):
        labels = sorted(slot["anonymous_id"] for slot in self.manifest(run)["candidates"].values())
        output = []
        for judge in ("judge-fable", "judge-gpt-sol"):
            candidates = {}
            for index, label in enumerate(labels):
                score = 5 if index == 0 else 2
                candidates[label] = {
                    "dimensions": {name: {"score": score, "evidence": f"{judge} {name}"} for name in ("D1", "D2", "D3", "D4", "D5")},
                    "concessions": ["strength"], "counters": ["counter"], "blockers": [],
                }
            output.append(self.write(f"{judge}.json", {"judgeId": judge, "candidates": candidates}))
        return output

    def race_candidate(self, run, index):
        candidate = f"candidate-{index}"
        self.bind(run, candidate, f"task_RC{index}", f"ctx_RC{index}", f"term_rc{index}",
                  "writer-model", f"race-c{index}", "task_RROOT", [])
        artifact = self.write(f"race-c{index}.md", f"candidate {index}")
        proof = self.write(f"race-proof-{index}.json", {
            "base_sha": "a" * 40,
            "commit_sha": ("%x" % (10 + index)) * 40,
            "worktree_id": f"wt-{index}", "home_id": f"home-{index}", "xdg_id": f"xdg-{index}",
            "session_id": f"race-c{index}", "child_agent_count": 0, "sibling_access": False,
            "test_command": "make test", "test_exit_code": 0,
        })
        report = self.write(f"race-test-{index}.txt", "PASS\n")
        self.cli("submit", "--run", run, "--candidate", candidate, "--artifact", artifact,
                 "--race-attestation", proof, "--test-report", report)

    def test_artifact_ledger_never_calls_orca(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("orca-ide", source)

    def test_reference_is_controller_attested_not_live_verified(self):
        self.init_plan()
        reference = self.manifest("plan-v3")["orca_refs"]["root"]
        self.assertEqual(reference["verification_level"], "controller-attested")
        self.assertFalse(reference["status_copied"])
        self.assertNotIn("task_status", reference)

    def test_attestation_mismatch_fails(self):
        self.init_plan(bind_root=False)
        args = self.ref_args("bad", "task_ROOT", "ctx_ROOT", "term_root", "coordinator", "session-root")
        Path(args[-1]).write_text("{}", encoding="utf-8")
        result = self.cli("bind", "--run", "plan-v3", "--role", "root", *args, ok=False)
        self.assertIn("does not exactly match", result["error"])

    def test_empty_research_log_fails(self):
        self.init_plan()
        result = self.contributor("plan-v3", "lane-A", "fable", entries=[], ok=False)
        self.assertIn("non-empty", result["error"])

    def test_duplicate_task_dispatch_session_or_terminal_fails(self):
        self.init_plan()
        self.contributor("plan-v3", "lane-A", "fable", task="task_DUP", session="unique")
        result = self.contributor("plan-v3", "lane-A", "gpt-sol", task="task_DUP", ok=False)
        self.assertIn("task_id", result["error"])

    def test_diversity_audit_waits_for_all_six(self):
        self.init_plan()
        self.contributor("plan-v3", "lane-A", "fable")
        self.contributor("plan-v3", "lane-A", "gpt-sol")
        result = self.cli("audit-diversity", "--run", "plan-v3", "--candidate", "lane-A", ok=False)
        self.assertIn("all six", result["error"])

    def test_same_query_warns_even_with_distinct_sources(self):
        self.init_plan()
        common_query = "same exact query"
        for lane in LANES:
            self.contributor("plan-v3", lane, "fable", entries=[{
                "query": common_query if lane == "lane-A" else f"{lane} f", "url": f"https://f-{lane}.example/a",
                "tool": "firecrawl", "source_class": "primary", "community": "f", "language": "ko",
                "evidence_root": f"f-{lane}",
            }])
            self.contributor("plan-v3", lane, "gpt-sol", entries=[{
                "query": common_query if lane == "lane-A" else f"{lane} g", "url": f"https://g-{lane}.example/b",
                "tool": "web", "source_class": "primary", "community": "g", "language": "en",
                "evidence_root": f"g-{lane}",
            }])
        result = self.cli("audit-diversity", "--run", "plan-v3", "--candidate", "lane-A")
        self.assertTrue(result["audit"]["independence_warning"])

    def test_lane_bind_requires_all_six_dependencies(self):
        self.init_plan()
        self.six_workers("plan-v3")
        result = self.bind("plan-v3", "lane-A", "task_S1", "ctx_S1", "term_s1", "synth", "synth-1",
                           "task_ROOT", self.lane_tasks("plan-v3")[:2], ok=False)
        self.assertIn("all six", result["error"])

    def test_claim_ingest_waits_for_all_three_lane_submissions(self):
        self.init_plan()
        self.six_workers("plan-v3")
        deps = self.lane_tasks("plan-v3")
        for lane in LANES:
            self.cli("audit-diversity", "--run", "plan-v3", "--candidate", lane)
        self.bind("plan-v3", "lane-A", "task_S1", "ctx_S1", "term_s1", "synth", "synth-1", "task_ROOT", deps)
        self.cli("submit", "--run", "plan-v3", "--candidate", "lane-A", "--artifact", self.write("a.md", "A"))
        claims = self.write("early-claims.json", [{"id": "p", "kind": "problem", "text": "p", "killCondition": "k"}])
        result = self.cli("ingest-claims", "--run", "plan-v3", "--candidate", "lane-A", "--claims", claims, ok=False)
        self.assertIn("all three", result["error"])

    def test_judge_bundle_requires_hardened_claims_and_refuter(self):
        self.init_plan()
        self.seal_lanes("plan-v3")
        result = self.cli("judge-bundle", "--run", "plan-v3", ok=False)
        self.assertIn("HARDENED", result["error"])

    def test_score_requires_two_bound_model_diverse_judges(self):
        self.init_plan()
        self.seal_lanes("plan-v3")
        self.claims("plan-v3")
        self.cli("judge-bundle", "--run", "plan-v3")
        files = self.judgment_files("plan-v3")
        result = self.cli("score", "--run", "plan-v3", "--judgment", files[0], "--judgment", files[1], ok=False)
        self.assertIn("bind exactly 2", result["error"])

    def test_full_plan_happy_path_and_bundle_tamper(self):
        self.init_plan()
        self.seal_lanes("plan-v3")
        self.claims("plan-v3")
        bundle = self.cli("judge-bundle", "--run", "plan-v3")
        payload = json.loads(Path(bundle["bundle"]).read_text(encoding="utf-8"))
        self.assertTrue(all(item["hardened_claims"] for item in payload["candidates"].values()))
        self.bind_judges("plan-v3")
        files = self.judgment_files("plan-v3")
        self.cli("score", "--run", "plan-v3", "--judgment", files[0], "--judgment", files[1])
        manifest = self.manifest("plan-v3")
        judge_tasks = sorted(item["task_id"] for item in manifest["orca_refs"]["judges"].values())
        self.bind("plan-v3", "synthesis", "task_FINAL", "ctx_FINAL", "term_final", "fresh-synth", "final-session",
                  "task_ROOT", judge_tasks)
        seed = self.write("seed.json", {
            "problem": "p", "chosen": ["x"], "rejected": [], "deferred": [], "disagreements": [],
            "nonGoals": ["y"], "metrics": [{"metric": "m", "target": "1", "measurement": "test"}],
        })
        self.cli("spec-seed", "--run", "plan-v3", "--spec-seed", seed)
        self.assertTrue(self.cli("readiness", "--run", "plan-v3")["ready_for_user_gate"])
        self.cli("plan-decide", "--run", "plan-v3", "--choice", "ADOPT")
        result = self.cli("plan-decide", "--run", "plan-v3", "--choice", "STOP", ok=False)
        self.assertIn("immutable", result["error"])
        self.assertEqual(self.cli("verify", "--run", "plan-v3")["integrity"], "PASS")
        Path(bundle["bundle"]).write_text("{}", encoding="utf-8")
        self.assertIn("integrity", self.cli("verify", "--run", "plan-v3", ok=False)["error"])

    def test_race_requires_isolation_commit_and_test_proof(self):
        self.init_race()
        self.bind("race-v3", "candidate-1", "task_RC1", "ctx_RC1", "term_rc1", "writer", "race-c1",
                  "task_RROOT", [])
        artifact = self.write("race-c1.md", "candidate")
        result = self.cli("submit", "--run", "race-v3", "--candidate", "candidate-1", "--artifact", artifact, ok=False)
        self.assertIn("race-attestation", result["error"])
        proof = self.write("race-proof.json", {
            "base_sha": "a" * 40, "commit_sha": "b" * 40, "worktree_id": "wt-1",
            "home_id": "home-1", "xdg_id": "xdg-1", "session_id": "race-c1",
            "child_agent_count": 0, "sibling_access": False, "test_command": "make test", "test_exit_code": 0,
        })
        test_report = self.write("race-test.txt", "PASS\n")
        self.cli("submit", "--run", "race-v3", "--candidate", "candidate-1", "--artifact", artifact,
                 "--race-attestation", proof, "--test-report", test_report)
        self.assertEqual(self.manifest("race-v3")["candidates"]["candidate-1"]["race_proof"]["commit_sha"], "b" * 40)

    def test_full_race_requires_model_diverse_judges_and_immutable_decision(self):
        self.init_race()
        self.race_candidate("race-v3", 1)
        self.race_candidate("race-v3", 2)
        bundle = self.cli("judge-bundle", "--run", "race-v3")
        payload = json.loads(Path(bundle["bundle"]).read_text(encoding="utf-8"))
        self.assertTrue(all(item["execution_proof"]["test_report"] == "PASS\n" for item in payload["candidates"].values()))
        self.bind_judges("race-v3")
        files = self.judgment_files("race-v3")
        scored = self.cli("score", "--run", "race-v3", "--judgment", files[0], "--judgment", files[1])
        self.cli("decide", "--run", "race-v3", "--choice", scored["computed_verdict"])
        result = self.cli("decide", "--run", "race-v3", "--choice", "STOP", ok=False)
        self.assertIn("immutable", result["error"])

    def test_score_margin_below_eight_is_draw(self):
        self.init_race()
        self.race_candidate("race-v3", 1)
        self.race_candidate("race-v3", 2)
        self.cli("judge-bundle", "--run", "race-v3")
        self.bind_judges("race-v3")
        labels = sorted(slot["anonymous_id"] for slot in self.manifest("race-v3")["candidates"].values())
        files = []
        for judge in ("judge-fable", "judge-gpt-sol"):
            candidates = {}
            for index, label in enumerate(labels):
                score = 5
                candidates[label] = {
                    "dimensions": {
                        name: {"score": (4 if index == 1 and name == "D5" else score), "evidence": "e"}
                        for name in ("D1", "D2", "D3", "D4", "D5")
                    },
                    "concessions": ["c"], "counters": ["c"], "blockers": [],
                }
            files.append(self.write(f"draw-{judge}.json", {"judgeId": judge, "candidates": candidates}))
        result = self.cli("score", "--run", "race-v3", "--judgment", files[0], "--judgment", files[1])
        self.assertEqual(result["computed_verdict"], "DRAW")

    def test_d1_zero_candidate_is_ineligible(self):
        self.init_race()
        self.race_candidate("race-v3", 1)
        self.race_candidate("race-v3", 2)
        self.cli("judge-bundle", "--run", "race-v3")
        self.bind_judges("race-v3")
        labels = sorted(slot["anonymous_id"] for slot in self.manifest("race-v3")["candidates"].values())
        files = []
        for judge in ("judge-fable", "judge-gpt-sol"):
            candidates = {}
            for index, label in enumerate(labels):
                dimensions = {
                    name: {"score": (0 if index == 0 and name == "D1" else 5 if index == 0 else 4), "evidence": "e"}
                    for name in ("D1", "D2", "D3", "D4", "D5")
                }
                candidates[label] = {
                    "dimensions": dimensions, "concessions": ["c"], "counters": ["c"], "blockers": [],
                }
            files.append(self.write(f"gate-{judge}.json", {"judgeId": judge, "candidates": candidates}))
        result = self.cli("score", "--run", "race-v3", "--judgment", files[0], "--judgment", files[1])
        self.assertEqual(result["computed_verdict"], labels[1])

    def test_undecided_verdict_resolves_once_then_immutable(self):
        # 2026-07-29 실전 데드락: undecided 판정도 불변으로 봉인되면 HARDENED(undecided 0 요구)에
        # 영원히 도달 불가. undecided만 1회 재판정을 허용하고, 확정 판정은 여전히 불변이어야 한다.
        self.init_plan()
        self.seal_lanes("plan-v3")
        for lane in LANES:
            path = self.write(f"{lane}-uclaims.json", [
                {"id": "u", "kind": "assumption", "text": f"{lane} u", "killCondition": "kc"},
            ])
            self.cli("ingest-claims", "--run", "plan-v3", "--candidate", lane, "--claims", path)
        synth_tasks = sorted(
            self.manifest("plan-v3")["candidates"][lane]["orca_ref"]["task_id"] for lane in LANES
        )
        self.bind("plan-v3", "refuter", "task_REF", "ctx_REF", "term_ref", "refuter-model",
                  "ref-session", "task_ROOT", synth_tasks)
        claims = sorted(self.manifest("plan-v3")["claims"])
        first = claims[0]
        self.cli("verdict", "--run", "plan-v3", "--claim-id", first, "--author-role", "refuter",
                 "--result", "undecided", "--why", "need more evidence")
        self.cli("verdict", "--run", "plan-v3", "--claim-id", first, "--author-role", "refuter",
                 "--result", "survives", "--why", "resolved with verifier evidence")
        result = self.cli("verdict", "--run", "plan-v3", "--claim-id", first, "--author-role",
                          "refuter", "--result", "refuted", "--why", "flip attempt", ok=False)
        self.assertIn("immutable", result["error"])
        manifest = self.manifest("plan-v3")
        self.assertEqual(manifest["claims"][first]["status"], "survives")
        self.assertEqual(len(manifest["claims"][first]["verdicts"]), 2)
        for claim_id in claims[1:]:
            self.cli("verdict", "--run", "plan-v3", "--claim-id", claim_id, "--author-role",
                     "refuter", "--result", "survives", "--why", "independent evidence")
        self.assertEqual(self.manifest("plan-v3")["state"], "HARDENED")


if __name__ == "__main__":
    unittest.main()
