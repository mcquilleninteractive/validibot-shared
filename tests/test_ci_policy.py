"""Security contracts for branch-protection-facing GitHub Actions checks.

The protected branch requires the aggregate ``ci`` check rather than every
matrix child by name. These tests ensure that aggregate always runs and fails
unless each security, test, and dependency prerequisite succeeded.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_required_ci_aggregate_fails_closed():
    """A failed or cancelled prerequisite must make the required check fail."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    aggregate = workflow.split("\n  ci:\n", maxsplit=1)[1]

    assert "if: always()" in aggregate
    assert "needs: [security, test, deps]" in aggregate
    for prerequisite in ("security", "test", "deps"):
        result_variable = f"${{{{ needs.{prerequisite}.result }}}}"
        assert result_variable in aggregate
    for environment_variable in ("SECURITY_RESULT", "TEST_RESULT", "DEPS_RESULT"):
        assert f'test "${environment_variable}" = "success"' in aggregate
    assert 'echo "All checks passed."' not in aggregate
