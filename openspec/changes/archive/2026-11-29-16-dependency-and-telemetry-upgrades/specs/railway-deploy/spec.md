# Spec Delta

## ADDED Requirements

### Requirement: Pinned Phoenix Container Image on Railway
The optional `phoenix` service in `.railway/railway.py` SHALL pin the explicit container image tag `arizephoenix/phoenix:version-22.0.1` matching `compose.yaml` and MUST NOT use the floating `:latest` tag.

#### Scenario: Railway Phoenix service uses pinned version tag
- **WHEN** `.railway/railway.py` and `compose.yaml` are inspected
- **THEN** `.railway/railway.py` uses `image("arizephoenix/phoenix:version-22.0.1")` (not `:latest`), matching the `version-22.0.1` tag in `compose.yaml`
