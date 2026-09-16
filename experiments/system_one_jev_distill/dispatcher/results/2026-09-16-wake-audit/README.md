# Follow-up: frozen dispatcher wake head fails its required capability

**Model outcome: FAIL. Physical sleep/wake acceptance: incomplete.**

The earlier 12 PASS / 6 BLOCKED physical routing report remains historical
evidence. This follow-up proves the frozen dispatcher model cannot request wake
for any legal sleeping-worker input, independently of the network wake problem.
The original Jev experiment and both frozen models remain unchanged.

## Proof and device check

Frozen rows SHA-256:
`dfb6a8abb8c47141fe3550f158b68953d1d3a63ede064f4becd9cbc15545bda7`.

The wake output is a linear function of eight projected features plus bias.
With readiness fixed at 0 (confirmed sleeping), maximize every other feature
over its allowed interval. The exact maximum wake logit is **-0.18359375**.
The reducer requires a nonnegative wake logit, so no legal sleeping input can
request wake. This bound includes the most favorable possible state: capable,
free, reliable, fresh, maximum work value, and zero energy or wake cost.

The physical ESP32 returned **-0.183594** for that synthetic corner input on
three repetitions. All eight outputs matched the frozen model within
`4.375e-7`. The original scoring head was restored and every coefficient checked.
No firmware was flashed or model saved. See [audit.json](audit.json).

These are real device inference measurements on synthetic candidate inputs;
they are not physical sleep/wake runs and do not satisfy scenarios 4 or 5.
High aggregate teacher agreement had concealed this unusable wake output.
The underlying training cause has not yet been established.

## Topology correction and desktop preflight

The owner clarified that Gamer stays awake. It can retain both the ESP32 USB
connection and GPU work. A separate CPU computer can serve as the sleeping
worker. The harness now permits separate `gpu` and `powerful` roles without
changing learned scores, thresholds, candidate membership, or expected gates.

A separate Windows laptop accepted a scheduled suspend request after Windows
confirmed an armed timed recovery. It then became unreachable over LAN and
Tailscale. Wake packets sent from two awake machines and the recovery timer did
not restore verified access. Without the laptop's post-resume power events,
this is an unresolved power preflight, not proof of successful sleep or wake.
The owner subsequently clarified that the task concerns worker processes, not
computer power. The laptop was manually recovered, both one-time experiment
tasks were removed, and their absence was independently verified. Private
addresses, device identifiers and raw logs remain excluded.

## Changes and remaining work

- Added an exact wake-capability bound and a preflight rejection before worker
  RPC, serial access, or suspend when the frozen model cannot request wake.
- Added separate GPU role support; legacy two-worker manifests retain their roles.
- Sixteen local dispatcher tests pass, including exhaustive-corner verification
  of the bound, controller suspend protection, and legacy role compatibility.
- The existing frozen model was not retrained or retuned. A separately documented
  training iteration and new held-out evaluation are required before another
  candidate can attempt acceptance.
- Computer power testing has stopped. Operating-system power adapters are disabled.
- The [corrected worker-process experiment](../2026-09-16-worker-process/README.md)
  subsequently completed all 18 repetitions with 15 PASS and 3 FAIL. The PR
  remains unmerged; no 18/18 PASS or deployed scheduler is claimed.
