# Validibot Shared Library development commands

# Default recipe - show available commands
default:
    @just --list

# Run all tests, or pass pytest paths/options to scope the run
test *args:
    uv run --frozen --extra dev python -m pytest {{args}}

# Run tests with verbose output, optionally scoped by pytest arguments
test-v *args:
    uv run --frozen --extra dev python -m pytest -v {{args}}

# Run tests with coverage
test-cov:
    uv run --frozen --extra dev python -m pytest --cov=validibot_shared

# Lint code
lint:
    uv run --frozen --extra dev ruff check .

# Verify formatting without changing files
format-check:
    uv run --frozen --extra dev ruff format --check .

# Format code
format:
    uv run --frozen --extra dev ruff format .
    uv run --frozen --extra dev ruff check --fix .

# Backwards-compatible alias for the former formatter name
fmt: format

# Verify pyproject.toml and uv.lock describe the same dependency graph
lock-check:
    uv lock --check

# Audit the exact locked runtime dependency set
audit:
    #!/usr/bin/env bash
    set -euo pipefail
    REQUIREMENTS_FILE="$(mktemp)"
    trap 'rm -f "$REQUIREMENTS_FILE"' EXIT
    uv export --frozen --no-emit-project \
        --quiet \
        --format requirements-txt \
        --output-file "$REQUIREMENTS_FILE"
    uvx --from pip-audit==2.10.1 pip-audit \
        --requirement "$REQUIREMENTS_FILE" \
        --no-deps \
        --disable-pip \
        --strict

# Run the deterministic local integration gate
check: lock-check format-check lint test

# Require the exact main-branch commit to have a successful CI workflow.
_require-release-ci:
    #!/usr/bin/env bash
    set -euo pipefail

    gh auth status >/dev/null
    REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
    HEAD_SHA="$(git rev-parse HEAD)"
    RUN_INFO="$(
        gh run list \
            --repo "$REPO" \
            --workflow ci.yml \
            --branch main \
            --commit "$HEAD_SHA" \
            --event push \
            --limit 1 \
            --json databaseId,status,conclusion,url \
            --jq 'if length == 0 then "" else .[0] | "\(.databaseId)|\(.status)|\(.conclusion // "")|\(.url)" end'
    )"

    if [[ -z "$RUN_INFO" ]]; then
        echo "Error: No main-branch CI run exists for $HEAD_SHA."
        echo "Push main and wait for CI before releasing."
        exit 1
    fi

    IFS='|' read -r RUN_ID RUN_STATUS RUN_CONCLUSION RUN_URL <<< "$RUN_INFO"
    if [[ "$RUN_STATUS" != "completed" ]]; then
        echo "Waiting for CI run $RUN_ID to finish: $RUN_URL"
        gh run watch "$RUN_ID" --repo "$REPO" --exit-status
    elif [[ "$RUN_CONCLUSION" != "success" ]]; then
        echo "Error: CI did not succeed for $HEAD_SHA: $RUN_URL"
        exit 1
    fi

    echo "CI succeeded for $HEAD_SHA: $RUN_URL"

# Run every local and remote release prerequisite without creating a tag
release-check: check audit _require-release-ci

# Build the package
build:
    uv build

# Clean build artifacts
clean:
    rm -rf dist/ build/ *.egg-info/ validibot_shared.egg-info/ sv_shared.egg-info/ vb_shared.egg-info/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Release a new version (signed tag + GitHub release → verified PyPI publish)
# Usage: just release 0.22.0
release VERSION:
    #!/usr/bin/env bash
    set -euo pipefail

    if [[ ! "{{VERSION}}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Error: Version must be in format X.Y.Z (e.g., 0.22.0)"
        exit 1
    fi

    if [[ -n $(git status --porcelain) ]]; then
        echo "Error: You have uncommitted changes. Commit or stash them first."
        exit 1
    fi

    BRANCH="$(git branch --show-current)"
    if [[ "$BRANCH" != "main" ]]; then
        echo "Error: Releases must be created from main, not '$BRANCH'."
        exit 1
    fi

    git fetch origin main
    LOCAL_COMMIT="$(git rev-parse HEAD)"
    REMOTE_COMMIT="$(git rev-parse origin/main)"
    if [[ "$LOCAL_COMMIT" != "$REMOTE_COMMIT" ]]; then
        echo "Error: Local main must exactly match origin/main."
        exit 1
    fi

    TOML_VERSION="$(python3 -c \
        'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')"
    if [[ "$TOML_VERSION" != "{{VERSION}}" ]]; then
        echo "Error: Version in pyproject.toml ($TOML_VERSION) doesn't match {{VERSION}}"
        exit 1
    fi

    TAG="v{{VERSION}}"
    if git rev-parse "$TAG" >/dev/null 2>&1; then
        echo "Error: Tag $TAG already exists."
        exit 1
    fi

    echo "Running the full release gate..."
    just release-check
    RELEASE_CHECK_DIR="$(mktemp -d)"
    trap 'rm -rf "$RELEASE_CHECK_DIR"' EXIT
    uv build --no-sources --out-dir "$RELEASE_CHECK_DIR"
    uvx --from twine==7.0.0 twine check --strict "$RELEASE_CHECK_DIR"/*

    if [[ -n $(git status --porcelain) ]]; then
        echo "Error: Release checks changed the working tree. Review and commit those changes first."
        git status --short
        exit 1
    fi

    echo "Creating and verifying signed tag $TAG..."
    git tag -s -m "Release $TAG" "$TAG"
    git verify-tag "$TAG"
    git push origin "$TAG"

    gh release create "$TAG" \
        --verify-tag \
        --title "$TAG" \
        --generate-notes

    echo ""
    echo "Release $TAG created from signed tag $LOCAL_COMMIT."
    echo "GitHub Actions will verify it again, attest it, and publish to PyPI."
    echo "Monitor: gh run list --limit 3"
