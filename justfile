# Validibot Shared Library development commands

# Default recipe - show available commands
default:
    @just --list

# Run tests
test:
    uv run python -m pytest

# Run tests with verbose output
test-v:
    uv run python -m pytest -v

# Run tests with coverage
test-cov:
    uv run python -m pytest --cov=validibot_shared

# Lint code
lint:
    uv run ruff check .
    uv run ruff format --check .

# Format code
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# Run all checks (lint, test)
check: lint test

# Build the package
build:
    uv build

# Clean build artifacts
clean:
    rm -rf dist/ build/ *.egg-info/ validibot_shared.egg-info/ sv_shared.egg-info/ vb_shared.egg-info/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Release a new version (signed tag + GitHub release → verified PyPI publish)
# Usage: just release 0.21.1
release VERSION:
    #!/usr/bin/env bash
    set -euo pipefail

    if [[ ! "{{VERSION}}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Error: Version must be in format X.Y.Z (e.g., 0.21.1)"
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
    just check
    uv lock --check
    RELEASE_CHECK_DIR="$(mktemp -d)"
    trap 'rm -rf "$RELEASE_CHECK_DIR"' EXIT
    uv build --no-sources --out-dir "$RELEASE_CHECK_DIR"
    uvx --from twine==7.0.0 twine check --strict "$RELEASE_CHECK_DIR"/*

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
