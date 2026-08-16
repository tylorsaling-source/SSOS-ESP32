# Governance

SSOS ESP32 is maintainer-led and collaboration-first.

## How decisions are made

- Anyone may open a bug report, change request, or pull request.
- Protocol, persistence, flashing, hardware-support, and benchmark-policy
  changes should begin as a change request.
- Maintainers decide by reviewing evidence, compatibility, safety, scope, and
  long-term maintenance cost.
- The automated moderator only performs transparent routing and completeness
  checks. It cannot approve, reject, close, or merge a contribution.
- A merged pull request is the record of an accepted change.

## Release policy

Tagged releases describe their actual validation status. Hardware-tested,
compiled-only, simulated, and artifact-validated are distinct claims. Release
assets include checksums, and published history is not rewritten.

## Maintainer authority

Maintainers may decline changes that break the packet contract, weaken flash
safety, make unsupported performance claims, include incompatible licensing,
or create maintenance obligations beyond the project's scope. The reason should
be stated publicly unless doing so would expose a security report.
