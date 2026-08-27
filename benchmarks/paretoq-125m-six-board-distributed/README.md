# ParetoQ 125M six-board distributed inference

This SSOS-ESP32 benchmark package runs one pretrained
`facebook/MobileLLM-ParetoQ-125M-2-bit` causal-language-model context through a
40 MHz SPI ring of six ESP32-S3 boards:

- five compute nodes own disjoint layer and vocabulary shards; and
- one relay-only node closes the physical ring.

Package version: **1.0.0**. This is an isolated benchmark package, not a change
to the SSOS core protocol version.

## Accepted physical result

The fixed five-prompt corpus uses greedy decoding, KV cache, and 24 generated
tokens per prompt. FAST and REGULAR use identical prompts, checkpoint, token
counts, decoding, and host-oracle gates.

| Metric | FAST | REGULAR | FAST comparison |
|---|---:|---:|---:|
| Prompts | 5 | 5 | identical |
| Generated tokens | 120 | 120 | identical |
| Exact host-oracle tokens | 120/120 | 120/120 | identical |
| Mean TTFT | 56.426 s | 87.588 s | 1.552x |
| Total prompt-to-finish | 1,195.151 s | 1,787.937 s | 1.496x |
| Aggregate decode | 0.125955 tok/s | 0.085185 tok/s | 1.479x |
| SPI errors | 0 | 0 | identical |

See [the complete proof](results/physical/AB_PROOF_REPORT.md) for every prompt,
decoded continuation, per-prompt timing, and artifact hash. The raw serial
receipts are preserved in `results/physical/ab_proof.json`.

## Physical topology

| Stage | Tested port | Role | Layers | Vocabulary rows |
|---:|---|---|---:|---:|
| 0 | COM4 | compute master | 0-5 | 0-6,399 |
| 1 | COM7 | compute | 6-11 | 6,400-12,799 |
| 2 | COM8 | compute | 12-17 | 12,800-19,199 |
| 3 | COM9 | compute | 18-23 | 19,200-25,599 |
| 4 | COM11 | compute | 24-29 | 25,600-31,999 |
| 5 | COM22 | transport relay | none | none |

The system therefore contains **six physical ESP32 boards and five model
compute shards**. See [WIRING.md](WIRING.md) and
`config/six_board_topology.json`.

## What is included

- `firmware/` - accepted node/relay source and generated model-layout headers
- `prebuilt/` - exact compute and relay boot/application images used by the proof
- `config/` - five-shard model layout, six-board topology, and prompt contract
- `tools/` - checkpoint export, verification, deployment planning, capture, and reporting
- `tests/` - fail-closed format, topology, prompt, and proof checks
- `artifacts/manifests/` - accepted derived-weight manifests without gated weights
- `results/` - host oracle and final physical A/B evidence

Compiler caches, ELF/map files, failed experiments, transient captures, recovery
images, COM3 material, and the gated checkpoint/shard bytes are excluded.

## Model access and reconstruction

The Meta checkpoint is access-controlled and is intentionally not redistributed.
After accepting its upstream terms and authenticating with Hugging Face:

```powershell
python -m pip install -r requirements.txt
hf download facebook/MobileLLM-ParetoQ-125M-2-bit --revision 2e367775142fafa944e28a1e8a1fc428e8554fab --local-dir model_source/MobileLLM-ParetoQ-125M-2-bit
python tools/export_paretoq.py --checkpoint model_source/MobileLLM-ParetoQ-125M-2-bit --layout config/five_compute_layout.json --output build/shards
python tools/verify_export.py --checkpoint model_source/MobileLLM-ParetoQ-125M-2-bit --export build/shards
python tools/generate_stage_headers.py --shards build/shards --output firmware/generated
```

Compare the reconstructed hashes with `artifacts/manifests/` before deployment.

## Verify the package

```powershell
python tools/verify_package.py
python -m pytest tests -q
```

The package verifier checks `SHA256SUMS`, the five-prompt completion gates,
240/240 combined FAST/REGULAR exact tokens, zero SPI errors, the checkpoint
identity, and the six-board topology.

## Physical benchmark

The model shards must already exist under `build/shards`, and all six boards
must be wired and running the included application:

```powershell
python tools/run_ring_link_test.py
python tools/run_physical_benchmark.py --package . --modes REGULAR FAST --preflight LINK
python tools/generate_ab_report.py --package .
```

`LINK` performs a complete zero-error ring lap. Each prompt independently
resets model state and must return 24 exact host-oracle tokens with zero SPI
errors. The heavier diagnostic `BUS` preflight remains available but is not
required for proof admission.

## Claim boundaries

- This proves exact distributed inference for the named checkpoint and tested
  six-board hardware identity.
- FAST is 1.496x faster in total prompt-to-finish time across the fixed corpus;
  it is not interactive-speed inference.
- COM22 is required by this ring but performs no model layers or vocabulary scan.
- `spi_ms` includes ring-cycle wall time overlapping worker computation; it is
  not isolated wire-transfer time.
- The five prompts are deterministic regression gates, not a broad language
  quality evaluation.
- Prebuilt role selection is MAC-bound to the six tested boards. Different
  boards require source changes, rebuild, and fresh validation.
- Flashing replaces existing application/partition regions. Preserve device
  state that matters before using deployment tools.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before redistribution.
