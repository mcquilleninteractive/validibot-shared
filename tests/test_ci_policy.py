"""Security contracts for branch-protection-facing GitHub Actions checks.

The protected branch requires the aggregate ``ci`` check rather than every
matrix child by name. These tests ensure the aggregate fails closed across
secret scanning, SAST, tests, and dependency auditing, and that security tools
are installed only from the repository's reviewed lockfile.
"""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"
UV_LOCK = REPO_ROOT / "uv.lock"
JUSTFILE = REPO_ROOT / "justfile"

FULL_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


def test_required_ci_aggregate_fails_closed() -> None:
    """A failed or cancelled prerequisite must make the required check fail."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    aggregate = workflow.split("\n  ci:\n", maxsplit=1)[1]

    assert "if: always()" in aggregate
    assert "needs: [security, codeql, test, deps]" in aggregate
    for prerequisite in ("security", "codeql", "test", "deps"):
        result_variable = f"${{{{ needs.{prerequisite}.result }}}}"
        assert result_variable in aggregate
    for environment_variable in (
        "SECURITY_RESULT",
        "CODEQL_RESULT",
        "TEST_RESULT",
        "DEPS_RESULT",
    ):
        assert f'test "${environment_variable}" = "success"' in aggregate
    assert 'echo "All checks passed."' not in aggregate


def test_secret_scanners_run_from_the_frozen_dependency_environment() -> None:
    """Secret scanning must not bypass the reviewed hashes in ``uv.lock``."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    security_job = workflow.split("\n  security:\n", maxsplit=1)[1].split(
        "\n  codeql:\n", maxsplit=1
    )[0]
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    lockfile = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))

    setup_uv_refs = re.findall(r"astral-sh/setup-uv@([^\s#]+)", security_job)
    assert len(setup_uv_refs) == 1
    assert FULL_COMMIT_SHA.fullmatch(setup_uv_refs[0])
    assert "uv python install 3.13" in security_job
    assert "uv sync --frozen --extra dev --python 3.13" in security_job
    assert security_job.count("uv run --frozen --extra dev --python 3.13") == 2
    assert "pip install" not in workflow

    dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]
    pre_commit_pins = [
        dependency
        for dependency in dev_dependencies
        if dependency.startswith("pre-commit==")
    ]
    assert len(pre_commit_pins) == 1
    pinned_version = pre_commit_pins[0].partition("==")[2]
    assert pinned_version

    locked_versions = [
        package["version"]
        for package in lockfile["package"]
        if package["name"] == "pre-commit"
    ]
    assert locked_versions == [pinned_version]


def test_codeql_scans_python_as_a_required_ci_prerequisite() -> None:
    """Every integrated change must receive SAST before ``ci`` can succeed."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    codeql_job = workflow.split("\n  codeql:\n", maxsplit=1)[1].split(
        "\n  test:\n", maxsplit=1
    )[0]

    assert "actions: read" in codeql_job
    assert "contents: read" in codeql_job
    assert "security-events: write" in codeql_job
    assert "persist-credentials: false" in codeql_job
    codeql_refs = re.findall(
        r"github/codeql-action/(init|analyze)@([^\s#]+)", codeql_job
    )
    assert len(codeql_refs) == 2
    assert {action for action, _reference in codeql_refs} == {"init", "analyze"}
    assert all(
        FULL_COMMIT_SHA.fullmatch(reference) for _action, reference in codeql_refs
    )
    assert len({reference for _action, reference in codeql_refs}) == 1
    assert "languages: python" in codeql_job
    assert "build-mode: none" in codeql_job


def test_local_commands_use_the_frozen_development_environment() -> None:
    """Fresh-checkout checks must not depend on ambient tools or rewrite the lock."""
    justfile = JUSTFILE.read_text(encoding="utf-8")

    assert "uv run --frozen --extra dev python -m pytest" in justfile
    assert "uv run --frozen --extra dev ruff check ." in justfile
    assert "uv run --frozen --extra dev ruff format --check ." in justfile
    assert "check: lock-check format-check lint test" in justfile
    assert "uv lock --check" in justfile


def test_release_requires_locked_audit_and_exact_commit_ci() -> None:
    """A direct push must not become releasable before its own CI succeeds."""
    justfile = JUSTFILE.read_text(encoding="utf-8")

    assert "release-check: check audit _require-release-ci" in justfile
    assert "--workflow ci.yml" in justfile
    assert '--commit "$HEAD_SHA"' in justfile
    assert "--event push" in justfile
    assert 'gh run watch "$RUN_ID"' in justfile
    assert "just release-check" in justfile
    assert "Release checks changed the working tree" in justfile
