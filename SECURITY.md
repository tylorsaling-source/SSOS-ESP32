# Security policy

SSOS is experimental firmware. Do not deploy it as a safety controller,
security boundary, alarm, medical device, or life-support component.

## Supported releases

Only the newest tagged release is supported. Unversioned ZIP files and local
development builds are not public security releases.

## Reporting

Do not include credentials, private packet contents, full device identifiers,
or exploit payloads in a public issue. Repository maintainers should configure
GitHub private vulnerability reporting before the first public release and put
that contact link here.

## Flashing guarantees

The guided scripts verify release hashes and require explicit target
confirmation. They do not prove that a connected board has the required flash
layout. Users must verify the exact supported hardware before writing.
