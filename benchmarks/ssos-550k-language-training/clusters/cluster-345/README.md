# Cluster 3–4–5: independent first checkpoint

`cluster-345-fresh` is a second, independently initialized lineage using the
SSOS 549,984-parameter master/worker architecture. It shares the accepted model
shape, tokenizer and corpus identity so results remain comparable, but it does
not inherit weights, optimizer state or RNG state from the original lineage.

## First checkpoint

| Measurement | Value |
| --- | ---: |
| Step | 5,000 |
| Presented tokens | 5,120,000 |
| Tokens per parameter | 9.309362 |
| Training loss | 3.468667 |
| Held-out loss | 3.488711 |
| Checkpoint bytes | 6,652,561 |
| SHA-256 | `f397e0eb18b74a2acf88e65bcc797628a49ab7612ee833a8b60a326bb3e0f27a` |

The V2 checkpoint stores cumulative tokens directly. It also contains master
and worker weights, AdamW state, RNG state, corpus identity and the complete
100-token-per-parameter schedule.

## Inspect or resume

Run these commands from the parent `ssos-550k-language-training` directory:

```powershell
python .\tools\quality_gate.py `
  .\clusters\cluster-345\checkpoints\step-00005000.pt

python -u .\tools\train_reference.py `
  --resume .\clusters\cluster-345\checkpoints\step-00005000.pt `
  --target-tokens-per-parameter 100 `
  --batch-size 16 --sequence-length 64 `
  --learning-rate 3e-4 --min-learning-rate 3e-5 `
  --warmup-steps 2000 --schedule-origin global `
  --checkpoint-every 5000 --eval-every 5000 --eval-batches 32 `
  --seed 345984
```

[`results/result.json`](results/result.json) is the machine-readable checkpoint
record. [`results/quality.json`](results/quality.json) preserves the exact
deterministic language samples generated at this milestone.
