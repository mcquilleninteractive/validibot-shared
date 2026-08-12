# Releasing validibot-shared

Releases use a signed tag, GitHub Actions, and PyPI trusted publishing. No
maintainer should upload a distribution from a workstation or store a PyPI API
token in GitHub.

## Release guarantees

For every release, the workflow:

1. checks out the exact GitHub Release tag and verifies its SSH signature
   against the repository's `.allowed_signers` trust policy from protected
   `main`;
2. requires an exact `vX.Y.Z` tag matching the version in `pyproject.toml`;
3. requires the tag commit to be reachable from protected `main`;
4. recreates the locked dependency environment and builds one wheel and one
   source distribution;
5. validates both distributions with Twine;
6. generates CycloneDX JSON and XML SBOMs and portable SHA-256 checksums;
7. creates a GitHub SBOM attestation covering both distributions;
8. attaches the distributions, SBOMs, and checksums to the GitHub Release; and
9. publishes the same distributions through PyPI OIDC trusted publishing,
   which creates PyPI provenance attestations.

The `pypi` GitHub environment must be restricted to `v*` tags with
administrator bypass disabled. Publishing is release-only: there is no
manual-dispatch or TestPyPI route in the production workflow.

GitHub repository settings must also have immutable releases enabled before a
new release is cut. This setting applies only to future releases, so it cannot
retrofit immutability onto an existing release such as 0.28.0. Only the
maintainer changes this account-level control; verify it under repository
Settings → Releases as part of release readiness.

Signed commits are intentionally not required in this public repository.
Protected `main`, required pull requests, and required CI govern source
integration. Release signing is a separate boundary: every published release
still requires a signed tag verified against the `.allowed_signers` policy
loaded from protected `main`.

## Integration guarantees

The required `ci` check is a fail-closed aggregate. On every pull request and
every push to `main`, it succeeds only after all of these jobs succeed:

1. private-key and tracked-file secret scanning, with `pre-commit` installed
   from the hash-locked `uv.lock` environment rather than directly from PyPI;
2. CodeQL static analysis of the Python source;
3. linting, formatting, and tests on every supported Python version; and
4. lockfile consistency and known-vulnerability auditing.

The CodeQL job receives only read access to Actions and repository contents,
plus the `security-events: write` permission needed to publish its analysis.
All third-party actions in the workflow are pinned to full commit SHAs.

## Maintainer procedure

1. Update `pyproject.toml`, `uv.lock`, and `CHANGELOG.md` in a pull request.
2. Merge the pull request after the required `ci` check passes.
3. Update local `main`, then run:

   ```console
   just release X.Y.Z
   ```

The recipe refuses dirty trees, non-`main` branches, and a local branch that
does not exactly match `origin/main`. It runs `just release-check`, which
combines the frozen local gate, an explicit locked-runtime dependency audit,
and the successful `ci.yml` push run for the exact release commit. It then
confirms the checks left the worktree clean, creates and locally verifies a
signed tag, pushes that tag, and publishes the GitHub Release.

Run `just release-check` alone to inspect every prerequisite without creating a
tag. `just check` is the deterministic subset: lock consistency, formatting,
linting, and tests. `just audit` is separate because it queries the live
vulnerability advisory service.

Do not move or replace a published version tag. If a release workflow fails
because its committed release code is defective, fix the pipeline and publish
the next patch version.

## Consumer verification

Verify a checked-out tag:

```console
git fetch origin main --tags
git show origin/main:.allowed_signers > /tmp/validibot-shared-allowed-signers
git -c gpg.format=ssh \
  -c gpg.ssh.allowedSignersFile=/tmp/validibot-shared-allowed-signers \
  verify-tag vX.Y.Z
```

The signer policy must come from a trusted source rather than from the tag
being verified. Protected `main` is the workflow's trust anchor; consumers
with stricter requirements can pin and distribute that public signer policy
out of band.

Download the GitHub Release assets into one directory and verify the portable
checksums:

```console
gh release download vX.Y.Z \
  --repo mcquilleninteractive/validibot-shared \
  --dir release-assets
cd release-assets
sha256sum --check SHA256SUMS
```

Version `0.21.0` predates the immutable release bundle. Its GitHub Release
contains only the JSON and XML SBOMs; verify its wheel and source distribution
through their PyPI provenance attestations instead.

Verify the GitHub-hosted SBOM attestation for a downloaded wheel:

```console
gh attestation verify validibot_shared-X.Y.Z-py3-none-any.whl \
  --repo mcquilleninteractive/validibot-shared \
  --predicate-type https://cyclonedx.org/bom
```

To verify PyPI provenance, copy the wheel's direct download URL from PyPI and
run:

```console
uvx --from pypi-attestations pypi-attestations verify pypi \
  --repository https://github.com/mcquilleninteractive/validibot-shared \
  https://files.pythonhosted.org/.../validibot_shared-X.Y.Z-py3-none-any.whl
```
