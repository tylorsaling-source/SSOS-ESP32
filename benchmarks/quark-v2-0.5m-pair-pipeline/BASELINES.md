# Original baseline comparison

All rows use the same pinned 465,504-parameter Quark-v2-0.5M checkpoint, the
same accepted Q8_0 group-8 artifact, greedy decoding and the same 24-token
oracle continuation.

## Original physical measurements

| Path | Contexts | Runs | Oracle | Decode throughput | Prefill | Decode wall | SPI/reporting |
|---|---:|---:|---:|---:|---:|---:|---:|
| One ESP32-S3, complete model | 1 | 1 | 24/24 | 18.469438 tok/s | 624.414 ms | 1,299.444 ms | none |
| Original sequential master/worker split | 1 | 5 | 120/120 | 18.344879-18.346576 tok/s; median 18.345216 | not retained per run in accepted baseline JSON | derived from reported tok/s | last reported 11.676 ms |
| Pre-change pair health recheck | 1 | 5 | 120/120 | 18.344711-18.345931 tok/s; median 18.344921 | 628.879-629.047 ms | 1,308.192-1,308.279 ms | 11.603-11.674 ms |

The original sequential pair was `0.993274x` the standalone board. It was exact
but slightly slower because dependent layer stages still execute serially for
one autoregressive stream.

The standalone row has one valid physical run. A repeated standalone statistic
is not claimed because that board did not re-enumerate after Windows closed its
native USB CDC handle.

## New two-context pipeline comparison

| Comparison | Calculation | Result |
|---|---|---:|
| New median versus standalone | 44.730763 / 18.469438 | 2.421880x |
| New minimum versus standalone | 44.729429 / 18.469438 | 2.421808x |
| New median versus original pair median | 44.730763 / 18.345216 | 2.438279x |
| New median versus pre-change pair recheck | 44.730763 / 18.344921 | 2.438319x |

The acceptance threshold, `36.938876 tok/s`, is exactly twice the standalone
18.469438 tok/s baseline. Every new physical run exceeded it.

These comparisons are aggregate decode throughput. The original rows decode one
autoregressive context; the new pipeline interleaves two independent contexts.
They do not establish a 2x reduction in one stream's causal token latency.

Machine-readable original evidence is in
`results/physical-20260818-original-baseline/benchmark.json`.

## Three-board four-context extension

| Path | Contexts | Accepted gate | Oracle | Aggregate decode throughput |
|---|---:|---:|---:|---:|
| Independent two-lane master plus two workers | 4 | 1 | 96/96 | 87.927387 tok/s |

The trio is `4.760696x` the one-board 18.469438 tok/s baseline and `4.792933x`
the original sequential-pair 18.345216 tok/s median. These are aggregate
throughput comparisons across four independent contexts. They are not
single-stream latency comparisons.

An earlier equivalent gate passed 96/96 at 87.871532 tok/s, but a five-run
trio stability statistic was not completed. The accepted result included one
checksum-recovered lane-2 packet and did not meet the requested 90 tok/s goal.
Machine-readable evidence is in
`results/physical-20260819-trio-pipeline/result.json`.
