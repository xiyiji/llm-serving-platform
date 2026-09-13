# Q1–Q5 verification

Initial local validation was based on main at d43c3137004e991aed0c6a32a9be8fcfcaf292bd.
The results below describe pre-deployment checks. See GitHub Actions and hosting
deployment records for subsequent rollout status. No Terraform apply was performed.

## Implemented

- Q1: typed promote JSON body; legacy query supported; missing, invalid and
  conflicting stages return 422. Unknown versions return 404.
- Q2: stream startup enters scheduler; complete successful streams are cached.
  First-token delivery is independent across a batch. Cancellation cleans up
  upstream work. Premature upstream EOF is an error, not a cacheable success.
- Q3: app-owned OTel SDK, FastAPI and httpx instrumentation, W3C propagation,
  per-request scheduler contexts, log trace IDs and optional OTLP HTTP export.
- Q4: Admin register/promote/load/unload controls, field validation, pending
  state, errors and registry/pool refresh.
- Q5: EKS connection and OIDC outputs, provider lock file, Terraform validation
  in CI.

## Verification performed

- Backend: 38 pytest cases, including 11 new regression tests. Local runtime:
  Python 3.14; existing CI targets Python 3.11/3.12 (remote CI not run here).
- Frontend: npm ci and production build/type checking succeeded.
- Browser: register, promote to production, load, unload succeeded against the
  local simulated backend; duplicate registration displayed the API error.
- Tracing: incoming parent extraction, outgoing trace header and child span,
  batch context isolation and actual protobuf export to a local OTLP receiver.
- Terraform 1.9.8: fmt -check, init -backend=false and validate succeeded.
- git diff --check succeeded. Temporary UI/backend servers were stopped.

Existing dependency warnings: npm reports one high and one critical advisory
in the existing frontend dependency tree (including Next.js 14.2.5). Dependency
upgrades were not included in these five fixes.

See [configuration and boundaries](GOVERNANCE-TRACING.md) for operation examples,
OTLP environment variables, cache semantics and EKS access prerequisites.
