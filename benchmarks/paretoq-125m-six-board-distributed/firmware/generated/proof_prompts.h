#pragma once

#include <stdint.h>

namespace paretoq {

struct ProofPrompt {
  const char* id;
  const uint16_t* input_ids;
  uint16_t input_count;
  const uint16_t* expected_ids;
  uint16_t output_count;
};

static constexpr uint16_t kP01Input[] = {1u, 450u, 2030u, 664u, 19032u, 471u};
static constexpr uint16_t kP01Expected[] = {263u, 2058u, 988u, 278u, 2030u, 17162u, 723u, 5870u, 304u, 5353u, 1009u, 664u, 29889u, 13u, 1576u, 2030u, 664u, 19032u, 471u, 263u, 2058u, 988u, 278u, 2030u};
static constexpr uint16_t kP02Input[] = {1u, 2180u, 6575u, 29878u, 895u, 29892u, 278u, 8580u};
static constexpr uint16_t kP02Expected[] = {338u, 1603u, 4972u, 292u, 29889u, 13u, 1576u, 8580u, 338u, 263u, 9434u, 329u, 653u, 310u, 278u, 402u, 6916u, 29892u, 607u, 24536u, 1549u, 278u, 4272u, 310u};
static constexpr uint16_t kP03Input[] = {1u, 450u, 22055u, 6496u, 278u, 28966u, 322u};
static constexpr uint16_t kP03Expected[] = {278u, 6012u, 414u, 892u, 2221u, 304u, 679u, 278u, 6012u, 414u, 304u, 278u, 2246u, 310u, 278u, 5214u, 29889u, 13u, 1576u, 6012u, 414u, 892u, 2221u, 304u};
static constexpr uint16_t kP04Input[] = {1u, 18502u, 898u, 278u, 1833u, 3699u, 29892u, 263u, 12474u, 6520u};
static constexpr uint16_t kP04Expected[] = {11981u, 304u, 278u, 5720u, 310u, 476u, 352u, 273u, 29892u, 988u, 278u, 5720u, 338u, 5982u, 29889u, 13u, 1576u, 5720u, 338u, 5982u, 297u, 278u, 476u, 352u};
static constexpr uint16_t kP05Input[] = {1u, 319u, 16010u, 5722u, 8910u, 7120u, 278u, 281u, 8491u, 1434u};
static constexpr uint16_t kP05Expected[] = {15476u, 278u, 21387u, 29889u, 13u, 1576u, 319u, 2477u, 21387u, 29889u, 13u, 1576u, 21387u, 471u, 5130u, 297u, 278u, 1959u, 2602u, 29889u, 13u, 1576u, 21387u, 471u};

static constexpr ProofPrompt kProofPrompts[] = {
  {"p01", kP01Input, 6u, kP01Expected, 24u},
  {"p02", kP02Input, 8u, kP02Expected, 24u},
  {"p03", kP03Input, 7u, kP03Expected, 24u},
  {"p04", kP04Input, 10u, kP04Expected, 24u},
  {"p05", kP05Input, 10u, kP05Expected, 24u},
};

static constexpr uint32_t kProofPromptCount = 5u;

}  // namespace paretoq
