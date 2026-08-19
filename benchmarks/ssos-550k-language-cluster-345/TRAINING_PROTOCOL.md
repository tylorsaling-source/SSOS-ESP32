# Physical split-training protocol

## Ownership

- Master: vocabulary embedding and transformer layers 0-1.
- Worker: transformer layers 2-3, final normalization, language head, and loss.
- Laptop: tokenizer, sample selection, durable checkpoint assembly, validation,
  and recovery. It does not silently compute board-owned gradients.
- Optional USB pointer boards: propose curriculum/sample addresses and verify
  acknowledgements. They never receive model weights or override sequence
  legality.

## 9-D transaction address

Every forward, backward, update, and acknowledgement carries the same address:

1. `corpus_id`
2. `sequence_id`
3. `token_offset`
4. `phase` (`forward`, `backward`, `update`, `ack`)
5. `split_id`
6. `checkpoint_generation`
7. `accumulation_slot`
8. `retry_id`
9. `curriculum_id`

It is an identity and routing layer. The 96-wide FP32/FP16 activation and
gradient payloads remain model tensors.

## One microbatch

1. Laptop sends token IDs, targets, legal sequence length, and a fresh 9-D
   address to the master.
2. Master embeds tokens and runs layers 0-1, retaining its forward tape.
3. Master sends the boundary activation to the worker over acknowledged SPI
   DMA.
4. Worker runs layers 2-3, normalization, language head, and cross-entropy.
5. Worker backpropagates through its stage and sends the boundary gradient back.
6. Master backpropagates that gradient through layers 0-1 and embeddings.
7. Both accumulate locally. Neither updates until both report the same address,
   finite gradients, matching accumulation count, and checksum.
8. Both apply the update and acknowledge the new checkpoint generation.
9. The laptop exports a durable two-part checkpoint only after both hashes are
   present. An incomplete generation is never promoted.

## Required stale-response protection

Frames must include a run nonce, the full 9-D address, payload length, role,
dtype, CRC32, and monotonically increasing frame sequence. Bounds for token,
position, layer, activation length, and gradient length are checked before any
memory access. This incorporates the focused V3 security-audit findings.

## First physical acceptance gate

- Preserve exact current master and worker flash/checkpoint images first.
- One deterministic sequence and one optimizer step.
- Host and boards start from identical FP32 weights.
- Forward loss absolute difference <= 1e-5.
- Every boundary-gradient element absolute difference <= 2e-5.
- Per-stage gradient cosine similarity >= 0.99999.
- Updated-weight maximum absolute difference <= 2e-5.
- No stale, cross-sequence, partial, or non-finite frame accepted.
- Reset before commit leaves the prior checkpoint bootable.

Only after that gate passes should throughput and longer training be measured.
