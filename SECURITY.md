# Security policy

SSOS is experimental firmware. Do not deploy it as a safety controller,
security boundary, alarm, medical device, or life-support component.

## Supported releases

Only the newest tagged release is supported. Unversioned ZIP files and local
development builds are not public security releases.

## Reporting

Do not include credentials, private packet contents, full device identifiers,
or exploit payloads in a public issue. Use the repository's
[private vulnerability report](https://github.com/tylorsaling-source/SSOS-ESP32/security/advisories/new)
so maintainers can investigate before details are disclosed publicly.

## Flashing guarantees

The guided scripts verify release hashes and require explicit target
confirmation. They do not prove that a connected board has the required flash
layout. Users must verify the exact supported hardware before writing.
