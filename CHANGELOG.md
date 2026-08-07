# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.25.0] - 2026-08-07

### Added

- Add the generic PDF package validator envelope, exact payload selectors,
  bounded parser policy, and canonical `validibot.pdf_inventory.v1` models.
- Add PDF, STEP Part 21, and related MIME identities used by typed PDF package
  inputs and extracted outputs.

### Notes

- The application and validator-backends repositories must upgrade together;
  PDF is a new typed advanced-validator boundary.

## [0.24.0] - 2026-08-03

### Added

- Extend the EnergyPlus input contract with typed review checks, full versus
  preflight execution, and standard/LEED-readiness review profiles.
- Add EnergyPlus binary, IDD, model-version, completion, issue-count, and
  artifact-availability evidence to the typed output contract.
- Add an aggregate for uncommon GJ-valued site fuels so modeled site EUI and
  total-site-energy derivations can account for every applicable fuel column.

### Changed

- Preserve unavailable EnergyPlus review metrics as explicit nullable fields in
  the strict shared contract.

## [0.23.0] - 2026-07-30

### Added

- Separate the three Portfolio Manager floor-area columns on
  `PortfolioManagerPropertyResult`. `gross_floor_area_ft2` now always carries
  the parking-excluded quantity matching EPA's gross floor area definition and
  Washington CBPS's Form B basis. `gross_floor_area_buildings_and_parking_ft2`
  and `parking_floor_area_ft2` retain the other two columns, and
  `gross_floor_area_basis` records which one backs the canonical value.

### Changed

- Replace the evidence manifest with a strict v2 permanent receipt containing
  only run outcome, workflow-step identity, the optional per-step backend image
  digest, and input/output digests. Runtime lineage, workflow configuration,
  retention metadata, and provider details are no longer part of the manifest.
- Portfolio Manager reports carrying both a parking-excluded and a
  parking-inclusive floor-area column now resolve deterministically to the
  parking-excluded value instead of depending on column or metric order.

## [0.22.0] - 2026-07-29

### Changed

- Move the canonical repository to the `mcquilleninteractive` organization.
- Raise the minimum supported Python version to 3.13 and add Python 3.14 to
  the tested compatibility matrix.
- Harden releases with protected-main tag ancestry, signed-tag and version
  verification, a single immutable distribution bundle, portable SHA-256
  checksums, CycloneDX SBOMs, GitHub artifact attestations, and PyPI trusted
  publishing provenance.
- Add an aggregate CI gate, exact lockfile vulnerability auditing, and OpenSSF
  Scorecard analysis.

## [0.21.0] - 2026-07-27

### Added

- Extend the strict `validibot.evidence.v1` manifest so execution-attempt records
  identify the semantic Validator contract, independent backend release,
  source tag and release-record digest, image, provider configuration, and
  runtime identity.

### Changed

- Make Portfolio Manager workflow policy entirely explicit by removing the
  unversioned profile shortcut from its input and output contracts. Workflow
  authors now control every readiness, reporting-period, target, and
  data-quality setting independently.

### Notes

- Consumers must update their package pin and lockfile before using these
  coordinated contract changes.
- Validibot has no external evidence consumers before launch, so the new fields
  extend the single current schema rather than adding parallel compatibility
  readers. Managed-release fields remain optional as a group but are validated
  as a complete identity whenever any member is present.

## [0.20.0] - 2026-07-23

### Added

- Add the strict Portfolio Manager input/output envelope, canonical
  per-property facts, domain findings, and bounded collection aggregates.
- Add the versioned Expected Buildings List contract, duplicate-key and
  semantic validation, defensive JSON bounds, and a published JSON Schema.
- Add XLS, XLSX, XML, ZIP, and JSON MIME identities used by the new backend.

### Notes

- The application and validator-backends repositories must upgrade together;
  Portfolio Manager is a new typed advanced-validator boundary.

## [0.19.0] - 2026-07-20

### Added

- Add immutable execution deployment ID, provider kind, provider revision, and
  canonical provider resource to each execution-attempt evidence record.

### Notes

- Additive change: existing `validibot.evidence.v1` manifests remain valid.
  New producers can prove the exact Cloud Run Service or Job deployment used
  without exposing routes, credentials, or storage URIs.

## [0.18.0] - 2026-07-18

### Added

- Add URI-free execution-attempt evidence records that bind canonical input
  and output envelope digests, provider identity, backend image digest, strict
  input file identities, and explicit source-to-executed transformations.
- Add immutable storage versions to produced-artifact and consumed-artifact
  evidence projections.

### Changed

- Clarify that `payload_digests.input_sha256` identifies the submission bytes
  accepted by the producer and does not, by itself, claim those bytes crossed
  the validator execution boundary unchanged.

### Notes

- Additive change: the evidence schema string stays `validibot.evidence.v1`.
  Older manifests remain valid, while newer producers populate the
  default-empty `execution_attempts` collection.

## [0.17.0] - 2026-07-17

### Changed (BREAKING)

- Advance the strict execution contract to `validibot.attempt.v2`.
- Require enabled asynchronous callbacks to carry an attempt-bound callback
  ID, raw nonce, and matching public nonce commitment.
- Require callback payloads to return the raw nonce so Django can authenticate
  the sender against its per-attempt verifier.
- Canonicalize input envelopes by removing the raw callback nonce and retaining
  only `SHA-256("validibot-callback-nonce\0" || nonce)`.
- Extend the FMU, SHACL, and Schematron input builders with callback nonce
  fields while preserving nonce-free synchronous execution.

### Notes

- Producers and validator runtimes must upgrade together; attempt-v1 envelopes
  are rejected rather than accepted without callback-secret authentication.
- The raw callback nonce never appears in canonical input bytes or output
  envelopes. Its public commitment can safely participate in evidence.
- The fixed cross-repository nonce fixture hashes to
  `a212b9aaad3aca508a88608d70fd75b5642a8c0e20876308887789dc5bbfb64d`.

## [0.16.0] - 2026-07-17

### Changed (BREAKING)

- Require every input, resource, and output artifact file item to carry its
  exact byte size, lowercase SHA-256, and provider-specific immutable storage
  version.
- Require resource items to carry a safe logical leaf name and reject path-like
  names across input, resource, and artifact items.
- Extend the FMU, SHACL, and Schematron input builders with the required file
  integrity arguments.

### Notes

- This is the shared-contract portion of the ADR-2026-07-10 streaming input
  verification slice. Producers and validator runtimes must upgrade together;
  there is no legacy or optional integrity mode.
- The fixed cross-repository fixture now hashes to
  `e17c5dae05c58f4d6034806e3f5e7a7602013d03f27ec811a97a9fc49f9d88d5`.

## [0.15.0] - 2026-07-17

### Changed (BREAKING)

- Require every validator input context to identify its execution attempt,
  step run, attempt-contract version, and exact expected output URI.
- Require every validator output envelope to echo that identity together with
  the canonical input-envelope SHA-256 and actual output URI.
- Extend the FMU, SHACL, and Schematron input builders with the required
  attempt identity arguments.

### Notes

- This is the coordinated strict-attempt-contract slice of
  ADR-2026-07-10. All envelope producers and consumers must upgrade together.
- The fixed cross-repository fixture hashes to
  `0f4f7cd8b38a79dbc2c4ac66c1ed602cb4db59665d52b6df73cd409bdaf765c7`
  using the shared RFC 8785/JCS canonicalization helper.

## [0.14.0] - 2026-07-15

### Added

- Add evidence-manifest artifact lineage models: `ManifestProducedArtifact`,
  `ManifestArtifactInputBinding`, and `ManifestArtifactLineageEdge`.
- Add default-empty `EvidenceManifest.produced_artifacts`,
  `artifact_input_bindings`, and `artifact_lineage_edges` fields so producers
  can record produced artifacts, consumed file-port bindings, and upstream
  artifact producer-to-consumer edges without exposing private storage URIs.

### Notes

- Additive change: the evidence schema string stays `validibot.evidence.v1`.
  Producers predating these fields leave them empty; newer producers can
  populate them while preserving v1 compatibility.

## [0.13.0] - 2026-07-14

### Added

- Add `validibot_shared.validations.artifacts` with the provider-neutral
  `ArtifactRef` schema and file-port contract vocabulary used by workflow
  artifact references and file-like step ports.
- Add optional `port_key` fields to `InputFileItem` and `ResourceFileItem` so
  backend envelope items can be traced back to their declared Validibot file
  ports during the artifact-port rollout.

## [0.12.1] - 2026-07-13

### Added

- Add `validibot_shared.canonicalization`, the shared RFC 8785 / JCS
  canonical-JSON helper used by community evidence manifests and Pro credential
  signing. This moves the canonicalizer out of the Pro-only layer so the
  workflow-definition contract hash has one portable implementation for
  producers and third-party verifiers.

## [0.12.0] - 2026-07-02

### Changed (BREAKING for the Schematron contract introduced in 0.11.0)

- Schematron pivots from curated "rule packs" to **author-uploaded rules**
  (ADR-2026-07-01 revision): `SchematronInputs` now carries the rules
  **inline** as `schematron_text` (+ `schematron_sha256` provenance) — the
  SHACL `shapes_text` pattern — replacing the staged-artefact reference
  fields (`pack_id`, `pack_version`, `artifact_uri`, `artifact_sha256`,
  `source_sha256`, `query_binding`, `engine`). The container compiles the
  source itself (SchXslt2 transpiler baked into the image).
- `SchematronOutputs` provenance: `schematron_sha256` replaces the
  `pack_*` fields; `query_binding` is now the binding *detected* from the
  source; `engine` unchanged (what actually ran).
- `ENGINE_ERROR_RULES_INVALID` replaces `ENGINE_ERROR_ARTIFACT_MISMATCH`:
  an uploaded schematron that fails to compile is an engine-level refusal
  (author-facing), never a finding about the submitted document.
- 0.11.0 had no consumers at publish time, so this breaking change is
  intentionally taken now rather than carried forever.

## [0.11.0] - 2026-07-02

### Added

- New `validibot_shared.schematron` package with the container contract for
  the Schematron Advanced validator (ADR-2026-07-01): `SchematronInputs` +
  `build_schematron_input_envelope()` (input direction — ships a *staged
  artefact reference* with checksums, not inlined rule text) and
  `SchematronOutputs` / `SchematronOutputEnvelope` (output direction —
  `engine_status` failure taxonomy, per-severity counts, the
  `finding_rule_ids_by_severity` map, structured `SchematronFinding` rows
  preserving native rule ids/locations, and full pack/engine provenance).
- `ValidatorType.SCHEMATRON` — required so Schematron envelopes can carry
  the canonical validator identifier.
- `validibot_shared.schematron.svrl` — the canonical SVRL → findings/summary
  parser (severity chain `@flag` → `@role` → fail-closed ERROR, active
  `successful-report` handling, `fired_rule_count`, the
  `finding_rule_ids_by_severity` map, explicit truncation). Lives here so the
  validator backend container and the Django app parse SVRL identically.
  Adds a `defusedxml` runtime dependency.

## [0.10.0] - 2026-07-01

### Added

- `WorkflowContractSnapshot` gains three additive, optional fields for the
  Constants primitive (ADR-2026-06-18): `constants` (workflow Constants — the
  `c.*` namespace — with their fixed values), `signal_mappings` (signal-mapping
  *definitions*, never resolved `s.*` runtime values), and
  `workflow_definition_hash` (the semantic-contract digest). New nested models
  `ContractConstant` and `ContractSignalMapping` are exported from
  `validibot_shared` and `validibot_shared.evidence`.
- These record "checked against these constants" in the evidence manifest for
  *every* run, not just Pro-signed ones. Resolved signal values are deliberately
  excluded (submission-derived and retention-gated).

### Notes

- Additive change: the schema string stays `validibot.evidence.v1` per the
  package's versioning policy. Producers predating these fields leave them empty
  and older consumers ignore them.

## [0.9.2] - 2026-06-10

### Changed

- Maintenance release: version bump and republish only — no library code
  changes relative to 0.9.1.

## [0.9.1] - 2026-06-06

### Changed

- `SHACLInputs.pyshacl_timeout_seconds` default raised from 30s to 300s to
  match the producer-side defaults in Django (`shacl/launch.py`) and the
  container backend (`shacl/engine.py`), which had moved to a 300s default
  (1800s hard cap). The envelope contract was lagging, so direct/shared-envelope
  consumers and tests saw a stale 30s timeout. `sparql_query_timeout_seconds`
  (10s) already matched.

## [0.9.0] - 2026-06-02

### Added

- SHACL Advanced validator envelopes (``validibot_shared/shacl/``):
  ``SHACLInputEnvelope`` / ``SHACLInputs``, ``SHACLOutputEnvelope`` /
  ``SHACLOutputs``, ``SHACLSparqlAssertionSpec``, and the
  ``build_shacl_input_envelope`` helper. These define the contract for running
  SHACL validation in an isolated container backend instead of in-process in the
  Django worker — the container is the only place untrusted RDF parsing and
  author-supplied SPARQL (SHACL-AF constraints + SPARQL-ASK assertions) execute.
- ``ValidatorType.SHACL``.
- RDF MIME types on ``SupportedMimeType`` (``RDF_TURTLE``, ``RDF_XML``,
  ``RDF_JSON_LD``, ``RDF_N_TRIPLES``, ``RDF_N_QUADS``) so an RDF submission can
  ride the typed ``InputFileItem.mime_type`` field.

These are purely additive — no existing schema changed.

## [0.8.0] - 2026-05-23

### Changed (breaking)

- ``EnergyPlusSimulationMetrics`` no longer carries ``zone_count``.
  Per ADR-2026-05-22's provenance rule, IDF-text-derived facts (zone
  count, version, north axis) are step **inputs** populated by the
  validator's parser, not step outputs. They live in the ``i.*`` CEL
  namespace, not in this output envelope. Consumers that read
  ``zone_count`` from an envelope must migrate to reading
  ``i.zone_count`` in their assertions (or
  ``run.summary["steps"][key]["input"]["zone_count"]`` for direct
  introspection).
- ``EnergyPlusSimulationMetrics.floor_area_m2`` renamed to
  ``simulated_conditioned_area_m2``. The new name disambiguates the
  value from any "floor area" the IDF declares as input — this field
  is the conditioned area EnergyPlus actually simulated, which may
  differ from the design area an author supplied. Producers MUST
  populate the new field name; consumers reading the old name will
  see ``None``.

### Schema-version contract

These are removals/renames, not additive changes. Per the
schema-versioning policy in
``validibot_shared/evidence/manifest.py``, removals bump the major
version of the field's schema. The envelope itself stays on its
existing schema version because the changes are confined to the
``metrics`` sub-model; consumers that need backward compatibility
should pin to ``validibot-shared<0.8.0`` until they migrate.

## [0.7.4] - 2026-05-03

### Added

- ``EvidenceManifest.source`` (optional, default ``None``): documents
  which auth channel produced the run. One of ``LAUNCH_PAGE``,
  ``API``, ``MCP``, ``X402_AGENT``, ``CLI``, ``SCHEDULE``. Producers
  MUST derive this from the authenticated route, NEVER from a
  caller-controlled header. Older producers and producers that don't
  track source leave the field ``None``.

### Schema-version contract

This change is purely additive — adding an optional field with a
default. Per the schema-versioning policy in
``validibot_shared/evidence/manifest.py``, additive changes preserve
``v1``. Verifiers reading manifests written by 0.7.4+ producers will
see the new field, while manifests written by 0.7.3- producers will
omit it (Pydantic's default kicks in on parse).

## [0.7.3] - 2026-05-03

### Fixed

- PyPI OIDC build attestations are now correctly generated and
  recorded against published wheels. The 0.7.2 release published
  successfully but PyPI's trusted-publisher binding was missing
  the workflow filename, so PyPI couldn't match the OIDC token's
  ``workflow_ref`` claim and skipped attestation generation. The
  binding has been corrected on PyPI's side; this release verifies
  the fix end-to-end. No library code changes between 0.7.2 and
  0.7.3 — only the upstream PyPI configuration.

### Note on 0.7.2

0.7.2 is on PyPI and functionally equivalent to 0.7.3, but lacks
the OIDC attestation in PyPI's provenance UI because the
trusted-publisher binding was incomplete at upload time. PyPI
doesn't allow re-attestation of already-uploaded files, so 0.7.2
will permanently show no provenance link. Operators who care about
the PyPI-side attestation should use 0.7.3 or later.

## [0.7.2] - 2026-05-03

### Fixed

- Publish workflow no longer collides with twine's pre-flight check.
  In 0.7.1 the CycloneDX SBOMs were generated into ``dist/``
  alongside the wheel; ``pypa/gh-action-pypi-publish`` treats every
  file in ``dist/`` as a candidate for PyPI upload and rejected the
  ``.cdx.json`` / ``.cdx.xml`` files as ``InvalidDistribution``,
  failing the publish step before the wheel reached PyPI. SBOMs now
  generate into ``sbom/`` so PyPI publish only sees wheels.

### Note on 0.7.1

0.7.1 was tagged and a GitHub release was created, but the wheel did
NOT reach PyPI due to the workflow bug fixed above. The 0.7.1 git
tag remains as a record of the failed release attempt; the v0.7.1
GitHub release retains the SBOM artifacts that were generated before
the publish step failed. Use 0.7.2 for the actual release content
(no library code changed between 0.7.1 and 0.7.2 — only the
workflow).

## [0.7.1] - 2026-05-03

### Added

- CycloneDX SBOM generation in the publish workflow (Trust ADR
  Phase 5 Session D). Each release uploads ``validibot-shared.cdx.json``
  and ``validibot-shared.cdx.xml`` as workflow artifacts and
  attaches them to the GitHub Release alongside the wheel. Combined
  with the OIDC build attestation that PyPI already records via
  ``attestations: true``, this gives downstream operators two
  independent layers of provenance: "did this come from where I
  think?" (OIDC) plus "what's inside it?" (SBOM).
- Signed-tag release flow via ``just release X.Y.Z``. The recipe
  enforces preconditions (clean working tree, on ``main``, version
  bumped, tag doesn't already exist) and signs the tag with the
  maintainer's SSH key before pushing. The ``.allowed_signers``
  file in the repo root carries the maintainer's public key so
  ``git verify-tag`` works out of the box for downstream operators.

## [0.7.0] - 2026-05-02

### Added

- ``StepValidatorRecord.validator_backend_image_digest``: optional
  field carrying the resolved sha256 digest of the validator backend
  container image that executed each step (e.g. ``sha256:abc...`` or
  ``registry/...@sha256:abc...``). Complements the existing
  ``validator_semantic_digest`` field — one describes the validator's
  *configuration*, the other describes the *image bytes that ran*.
  Optional because (a) simple-validator steps run inline without a
  backend, and (b) historical step runs predate the field. Producers
  source the value from a new ``ValidationStepRun.validator_backend_image_digest``
  column populated at execution time (Docker SDK ``RepoDigests`` for
  local runs; Cloud Run Execution metadata for hosted runs). The
  schema-version string stays ``validibot.evidence.v1`` because the
  change is additive — verifiers running an older shared version
  silently ignore the unknown key. ADR-2026-04-27 Trust ADR Phase 5
  Session A.

### Why this is a minor bump (not patch)

Optional additive fields are technically backwards-compatible at
parse time (an old verifier sees an extra key it ignores), but they
*do* extend the public surface — a verifier built against 0.7.0 can
expect the field to exist on records produced by ≥0.7.0 manifests.
Per the project's pre-1.0 SemVer practice, additive surface changes
get a minor bump so downstream consumers' resolvers can express
"I need a producer that emits this field" via ``>=0.7.0`` constraints.

## [0.6.0] - 2026-05-02

### Changed (BREAKING)

- ``WorkflowContractSnapshot.data_retention`` renamed to
  ``input_retention``. Mirrors the existing ``output_retention``
  field name and removes the long-running ambiguity ("data" could
  mean input or output) that caused real reasoning bugs in
  consuming code. The rename is *clarification only* — same
  retention values, same enforcement behaviour. The schema-version
  string stays ``validibot.evidence.v1`` because no semantic
  property changed; only the field name is clearer.
- Consumers reading manifests produced by this version see
  ``input_retention`` instead of ``data_retention``. There are no
  external consumers yet (Phase 4 of the Validibot Trust ADR
  hasn't shipped publicly), so the rename is safe to land before
  any verifier writes to the field name.

## [0.5.1] - 2026-05-02

### Changed

- Loosened the `pydantic` dependency from the strict `==2.13.3` pin
  to a `>=2.13,<3` range. Strict pins on shared-library dependencies
  break universal resolution for downstream projects whose
  `requires-python` window extends past pydantic's classifier
  range. Libraries should pin a band, not a point.

## [0.5.0] - 2026-05-02

### Added

- ``validibot_shared.evidence`` module exposing the
  ``validibot.evidence.v1`` Pydantic schema for run-completion
  evidence manifests. Public symbols: ``EvidenceManifest``,
  ``WorkflowContractSnapshot``, ``StepValidatorRecord``,
  ``ManifestRetentionInfo``, ``ManifestPayloadDigests``,
  ``SCHEMA_VERSION``. Lives in shared so external verifiers can
  depend on a single PyPI package without pulling in the Django
  application stack. See ADR-2026-04-27 (Validibot Trust ADR),
  Phase 4 Session A.

## [0.4.4] - 2026-03-25

### Changed

- Updated dependencies.

## [0.4.3] - 2026-03-25

### Changed

- Updated dependencies.
- Renaming validibot-validators project.

## [0.4.2] - 2026-03-25

### Fixed

- Pinned the runtime and development dependencies to exact versions so shared package installs stay reproducible across rebuilds.

## [0.4.1] - 2026-03-20

### Fixed

- Updated the README EnergyPlus input-envelope example to use the current
  enum values and required `org`/`workflow` fields.
- Corrected the documented developer test command to
  `uv run python -m pytest` and removed the stale `mypy src/` command.

## 0.4.0

### Changed

- **FMU envelopes**: Clarified that `input_values`, `output_variables`,
  and `output_values` are keyed by native FMU variable names (from
  modelDescription.xml), not internal catalog slugs. No wire format
  change — this documents the contract that was already in practice.
- **FMU models**: Probe results now feed into `StepIODefinition` rows
  in the core Django app (previously documented as "catalog entries").
- **EnergyPlus models**: `EnergyPlusSimulationMetrics` field names are
  now documented as the canonical EnergyPlus output names expected by
  core Validibot, mapped to `StepIODefinition` rows.

## [0.3.1] - 2026-03-10

### Added

- Window envelope metrics on `EnergyPlusSimulationMetrics`: `window_heat_gain_kwh`,
  `window_heat_loss_kwh`, `window_transmitted_solar_kwh`. These are extracted from
  EnergyPlus output variables (`Surface Window Heat Gain Energy`, etc.) and will be
  `None` when the corresponding `Output:Variable` objects are not present in the IDF.

## [0.3.0] - 2026-02-25

### Changed

- **BREAKING**: Renamed `fmi` module to `fmu` throughout the library
  - `validibot_shared.fmi` -> `validibot_shared.fmu`
  - All class names: `FMIInputEnvelope` -> `FMUInputEnvelope`, `FMIOutputEnvelope` -> `FMUOutputEnvelope`, `FMISimulationConfig` -> `FMUSimulationConfig`, `FMIInputs` -> `FMUInputs`, `FMIOutputs` -> `FMUOutputs`, `FMIProbeResult` -> `FMUProbeResult`, `FMIVariableMeta` -> `FMUVariableMeta`
  - Function: `build_fmi_input_envelope()` -> `build_fmu_input_envelope()`
  - Enum: `ValidatorType.FMI` -> `ValidatorType.FMU`
  - The `fmi_version` field on `FMUOutputs` is unchanged (refers to the FMI standard version)

## [0.2.1] - 2026-02-16

### Added

- Pre-commit hooks with TruffleHog secret scanning, detect-private-key, and Ruff linting
- Dependabot configuration for GitHub Actions and Python dependency updates
- Hardened .gitignore to exclude key material and credential files
- pip-audit dependency auditing in CI
- Sigstore attestations for PyPI publish (provenance verification)

### Changed

- Pinned all GitHub Actions to commit SHAs and uv to exact version in publish and test workflows
