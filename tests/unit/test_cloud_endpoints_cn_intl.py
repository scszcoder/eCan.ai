"""
Tests for apps/{cn,intl}/config/cloud_endpoints.json field integrity.

These tests exist to catch the class of bug introduced before this refactor:

  * buckets with the wrong name (e.g. the long-dead ``ecan-intl-files`` /
    ``ecan-cn-files`` names),
  * CN fields misnamed so that storage code silently fell back to a default
    (``backend_storage_region`` vs ``storage_region`` — same name, two
    different namespaces).

For every field that ``utils/storage`` and ``utils/app_config_loader`` read,
we pin the exact expected value per app. If somebody renames a field or
regresses a bucket name to a legacy placeholder, one of these tests fails
with the exact string mismatch.
"""

from pathlib import Path
import pytest

pytestmark = pytest.mark.unit


REPO_ROOT = Path(__file__).resolve().parents[2]
INTL_PATH = REPO_ROOT / "apps" / "intl" / "config" / "cloud_endpoints.json"
CN_PATH = REPO_ROOT / "apps" / "cn" / "config" / "cloud_endpoints.json"


# ---------------------------------------------------------------------------
# Pinned expected values per field per app.
#
# Updating these tables is the correct way to evolve the configuration; if a
# value needs to change for real reasons, the test that catches the change
# forces you to acknowledge it by editing the table here.
# ---------------------------------------------------------------------------
SHARED_FIELDS: dict[str, dict[str, str]] = {
    # key: { app: expected_value }
    #
    # Cloud GraphQL / WS endpoints were removed from this file: they live in
    # auth_config.yml -> APPSYNC.* and are read by agent/cloud_api/endpoints.py.
    # Update the pinned table in tests/unit/test_app_config_loader_endpoints.py
    # instead if those change. The fields kept here are the ones actually
    # consumed by utils/storage/{aws_s3,tencent_cos}.py and agent/cloud/s3_storage_service.py.
    "storage": {
        # Virtual-hosted–style URL the way the rest of the codebase builds
        # them for both backends:
        #   * AWS S3:  https://{bucket}.s3.{region}.amazonaws.com
        #     (matches the pattern in ota/config/ota_config.yaml and docs)
        #   * COS:    https://{bucket}.cos.{region}.myqcloud.com
        #     (matches the pattern in ota/config/loader.py and tests)
        "intl": "https://ecan-skills.s3.us-east-1.amazonaws.com",
        "cn": "https://ecan-skills-1251680599.cos.ap-shanghai.myqcloud.com",
    },
    "storage_region": {
        "intl": "us-east-1",
        "cn": "ap-shanghai",
    },
    "storage_bucket": {
        # Runtime app-storage bucket per app. These names are the canonical
        # ones we aligned with after the refactor — they must NEVER regress
        # to legacy placeholders like ``ecan-intl-files`` / ``ecan-cn-files``.
        "intl": "ecan-skills",
        "cn": "ecan-skills-1251680599",
    },
    "cdn": {
        # Intl cdn.ecan.ai is verified in agent/avatar/README.md:351.
        # CN has no CDN documented anywhere in the repo — the migration plan
        # referenced cdn.ecan.cn as the *pre*-migration value, and nothing
        # replaced it. Leave CN as empty string so callers know to treat it
        # as unconfigured rather than guessing a fastprecisiontech.com CDN
        # that may not exist.
        "intl": "https://cdn.ecan.ai",
        "cn": "",
    },
    "backend_avatar_bucket": {
        "intl": "ecan-avatars",
        "cn": "ecan-avatars-1251680599",
    },
    "backend_skill_bucket": {
        "intl": "ecan-skills",
        "cn": "ecan-skills-1251680599",
    },
    "backend_log_bucket": {
        # The ecan-logs / ecan-logs-APPID bucket is referenced by
        # agent/skill_editor/skill_editor_agent.py but NOT referenced anywhere
        # else in this repo (including Lambda / cloudbase-graphql). It is
        # currently a client-side hardcoded placeholder that has no matching
        # bucket. Leaving the field present (empty) makes the misconfiguration
        # visible: skill_editor_agent reads ECAN_LOG_BUCKET first, falls back
        # to this field, and raises if both are empty.
        "intl": "",
        "cn": "",
    },
    "backend_rag_bucket": {
        "intl": "ecan-rags",
        "cn": "ecan-rags-1251680599",
    },
}

# CN-only fields block removed — the four keys it pinned (vcloudbase_env_id,
# backend_ota_bucket, backend_ota_region, icp_beian) were deleted from
# apps/cn/config/cloud_endpoints.json because production code never reads them.
# CloudBase env id and ICP 备案 live in apps/cn/config/auth_config.yml ->
# CLOUDBASE.ENV_ID and apps/cn/config/app_manifest.json -> legal.icp_beian.
# OTA bucket/region live in ota/config/ota_config.yaml (not this file).


def _load(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


# ===========================================================================
# File-level presence (loading the file yields the expected shape).
# ===========================================================================
class TestFilesLoadCleanly:
    def test_intl_endpoints_loads_as_json(self):
        data = _load(INTL_PATH)
        assert isinstance(data, dict)

    def test_cn_endpoints_loads_as_json(self):
        data = _load(CN_PATH)
        assert isinstance(data, dict)


# ===========================================================================
# Field-by-field equality matrix.
# ===========================================================================
class TestSharedFieldsPerApp:
    """Every shared field must have exactly the pinned value per app.

    Field naming is shared so ``utils/app_config_loader.AppConfigLoader``
    can use one accessor (``graphql_url``, ``storage_url``, ...) for both
    apps. The values are app-specific.
    """

    @pytest.mark.parametrize("field", list(SHARED_FIELDS.keys()))
    def test_intl_field_value(self, field: str):
        data = _load(INTL_PATH)
        assert field in data, f"intl cloud_endpoints.json missing {field!r}"
        assert data[field] == SHARED_FIELDS[field]["intl"], (
            f"intl {field}: expected {SHARED_FIELDS[field]['intl']!r}, "
            f"got {data[field]!r}"
        )

    @pytest.mark.parametrize("field", list(SHARED_FIELDS.keys()))
    def test_cn_field_value(self, field: str):
        data = _load(CN_PATH)
        assert field in data, f"cn cloud_endpoints.json missing {field!r}"
        assert data[field] == SHARED_FIELDS[field]["cn"], (
            f"cn {field}: expected {SHARED_FIELDS[field]['cn']!r}, "
            f"got {data[field]!r}"
        )


# ===========================================================================
# Cross-app sanity checks.
#
# These guard against the bug pattern where the CN and INTL configs are
# swapped, or one app's URL leaks into the other's config file.
# ===========================================================================
class TestNoCrossContamination:
    @pytest.mark.parametrize("field", list(SHARED_FIELDS.keys()))
    def test_cn_does_not_leak_ecan_ai_domain(self, field: str):
        """CN must not have any ecan.ai URLs."""
        data = _load(CN_PATH)
        value = data.get(field, "")
        assert "ecan.ai" not in value, (
            f"cn {field}={value!r} contains an ecan.ai URL — looks like "
            "intl values leaked into cn config"
        )

    @pytest.mark.parametrize("field", list(SHARED_FIELDS.keys()))
    def test_intl_does_not_leak_fastprecisiontech_domain(self, field: str):
        """Intl must not have any fastprecisiontech.com URLs."""
        data = _load(INTL_PATH)
        value = data.get(field, "")
        assert "fastprecisiontech" not in value, (
            f"intl {field}={value!r} contains a fastprecisiontech URL — "
            "looks like cn values leaked into intl config"
        )

    def test_cn_storage_region_is_not_us_east_1(self):
        """CN must never accidentally use the legacy ``us-east-1`` region."""
        data = _load(CN_PATH)
        assert data["storage_region"] != "us-east-1", (
            "cn storage_region regressed to us-east-1"
        )

    def test_intl_storage_region_is_not_ap_shanghai(self):
        """Intl must never accidentally use the CN region."""
        data = _load(INTL_PATH)
        assert data["storage_region"] != "ap-shanghai", (
            "intl storage_region regressed to ap-shanghai (cn region)"
        )

    def test_intl_does_not_use_legacy_ecan_intl_files_bucket(self):
        """The first version of intl cloud_endpoints.json used the
        placeholder ``ecan-intl-files`` bucket. That bug was a real
        incident — guard against a regression."""
        data = _load(INTL_PATH)
        for bucket_field in (
            "storage_bucket",
            "backend_avatar_bucket",
            "backend_skill_bucket",
            "backend_log_bucket",
            "backend_rag_bucket",
        ):
            assert data[bucket_field] != "ecan-intl-files", (
                f"intl {bucket_field} regressed to legacy 'ecan-intl-files'"
            )


# ===========================================================================
# Bucket naming rules for COS (CN side).
#
# COS bucket names are globally unique and must include the APPID suffix,
# otherwise Tencent rejects creation. Pin the rule rather than the value.
# ===========================================================================
class TestCOSBucketNaming:
    @pytest.mark.parametrize(
        "field",
        [
            "backend_avatar_bucket",
            "backend_skill_bucket",
            "backend_log_bucket",
            "backend_rag_bucket",
            "storage_bucket",
        ],
    )
    def test_cn_bucket_name_ends_with_appid(self, field: str):
        data = _load(CN_PATH)
        bucket = data.get(field)
        if not bucket:  # storage_bucket may be left to env var
            pytest.skip(f"{field} not declared on cn side")
        # Tencent Cloud COS bucket names must end with -{APPID}.
        assert bucket.endswith("-1251680599"), (
            f"cn {field}={bucket!r} does not end with -1251680599 APPID"
        )
        assert "-" in bucket, f"cn {field}={bucket!r} has no '-' separator"

    def test_cn_storage_region_is_tencent_supported(self):
        """Only TCB-supported regions for this app."""
        data = _load(CN_PATH)
        assert data["storage_region"] in {"ap-shanghai", "ap-guangzhou", "ap-beijing"}


# ===========================================================================
# S3 (Intl) naming rules.
# ===========================================================================
class TestS3BucketNaming:
    @pytest.mark.parametrize(
        "field",
        ["storage_bucket", "backend_avatar_bucket", "backend_skill_bucket",
         "backend_log_bucket", "backend_rag_bucket"],
    )
    def test_intl_bucket_does_not_have_appid_suffix(self, field: str):
        """S3 buckets don't need APPID-suffix; an APPID suffix on intl means
        somebody copy-pasted from CN."""
        data = _load(INTL_PATH)
        bucket = data.get(field, "")
        assert "-1251680599" not in bucket, (
            f"intl {field}={bucket!r} contains CN APPID suffix -1251680599"
        )

    def test_intl_storage_region_is_aws_supported(self):
        data = _load(INTL_PATH)
        # The team uses us-east-1 historically; allow a small well-known set.
        assert data["storage_region"] in {"us-east-1", "us-west-2", "eu-west-1"}


# ===========================================================================
# Structural invariants.
# ===========================================================================
class TestStructuralInvariants:
    def test_intl_has_no_unexpected_fields(self):
        """Intl cloud_endpoints.json must only contain fields that production
        code (utils/storage, s3_storage_service) reads. Anything else is
        either dead config or a leak from a CN-only field. This is the
        reverse of the original ``test_intl_has_no_cn_only_field``: instead
        of pinning a deny-list of CN-only keys, we pin the exact allow-list
        of fields each app declares, so any future stray addition surfaces
        immediately.
        """
        data = _load(INTL_PATH)
        allowed = set(SHARED_FIELDS.keys())  # same shape as CN
        extras = set(data.keys()) - allowed - {k for k in data if k.startswith("_")}
        assert not extras, (
            f"intl cloud_endpoints.json has unexpected fields: {sorted(extras)}"
        )

    def test_cn_has_no_unexpected_fields(self):
        data = _load(CN_PATH)
        allowed = set(SHARED_FIELDS.keys())  # CN shares the field set with Intl
        extras = set(data.keys()) - allowed - {k for k in data if k.startswith("_")}
        assert not extras, (
            f"cn cloud_endpoints.json has unexpected fields: {sorted(extras)}"
        )

    # Fields that are allowed to be declared as an empty string. These are
    # fields that may legitimately be unconfigured in some deployment (e.g.
    # the company has not set up a CDN yet, or the log bucket is not
    # provisioned on this app). Anything else with an empty value is the
    # silent-misconfiguration class the no-fallback refactor caught.
    ALLOW_EMPTY = {"cdn", "backend_log_bucket"}

    def test_no_empty_string_field(self):
        """Most fields MUST NOT be empty — that was the silent
        misconfiguration the no-fallback refactor was supposed to catch.
        See ALLOW_EMPTY for documented exceptions.
        """
        import json
        for path, label in ((INTL_PATH, "intl"), (CN_PATH, "cn")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for k, v in data.items():
                if k.startswith("_"):
                    continue  # comments
                if k in self.ALLOW_EMPTY:
                    continue  # documented "may be empty" fields
                assert v != "", (
                    f"{label} cloud_endpoints.json has empty value for {k!r}"
                )

    def test_cdn_is_https_when_set(self):
        """If a CDN URL is declared, it must be HTTPS — cleartext CDN is
        not something we ever want to deploy by accident."""
        import json
        for path, label in ((INTL_PATH, "intl"), (CN_PATH, "cn")):
            data = json.loads(path.read_text(encoding="utf-8"))
            cdn = data.get("cdn", "")
            if cdn:
                assert cdn.startswith("https://"), (
                    f"{label} cdn={cdn!r} is not an https URL"
                )

    def test_storage_bucket_differs_from_avatar_bucket_intl(self):
        """The avatar and storage buckets must be distinct. If they collapse
        to the same name, IAM policies collide and uploads land on the wrong
        key prefix."""
        data = _load(INTL_PATH)
        assert data["storage_bucket"] != data["backend_avatar_bucket"], (
            "intl storage_bucket and backend_avatar_bucket collapsed to "
            "the same bucket"
        )

    def test_storage_bucket_differs_from_avatar_bucket_cn(self):
        data = _load(CN_PATH)
        assert data["storage_bucket"] != data["backend_avatar_bucket"], (
            "cn storage_bucket and backend_avatar_bucket collapsed to "
            "the same bucket"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
