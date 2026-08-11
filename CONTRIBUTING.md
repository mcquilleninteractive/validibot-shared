# Contributing to Validibot Shared

Thank you for your interest in contributing! This document covers the process
for contributing to `validibot-shared`.

## License Agreement

By submitting a pull request, you agree that your contributions are licensed
under the [MIT License](LICENSE), the same license that covers this project.
You confirm that you have the right to grant this license for your contributions.

## Getting Started

1. Fork the repository
2. Clone your fork and create a feature branch
3. Install dependencies: `uv sync --extra dev`
4. Make your changes
5. Run checks (see below)
6. Submit a pull request

## Development Setup

```bash
# Install dependencies
uv sync --extra dev

# Run the deterministic suite, including bounded security properties
just test

# Run linter
uv run ruff check .

# Run type checker
uv run mypy src/
```

## Pull Request Guidelines

- Keep changes focused — one feature or fix per PR
- Include tests for new or modified models
- Ensure all checks pass before submitting
- Write a clear PR description explaining the "why" behind the change

## Security Property Tests

The Hypothesis suite exercises the canonical JSON, callback nonce, envelope,
file-port, and SVRL contracts with bounded generated inputs. CI selects the
`ci` profile (75 examples per property with a 500 ms per-example deadline).
Run the same profile locally when reproducing CI:

```bash
HYPOTHESIS_PROFILE=ci just test tests/test_security_properties.py
```

Rejected malformed inputs are expected outcomes when they raise the public
contract's documented exceptions. Unexpected exceptions, hangs, resource
exhaustion, or broken invariants are bugs. When Hypothesis minimizes a genuine
bug, add a named regression test explaining the security impact rather than
committing an unreviewed generated corpus.

## Adding a New Validator Schema

If you're adding envelope models for a new validator type:

1. Create a new directory under `validibot_shared/` (e.g., `validibot_shared/myvalidator/`)
2. Define your input/output models in `models.py`
3. Create typed envelope subclasses in `envelopes.py`
4. Add tests under `tests/`

See the existing `energyplus/` and `fmu/` directories for examples.

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and
formatting. Run `uv run ruff check . --fix` to auto-fix issues and
`uv run ruff format .` to format code.

## Reporting Issues

- **Bugs and feature requests:** [GitHub Issues](https://github.com/danielmcquillen/validibot-shared/issues)
- **Security vulnerabilities:** See [SECURITY.md](SECURITY.md) — do not open a public issue
