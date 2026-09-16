# SSOS System-One / Jev Distillation Experiment

Status: **experimental**. This does not modify or invalidate the V2.0.1 hardware proof.

## Goal

Test whether Jev-style atomic probabilistic judgments can be distilled into the existing SSOS V2 fixed **9-input / 8-output / 72-weight signed-Q10 head**.

The first mapping uses eight independent Noul-like questions rather than text generation:

1. `route_fast_path`
2. `persist_state`
3. `prefetch_context`
4. `wake_worker`
5. `retry_transport`
6. `request_more_state`
7. `state_anomalous`
8. `fallback_deterministic`

The ESP32 computes eight logits with the existing V2 `MINFER` path. A deterministic caller can interpret `logit > 0` as probability > 0.5, or apply `sigmoid(logit)` when a calibrated probability is useful. Nothing requires autoregressive text generation.

## 9-D state contract

Inputs 0..7 are normalized to `[-1, +1]`; input 8 is fixed to `1.0` as the bias feature.

| i | feature | -1 | +1 |
|---|---|---|---|
| 0 | urgency | idle / no deadline | immediate / deadline-critical |
| 1 | queue_pressure | empty | saturated |
| 2 | memory_pressure | ample memory | memory critical |
| 3 | transport_health | failing / unstable | healthy |
| 4 | worker_capacity | unavailable | abundant capacity |
| 5 | state_novelty | familiar | highly novel / out-of-distribution |
| 6 | confidence_margin | uncertain | strong separation / confidence |
| 7 | persistence_risk | loss is cheap | state loss is costly |
| 8 | bias | `1.0` | `1.0` |

The contract is intentionally tiny. The host/controller may derive these eight values from richer state. The experiment asks whether the last-mile decision fabric can remain tiny.

## Phase 0 result: synthetic stress test

`distill_system_one.py` includes a reproducible mildly nonlinear synthetic teacher. It is **not Jev** and makes no claim about Jev's hidden architecture. It exists only to answer a narrower question: can the fixed 72-weight head approximate eight nonlinear probabilistic judgments well enough to justify a real teacher run?

Seed 42, 50,000 examples, 40,000 train / 10,000 test:

- mean threshold agreement: **92.126%**
- mean probability MAE: **0.05759**
- mean Brier error against teacher probabilities: **0.006396**
- maximum probability change caused by Q10 quantization: **0.0004701**

That is strong enough to continue to a real Jev-labelled dataset without changing the V2 model shape first.

## Real Jev path

TypeSafe's public API accepts one state plus multiple independent typed questions in one call. `collect_jev_teacher.py` sends the eight questions above as Noul questions and records the returned probabilities beside the eight normalized SSOS features.

Install:

```bash
python -m pip install typesafe-sdk numpy
```

Set early-access credentials:

```bash
export TYPESAFE_API_KEY=...
```

Prepare JSONL where each row contains both the richer state presented to Jev and the compact SSOS projection:

```json
{"state":{"queue_depth":7,"free_heap":90321,"worker_ready":true},"x8":[0.3,0.7,-0.2,0.8,0.4,0.1,0.2,0.6]}
```

Collect teacher labels:

```bash
python experiments/system_one_jev_distill/collect_jev_teacher.py states.jsonl jev_teacher.jsonl
```

Distill to the 72-weight head:

```bash
python experiments/system_one_jev_distill/distill_system_one.py \
  --teacher-jsonl jev_teacher.jsonl \
  --out system_one_distill_out
```

The output includes `ssos_head_rows.json`, which uses the same 8x9 float-row shape consumed by the existing V2 model installer, plus a report containing Q10 evaluation metrics.

## Pass/fail gate for the first real run

Do not move the goalposts after seeing results. Initial gate:

- >= 90% mean threshold agreement with Jev on a held-out set;
- <= 0.08 mean probability MAE;
- Q10 quantization changes predicted probabilities by <= 0.005 max;
- no single question below 80% threshold agreement without being explicitly investigated.

If the head misses this gate, preserve the result. The next comparison should be a small nonlinear head (for example 9 -> 16 -> 8), not an immediate jump back to a language model.

## Why this fits SSOS

V2 already gives us the useful deployment properties: packet-backed replaceable weights, persistence, a fixed compact input/output contract, and deterministic surrounding code. Jev-style System-One behavior gives that head a much better target than prose generation: **small, typed, probabilistic judgments** that software composes.
