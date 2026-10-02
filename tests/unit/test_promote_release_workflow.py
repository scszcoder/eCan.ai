"""Structure tests for the rollout release workflow surface.

Pins the contract between the three workflow files that gate OTA
publishing, so a refactor can't silently remove a guard:

  * ``release-{cn,intl}.yml``: the ``publish`` input gates the four
    jobs that write to ``channels/`` (appcast, latest.json,
    download-links, smoke) — both files must carry the same gate.
  * ``promote-release.yml``: the go-live button. Guard-before-write
    ordering (resolve -> feeds -> apply -> smoke) is the invariant
    that keeps a failed guard from leaving the appcast and the rollout
    file disagreeing.
  * ``ota-status.yml``: read-only by construction (``--status``,
    never ``--apply``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    doc = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # YAML 1.1 parses the unquoted `on:` key as boolean True.
    doc["_on"] = doc.get("on") or doc.get(True) or {}
    return doc


def _step(workflow: dict, job: str, name_prefix: str) -> dict:
    for step in workflow["jobs"][job]["steps"]:
        if str(step.get("name", "")).startswith(name_prefix):
            return step
    raise AssertionError(f"step starting with {name_prefix!r} not found in {job}")


# ---------------------------------------------------------------------------
# release-{cn,intl}.yml — publish gate
# ---------------------------------------------------------------------------

RELEASE_GATED_JOBS = [
    "generate-appcast",
    "generate-latest-json",
    "generate-download-links",
    "smoke-test-ota",
]


@pytest.mark.parametrize("name", ["release-cn.yml", "release-intl.yml"])
class TestReleasePublishGate:
    def test_publish_input_is_boolean_default_false(self, name):
        wf = _load(name)
        publish = wf["_on"]["workflow_dispatch"]["inputs"]["publish"]
        assert publish["type"] == "boolean"
        assert publish["default"] is False

    @pytest.mark.parametrize("job", RELEASE_GATED_JOBS)
    def test_job_if_requires_publish(self, name, job):
        wf = _load(name)
        cond = str(wf["jobs"][job]["if"])
        assert "inputs.publish == true" in cond, (
            f"{name}:{job} lost its publish gate — with publish=false the "
            "job would rewrite channels/ and ship an unreviewed release"
        )

    def test_build_and_upload_jobs_not_gated(self, name):
        # Builds and uploads must still run with publish=false — the
        # whole point is build-now / go-live-later.
        wf = _load(name)
        gated_only = {"generate-appcast", "generate-latest-json",
                      "generate-download-links", "smoke-test-ota"}
        for job_id, job in wf["jobs"].items():
            cond = job.get("if")
            if cond is None:
                continue
            mentions = "inputs.publish" in str(cond)
            if job_id in gated_only:
                assert mentions, f"{name}:{job_id} lost the publish gate"
            else:
                assert not mentions, (
                    f"{name}:{job_id} must not depend on publish"
                )

    def test_final_status_reports_publish(self, name):
        wf = _load(name)
        env = _step(wf, "final-status", "Show summary")["env"]
        assert "PUBLISH" in env
        assert "inputs.publish" in str(env["PUBLISH"])


# ---------------------------------------------------------------------------
# promote-release.yml — the go-live button
# ---------------------------------------------------------------------------

class TestPromoteReleaseWorkflow:
    @pytest.fixture(scope="class")
    def wf(self):
        return _load("promote-release.yml")

    def test_inputs_surface_the_whole_action_space(self, wf):
        inputs = wf["_on"]["workflow_dispatch"]["inputs"]
        assert inputs["app"]["options"] == ["cn", "intl"]
        assert inputs["action"]["options"] == [
            "promote", "ramp", "reduce", "pause", "resume", "rollback",
        ]
        assert inputs["environment"]["options"] == [
            "production", "staging", "test",
        ]
        assert inputs["channel"]["options"] == ["stable", "beta", "dev"]
        assert inputs["percent"]["default"] == "100"  # fully open default
        assert "100" in inputs["percent"]["options"]

    def test_serialised_per_target_channel(self, wf):
        conc = wf["concurrency"]
        assert "promote-ota-" in conc["group"]
        assert conc["cancel-in-progress"] is False

    def test_job_binds_github_environment(self, wf):
        # environment-scoped secrets + optional required-reviewers gate.
        assert wf["jobs"]["promote"]["environment"] == "${{ inputs.environment }}"

    def test_step_order_guard_apply_before_feeds_before_smoke(self, wf):
        names = [str(s.get("name", "")) for s in wf["jobs"]["promote"]["steps"]]
        def pos(prefix):
            return next(i for i, n in enumerate(names) if n.startswith(prefix))
        resolve = pos("Resolve and guard")
        apply = pos("Apply rollout control")
        appcast = pos("Regenerate appcast")
        latest = pos("Regenerate latest.json")
        smoke = pos("Smoke-test published endpoints")
        # Guard first: a violated guard must fail before any bucket
        # write. Control plane before feeds: the rollout gate must be
        # in place before the feed rewrite exposes the new version, so
        # an Apply failure means nothing has changed at all. Smoke
        # last: verify after publishing.
        assert resolve < apply < appcast < latest < smoke

    def test_resolve_exports_workflow_outputs(self, wf):
        run = _step(wf, "promote", "Resolve and guard")["run"]
        for key in ("target=", "publish=", "smoke=", "exclude="):
            assert key in run
        assert "$GITHUB_OUTPUT" in run
        # percent only flows for percent-moving actions (pause/resume
        # must not emit "ignores --percent" noise).
        assert "promote|ramp|reduce" in run

    def test_feed_exclusions_flow_from_resolve_output(self, wf):
        # Feed regeneration consumes the UNION (manual input merged
        # with the version rollback auto-derived) computed by
        # set_rollout.py during resolve — not the raw input.
        for name in ("Regenerate appcast", "Regenerate latest.json"):
            env = _step(wf, "promote", name)["env"]
            assert env["EXCLUDE"] == "${{ steps.resolve.outputs.exclude }}"
        # Resolve/apply take the raw input and do the merging.
        for name in ("Resolve and guard", "Apply rollout control"):
            env = _step(wf, "promote", name)["env"]
            assert env["EXCLUDE"] == "${{ inputs.exclude }}"
            assert '--exclude "$EXCLUDE"' in _step(wf, "promote", name)["run"]

    def test_feed_regeneration_only_when_publishing(self, wf):
        for name in ("Regenerate appcast", "Regenerate latest.json"):
            step = _step(wf, "promote", name)
            assert step["if"] == "steps.resolve.outputs.publish == 'true'"

    def test_apply_is_the_only_write_step(self, wf):
        runs = [str(s.get("run", "")) for s in wf["jobs"]["promote"]["steps"]]
        writers = [r for r in runs if "set_rollout.py" in r and "--apply" in r]
        assert len(writers) == 1
        # Both write paths append to the step summary (free status page).
        apply_run = _step(wf, "promote", "Apply rollout control")["run"]
        assert "--summary" in apply_run and "$GITHUB_STEP_SUMMARY" in apply_run

    def test_smoke_runs_only_after_feed_rewrite(self, wf):
        step = _step(wf, "promote", "Smoke-test published endpoints")
        assert step["if"] == "steps.resolve.outputs.smoke == 'true'"
        assert "smoke_test_ota.py" in step["run"]
        assert "--version \"$TARGET\"" in step["run"]

    def test_creds_passed_to_every_bucket_touching_step(self, wf):
        for step in wf["jobs"]["promote"]["steps"]:
            if "run" not in step:
                continue
            env = step.get("env", {})
            runs_bucket_code = any(
                token in step["run"]
                for token in ("set_rollout.py", "generate_appcast.py",
                              "generate_latest_json.py", "smoke_test_ota.py")
            )
            if runs_bucket_code:
                assert "AWS_ACCESS_KEY_ID" in env, step.get("name")
                assert "ECAN_TENCENT_SECRET_ID" in env, step.get("name")


# ---------------------------------------------------------------------------
# ota-status.yml — read-only
# ---------------------------------------------------------------------------

class TestOtaStatusWorkflow:
    @pytest.fixture(scope="class")
    def wf(self):
        return _load("ota-status.yml")

    def test_status_mode_only_never_applies(self, wf):
        runs = [str(s.get("run", "")) for s in wf["jobs"]["status"]["steps"]]
        status_runs = [r for r in runs if "set_rollout.py" in r]
        assert len(status_runs) == 1
        assert "--status" in status_runs[0]
        assert "--apply" not in status_runs[0]
        assert "--action" not in status_runs[0]

    def test_same_selector_surface_as_promote(self, wf):
        inputs = wf["_on"]["workflow_dispatch"]["inputs"]
        assert inputs["app"]["options"] == ["cn", "intl"]
        assert inputs["environment"]["options"] == [
            "production", "staging", "test",
        ]
        assert inputs["channel"]["options"] == ["stable", "beta", "dev"]

    def test_summary_written(self, wf):
        run = _step(wf, "status", "Read rollout status")["run"]
        assert "--summary" in run and "$GITHUB_STEP_SUMMARY" in run
