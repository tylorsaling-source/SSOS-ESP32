# V4.0.0 package manifest

## Included capabilities

| Path | Purpose |
|---|---|
| `README.md` | Start-to-finish public guide |
| `VERSION` | Package version 4.0.0 |
| `config.json` | Exact 549,984-parameter architecture |
| `TRAINING_PROTOCOL.md` | 9-D physical forward/backward/update contract |
| `checkpoints/step-00107419.pt` | First resumable master/worker checkpoint |
| `data/manifest.json` | Accepted corpus and tokenizer identity |
| `data/ssos-550k-vocab.json` | Exact 940-token vocabulary |
| `data/ssos-550k-merges.txt` | Exact BPE merges |
| `domain/field-language.txt` | Authored field-language curriculum |
| `tools/model.py` | Model and stage ownership |
| `tools/train_reference.py` | Resumable cumulative-token trainer |
| `tools/verify_split.py` | Continuous-versus-split numerical gate |
| `tools/prepare_corpus.py` | FineWeb-Edu/Wikipedia corpus builder |
| `tools/prepare_curriculum.py` | Balanced adult field-language builder |
| `tools/quality_gate.py` | Deterministic language inspection |
| `tools/generate.py` | Prompted checkpoint generation |
| `results/first-checkpoint/` | Compact checkpoint and quality evidence |
| `SHA256SUMS` | Integrity for every packaged file |

## Excluded runtime material

- Downloaded corpus text and local documents
- Intermediate and continuation checkpoints
- Full 30 MB training event log
- Process IDs, dashboard runtime files and build caches
- Serial ports, MAC addresses, hostnames and local filesystem paths
