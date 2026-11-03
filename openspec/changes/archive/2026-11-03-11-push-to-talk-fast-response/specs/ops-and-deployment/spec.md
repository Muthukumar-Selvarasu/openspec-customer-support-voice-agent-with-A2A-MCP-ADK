# Spec Delta

## ADDED Requirements

### Requirement: Local Phoenix opens without a login
The local Phoenix service SHALL set `PHOENIX_ENABLE_AUTH` to false. `run.sh` SHALL keep that setting when it writes `compose.runtime.yaml`. The local Phoenix page SHALL load without a username or password.

#### Scenario: Compose disables Phoenix auth
- **WHEN** `compose.yaml` is inspected
- **THEN** the phoenix service sets `PHOENIX_ENABLE_AUTH` to false

#### Scenario: Generated runtime file keeps auth off
- **WHEN** `run.sh` writes `compose.runtime.yaml` because host port 5000 is busy
- **THEN** the phoenix service in that file still sets `PHOENIX_ENABLE_AUTH` to false

