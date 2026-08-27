#pragma once

#include <stdint.h>

namespace paretoq {

struct MatrixLocation {
  uint32_t code_offset;
  uint32_t low_scale_offset;
  uint32_t high_scale_offset;
  uint32_t rows;
  uint32_t columns;
  uint32_t row_bytes;
};

struct LayerLocation {
  uint32_t global_layer;
  MatrixLocation query;
  MatrixLocation key;
  MatrixLocation value;
  MatrixLocation attention_output;
  MatrixLocation gate;
  MatrixLocation up;
  MatrixLocation down;
  uint32_t input_norm_offset;
  uint32_t post_attention_norm_offset;
};

struct StageLocation {
  uint32_t stage;
  uint32_t layer_first;
  uint32_t layer_count;
  uint32_t layers_bytes;
  uint32_t vocab_flash_offset;
  uint32_t vocab_first;
  uint32_t vocab_count;
  uint32_t vocab_flash_rows;
  uint32_t vocab_psram_rows;
  uint32_t final_norm_offset;
  const LayerLocation* layers;
};

}  // namespace paretoq
