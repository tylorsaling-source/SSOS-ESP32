# Third-party notices

## LH-Tech-AI/Quark-v2-0.5M

- Upstream: <https://huggingface.co/LH-Tech-AI/Quark-v2-0.5M>
- Pinned revision: `7a30cd277348416659e94d5937d699d72e34afac`
- Declared license: Apache License 2.0
- Original `model.safetensors` SHA-256:
  `3fce3f379b5c485d25f72364d10fd8d9fe22a1f38e244531391e77272cb79404`
- Converted Q8_0 group-8 artifact SHA-256:
  `b7ad1a7dfd8ae2d0fecf2c9f7db5546be56ff280fd35f616d16d9c400ae0b9bc`

The package includes a converted/quantized representation of this model and a
copy of its pinned model card under `upstream/`.

The Apache License 2.0 text is included as the package `LICENSE` and again at
`licenses/Quark-v2-0.5M-Apache-2.0.txt` for explicit model attribution.

## llama2.c

The compact Transformer runtime is derived from Karpathy's `llama2.c` project:

- Upstream: <https://github.com/karpathy/llama2.c>
- Declared license: MIT

The upstream MIT license is included at `licenses/llama2.c-MIT.txt`.

## Arduino-ESP32 and ESP-IDF

The firmware uses Arduino-ESP32 3.3.11 and Espressif ESP-IDF SPI, GPIO and heap
APIs. Those dependencies are not vendored in this preview and retain their own
licenses.
