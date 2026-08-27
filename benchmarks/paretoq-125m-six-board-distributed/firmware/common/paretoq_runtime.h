#pragma once

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(ARDUINO)
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#define PQ_COOPERATIVE_YIELD() vTaskDelay(1)
#else
#define PQ_COOPERATIVE_YIELD() ((void)0)
#endif

#if defined(__GNUC__)
#define PQ_ALWAYS_INLINE __attribute__((always_inline)) inline
#else
#define PQ_ALWAYS_INLINE inline
#endif

namespace paretoq {

constexpr uint32_t kHiddenSize = 576;
constexpr uint32_t kIntermediateSize = 1536;
constexpr uint32_t kAttentionHeads = 9;
constexpr uint32_t kKvHeads = 3;
constexpr uint32_t kHeadDim = 64;
constexpr uint32_t kWeightsPerByte = 4;
constexpr uint32_t kPackedCodeCount = 256;

struct QuantMatrix {
  const uint8_t* codes;
  const uint16_t* low_scales_bf16;
  const uint16_t* high_scales_bf16;
  uint32_t rows;
  uint32_t columns;
  uint32_t row_bytes;
};

struct LayerWeights {
  QuantMatrix query;
  QuantMatrix key;
  QuantMatrix value;
  QuantMatrix attention_output;
  QuantMatrix gate;
  QuantMatrix up;
  QuantMatrix down;
  const uint16_t* input_norm_bf16;
  const uint16_t* post_attention_norm_bf16;
};

struct LayerScratch {
  float* normalized;
  float* query;
  float* key;
  float* value;
  float* attention;
  float* projection;
  float* gate;
  float* up;
  float* scores;
  float* dot_lookup;
};

PQ_ALWAYS_INLINE float bf16_to_float(uint16_t value) {
  uint32_t bits = static_cast<uint32_t>(value) << 16;
  float result;
  memcpy(&result, &bits, sizeof(result));
  return result;
}

PQ_ALWAYS_INLINE uint16_t float_to_bf16(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  const uint32_t rounding_bias = 0x7FFFu + ((bits >> 16) & 1u);
  return static_cast<uint16_t>((bits + rounding_bias) >> 16);
}

PQ_ALWAYS_INLINE uint8_t weight_code(uint8_t packed, uint32_t index) {
  return static_cast<uint8_t>((packed >> (index * 2u)) & 0x03u);
}

inline void init_weight_lut(uint8_t lut[kPackedCodeCount][kWeightsPerByte]) {
  for (uint32_t code = 0; code < kPackedCodeCount; ++code) {
    for (uint32_t lane = 0; lane < kWeightsPerByte; ++lane) {
      lut[code][lane] = weight_code(static_cast<uint8_t>(code), lane);
    }
  }
}

PQ_ALWAYS_INLINE void dot_group_regular(
    uint8_t packed, const float* input, uint32_t count, float& low_sum, float& high_sum) {
  for (uint32_t lane = 0; lane < count; ++lane) {
    const uint8_t code = weight_code(packed, lane);
    if (code == 0) high_sum -= input[lane];
    else if (code == 1) low_sum -= input[lane];
    else if (code == 2) low_sum += input[lane];
    else high_sum += input[lane];
  }
}

PQ_ALWAYS_INLINE void dot_group_lut(
    const uint8_t codes[kWeightsPerByte], const float* input, uint32_t count,
    float& low_sum, float& high_sum) {
  for (uint32_t lane = 0; lane < count; ++lane) {
    const uint8_t code = codes[lane];
    if (code == 0) high_sum -= input[lane];
    else if (code == 1) low_sum -= input[lane];
    else if (code == 2) low_sum += input[lane];
    else high_sum += input[lane];
  }
}

inline void matvec_regular_rows(const QuantMatrix& matrix, const float* input,
                                float* output, uint32_t row_begin,
                                uint32_t row_end) {
  const uint32_t groups = (matrix.columns + kWeightsPerByte - 1) / kWeightsPerByte;
  if (row_end > matrix.rows) row_end = matrix.rows;
  for (uint32_t row = row_begin; row < row_end; ++row) {
    const uint8_t* codes = matrix.codes + static_cast<size_t>(row) * matrix.row_bytes;
    float low_sum = 0.0f;
    float high_sum = 0.0f;
    for (uint32_t group = 0; group < groups; ++group) {
      const uint32_t first = group * kWeightsPerByte;
      const uint32_t remaining = matrix.columns - first;
      const uint32_t count = remaining < kWeightsPerByte ? remaining : kWeightsPerByte;
      dot_group_regular(codes[group], input + first, count, low_sum, high_sum);
    }
    output[row] = low_sum * bf16_to_float(matrix.low_scales_bf16[row]) +
        high_sum * bf16_to_float(matrix.high_scales_bf16[row]);
    if (((row - row_begin) & 0xFFu) == 0xFFu) PQ_COOPERATIVE_YIELD();
  }
}

inline void matvec_regular(const QuantMatrix& matrix, const float* input, float* output) {
  matvec_regular_rows(matrix, input, output, 0, matrix.rows);
}

using FastMatvecExecutor = bool (*)(
    const QuantMatrix& matrix, const float* input, float* output);

inline FastMatvecExecutor& fast_matvec_executor_slot() {
  static FastMatvecExecutor executor = nullptr;
  return executor;
}

inline void set_fast_matvec_executor(FastMatvecExecutor executor) {
  fast_matvec_executor_slot() = executor;
}

inline void build_dot_lookup(
    const float* input,
    uint32_t columns,
    const uint8_t weight_lut[kPackedCodeCount][kWeightsPerByte],
    float* dot_lookup) {
  const uint32_t groups = (columns + kWeightsPerByte - 1) / kWeightsPerByte;
  for (uint32_t group = 0; group < groups; ++group) {
    const uint32_t first = group * kWeightsPerByte;
    const uint32_t remaining = columns - first;
    const uint32_t count = remaining < kWeightsPerByte ? remaining : kWeightsPerByte;
    float* table = dot_lookup + static_cast<size_t>(group) * kPackedCodeCount * 2u;
    for (uint32_t code = 0; code < kPackedCodeCount; ++code) {
      float low_sum = 0.0f;
      float high_sum = 0.0f;
      dot_group_lut(weight_lut[code], input + first, count, low_sum, high_sum);
      table[code * 2u] = low_sum;
      table[code * 2u + 1u] = high_sum;
    }
  }
}

inline void matvec_fast(
    const QuantMatrix& matrix, const float* dot_lookup, float* output) {
  const uint32_t groups = (matrix.columns + kWeightsPerByte - 1) / kWeightsPerByte;
  for (uint32_t row = 0; row < matrix.rows; ++row) {
    const uint8_t* codes = matrix.codes + static_cast<size_t>(row) * matrix.row_bytes;
    float low_sum = 0.0f;
    float high_sum = 0.0f;
    for (uint32_t group = 0; group < groups; ++group) {
      const size_t index = (static_cast<size_t>(group) * kPackedCodeCount + codes[group]) * 2u;
      low_sum += dot_lookup[index];
      high_sum += dot_lookup[index + 1u];
    }
    output[row] = low_sum * bf16_to_float(matrix.low_scales_bf16[row]) +
        high_sum * bf16_to_float(matrix.high_scales_bf16[row]);
    if ((row & 0xFFu) == 0xFFu) PQ_COOPERATIVE_YIELD();
  }
}

inline void rms_norm(
    const float* input, const uint16_t* weight_bf16, uint32_t count, float epsilon, float* output) {
  float square_sum = 0.0f;
  for (uint32_t index = 0; index < count; ++index) {
    square_sum += input[index] * input[index];
  }
  const float inverse = 1.0f / sqrtf(square_sum / static_cast<float>(count) + epsilon);
  for (uint32_t index = 0; index < count; ++index) {
    output[index] = input[index] * inverse * bf16_to_float(weight_bf16[index]);
  }
}

PQ_ALWAYS_INLINE float silu(float value) {
  return value / (1.0f + expf(-value));
}

inline void float_to_bf16_vector(const float* input, uint16_t* output, uint32_t count) {
  for (uint32_t index = 0; index < count; ++index) {
    output[index] = float_to_bf16(input[index]);
  }
}

inline void bf16_to_float_vector(const uint16_t* input, float* output, uint32_t count) {
  for (uint32_t index = 0; index < count; ++index) {
    output[index] = bf16_to_float(input[index]);
  }
}

inline void round_to_bf16_inplace(float* values, uint32_t count) {
  for (uint32_t index = 0; index < count; ++index) {
    values[index] = bf16_to_float(float_to_bf16(values[index]));
  }
}

inline void apply_rope(float* query, float* key, uint32_t position) {
  constexpr uint32_t half_head = kHeadDim / 2;
  for (uint32_t head = 0; head < kAttentionHeads; ++head) {
    float* query_head = query + head * kHeadDim;
    for (uint32_t index = 0; index < half_head; ++index) {
      const float frequency = powf(10000.0f, -2.0f * static_cast<float>(index) /
          static_cast<float>(kHeadDim));
      const float angle = static_cast<float>(position) * frequency;
      const float cosine = cosf(angle);
      const float sine = sinf(angle);
      const float first = query_head[index];
      const float second = query_head[index + half_head];
      query_head[index] = first * cosine - second * sine;
      query_head[index + half_head] = second * cosine + first * sine;
    }
  }
  for (uint32_t head = 0; head < kKvHeads; ++head) {
    float* key_head = key + head * kHeadDim;
    for (uint32_t index = 0; index < half_head; ++index) {
      const float frequency = powf(10000.0f, -2.0f * static_cast<float>(index) /
          static_cast<float>(kHeadDim));
      const float angle = static_cast<float>(position) * frequency;
      const float cosine = cosf(angle);
      const float sine = sinf(angle);
      const float first = key_head[index];
      const float second = key_head[index + half_head];
      key_head[index] = first * cosine - second * sine;
      key_head[index + half_head] = second * cosine + first * sine;
    }
  }
  round_to_bf16_inplace(query, kHiddenSize);
  round_to_bf16_inplace(key, kKvHeads * kHeadDim);
}

inline bool grouped_query_attention(
    const float* query,
    const float* key,
    const float* value,
    uint16_t* key_cache_bf16,
    uint16_t* value_cache_bf16,
    uint32_t position,
    uint32_t context_tokens,
    float* scores,
    float* output) {
  if (position >= context_tokens) return false;
  constexpr uint32_t kv_width = kKvHeads * kHeadDim;
  float_to_bf16_vector(key, key_cache_bf16 + static_cast<size_t>(position) * kv_width, kv_width);
  float_to_bf16_vector(value, value_cache_bf16 + static_cast<size_t>(position) * kv_width, kv_width);
  memset(output, 0, sizeof(float) * kHiddenSize);
  constexpr uint32_t queries_per_kv = kAttentionHeads / kKvHeads;
  constexpr float attention_scale = 0.125f;
  for (uint32_t query_head_index = 0; query_head_index < kAttentionHeads; ++query_head_index) {
    const uint32_t kv_head_index = query_head_index / queries_per_kv;
    const float* query_head = query + query_head_index * kHeadDim;
    float maximum = -INFINITY;
    for (uint32_t token = 0; token <= position; ++token) {
      const uint16_t* cached_key = key_cache_bf16 +
          static_cast<size_t>(token) * kv_width + kv_head_index * kHeadDim;
      float dot = 0.0f;
      for (uint32_t index = 0; index < kHeadDim; ++index) {
        dot += query_head[index] * bf16_to_float(cached_key[index]);
      }
      scores[token] = dot * attention_scale;
      if (scores[token] > maximum) maximum = scores[token];
    }
    float denominator = 0.0f;
    for (uint32_t token = 0; token <= position; ++token) {
      scores[token] = expf(scores[token] - maximum);
      denominator += scores[token];
    }
    const float inverse_denominator = 1.0f / denominator;
    float* output_head = output + query_head_index * kHeadDim;
    for (uint32_t token = 0; token <= position; ++token) {
      const float probability = scores[token] * inverse_denominator;
      const uint16_t* cached_value = value_cache_bf16 +
          static_cast<size_t>(token) * kv_width + kv_head_index * kHeadDim;
      for (uint32_t index = 0; index < kHeadDim; ++index) {
        output_head[index] += probability * bf16_to_float(cached_value[index]);
      }
    }
  }
  round_to_bf16_inplace(output, kHiddenSize);
  return true;
}

inline void project_regular(
    const QuantMatrix& matrix, const float* input, float* output) {
  matvec_regular(matrix, input, output);
  round_to_bf16_inplace(output, matrix.rows);
}

inline void project_fast(
    const QuantMatrix& matrix, const float* dot_lookup, float* output) {
  matvec_fast(matrix, dot_lookup, output);
  round_to_bf16_inplace(output, matrix.rows);
}

inline bool project_fast_parallel(
    const QuantMatrix& matrix, const float* input, float* output) {
  FastMatvecExecutor executor = fast_matvec_executor_slot();
  if (!executor || !executor(matrix, input, output)) return false;
  round_to_bf16_inplace(output, matrix.rows);
  return true;
}

inline bool run_layer_regular(
    const LayerWeights& weights,
    float* hidden,
    uint16_t* key_cache_bf16,
    uint16_t* value_cache_bf16,
    uint32_t position,
    uint32_t context_tokens,
    LayerScratch& scratch) {
  rms_norm(hidden, weights.input_norm_bf16, kHiddenSize, 1.0e-5f, scratch.normalized);
  round_to_bf16_inplace(scratch.normalized, kHiddenSize);
  project_regular(weights.query, scratch.normalized, scratch.query);
  project_regular(weights.key, scratch.normalized, scratch.key);
  project_regular(weights.value, scratch.normalized, scratch.value);
  apply_rope(scratch.query, scratch.key, position);
  if (!grouped_query_attention(
          scratch.query, scratch.key, scratch.value, key_cache_bf16, value_cache_bf16,
          position, context_tokens, scratch.scores, scratch.attention)) {
    return false;
  }
  project_regular(weights.attention_output, scratch.attention, scratch.projection);
  for (uint32_t index = 0; index < kHiddenSize; ++index) {
    hidden[index] = bf16_to_float(float_to_bf16(hidden[index] + scratch.projection[index]));
  }

  rms_norm(
      hidden, weights.post_attention_norm_bf16, kHiddenSize, 1.0e-5f, scratch.normalized);
  round_to_bf16_inplace(scratch.normalized, kHiddenSize);
  project_regular(weights.gate, scratch.normalized, scratch.gate);
  project_regular(weights.up, scratch.normalized, scratch.up);
  for (uint32_t index = 0; index < kIntermediateSize; ++index) {
    scratch.gate[index] = bf16_to_float(
        float_to_bf16(silu(scratch.gate[index]) * scratch.up[index]));
  }
  project_regular(weights.down, scratch.gate, scratch.projection);
  for (uint32_t index = 0; index < kHiddenSize; ++index) {
    hidden[index] = bf16_to_float(float_to_bf16(hidden[index] + scratch.projection[index]));
  }
  return true;
}

inline bool run_layer_fast(
    const LayerWeights& weights,
    float* hidden,
    uint16_t* key_cache_bf16,
    uint16_t* value_cache_bf16,
    uint32_t position,
    uint32_t context_tokens,
    const uint8_t weight_lut[kPackedCodeCount][kWeightsPerByte],
    LayerScratch& scratch) {
  rms_norm(hidden, weights.input_norm_bf16, kHiddenSize, 1.0e-5f, scratch.normalized);
  round_to_bf16_inplace(scratch.normalized, kHiddenSize);
  if (fast_matvec_executor_slot()) {
    if (!project_fast_parallel(weights.query, scratch.normalized, scratch.query) ||
        !project_fast_parallel(weights.key, scratch.normalized, scratch.key) ||
        !project_fast_parallel(weights.value, scratch.normalized, scratch.value)) {
      return false;
    }
  } else {
    build_dot_lookup(scratch.normalized, kHiddenSize, weight_lut, scratch.dot_lookup);
    project_fast(weights.query, scratch.dot_lookup, scratch.query);
    project_fast(weights.key, scratch.dot_lookup, scratch.key);
    project_fast(weights.value, scratch.dot_lookup, scratch.value);
  }
  apply_rope(scratch.query, scratch.key, position);
  if (!grouped_query_attention(
          scratch.query, scratch.key, scratch.value, key_cache_bf16, value_cache_bf16,
          position, context_tokens, scratch.scores, scratch.attention)) {
    return false;
  }
  if (fast_matvec_executor_slot()) {
    if (!project_fast_parallel(
            weights.attention_output, scratch.attention, scratch.projection)) {
      return false;
    }
  } else {
    build_dot_lookup(scratch.attention, kHiddenSize, weight_lut, scratch.dot_lookup);
    project_fast(weights.attention_output, scratch.dot_lookup, scratch.projection);
  }
  for (uint32_t index = 0; index < kHiddenSize; ++index) {
    hidden[index] = bf16_to_float(float_to_bf16(hidden[index] + scratch.projection[index]));
  }

  rms_norm(
      hidden, weights.post_attention_norm_bf16, kHiddenSize, 1.0e-5f, scratch.normalized);
  round_to_bf16_inplace(scratch.normalized, kHiddenSize);
  if (fast_matvec_executor_slot()) {
    if (!project_fast_parallel(weights.gate, scratch.normalized, scratch.gate) ||
        !project_fast_parallel(weights.up, scratch.normalized, scratch.up)) {
      return false;
    }
  } else {
    build_dot_lookup(scratch.normalized, kHiddenSize, weight_lut, scratch.dot_lookup);
    project_fast(weights.gate, scratch.dot_lookup, scratch.gate);
    project_fast(weights.up, scratch.dot_lookup, scratch.up);
  }
  for (uint32_t index = 0; index < kIntermediateSize; ++index) {
    scratch.gate[index] = bf16_to_float(
        float_to_bf16(silu(scratch.gate[index]) * scratch.up[index]));
  }
  if (fast_matvec_executor_slot()) {
    if (!project_fast_parallel(weights.down, scratch.gate, scratch.projection)) {
      return false;
    }
  } else {
    build_dot_lookup(scratch.gate, kIntermediateSize, weight_lut, scratch.dot_lookup);
    project_fast(weights.down, scratch.dot_lookup, scratch.projection);
  }
  for (uint32_t index = 0; index < kHiddenSize; ++index) {
    hidden[index] = bf16_to_float(float_to_bf16(hidden[index] + scratch.projection[index]));
  }
  return true;
}

}  // namespace paretoq
