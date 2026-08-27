#include <Arduino.h>
#include <esp_heap_caps.h>
#include <esp_mac.h>
#include <esp_partition.h>
#include <esp_timer.h>
#include <driver/gpio.h>
#include <driver/spi_master.h>
#include <driver/spi_slave.h>
#include <freertos/queue.h>
#include <hal/gpio_ll.h>
#include <mbedtls/base64.h>

#include "../common/cluster_protocol.h"
#include "../common/paretoq_runtime.h"
#include "../generated/proof_prompts.h"
#include "../generated/stage0_layout.h"
#include "../generated/stage1_layout.h"
#include "../generated/stage2_layout.h"
#include "../generated/stage3_layout.h"
#include "../generated/stage4_layout.h"

using namespace paretoq;

namespace {

constexpr uint32_t kContextTokens = 34;
constexpr uint8_t kPipelineStreams = 5;
constexpr uint32_t kKvWidth = kKvHeads * kHeadDim;
constexpr uint8_t kRgbPin = 48;
constexpr uint32_t kSerialBaud = 921600;
constexpr int kInSck = 9;
constexpr int kInMosi = 10;
constexpr int kInMiso = 11;
constexpr int kInCs = 12;
constexpr int kInReady = 13;
constexpr int kOutMosi = 42;
constexpr int kOutMiso = 41;
constexpr int kOutCs = 40;
constexpr int kOutReady = 39;

const StageLocation* g_stage = nullptr;
bool g_transport_relay = false;
const esp_partition_t* g_model_partition = nullptr;
uint16_t* g_vocab_psram = nullptr;
uint16_t* g_key_cache = nullptr;
uint16_t* g_value_cache = nullptr;
float* g_hidden = nullptr;
LayerScratch g_scratch{};
uint8_t g_weight_lut[kPackedCodeCount][kWeightsPerByte];
bool g_ready = false;
bool g_bus_started = false;
spi_device_handle_t g_downstream = nullptr;
ClusterPacket* g_spi_request = nullptr;
ClusterPacket* g_spi_reply = nullptr;
ClusterPacket* g_command_response = nullptr;
uint16_t* g_transfer_hidden_bf16 = nullptr;
uint16_t* g_logits_hidden_bf16 = nullptr;
TaskHandle_t g_worker_task = nullptr;
TaskHandle_t g_logits_task = nullptr;
TaskHandle_t g_pipeline_receiver_task = nullptr;
TaskHandle_t g_fast_matvec_task = nullptr;
QueueHandle_t g_pipeline_receive_permits = nullptr;
QueueHandle_t g_pipeline_return_queue = nullptr;
SemaphoreHandle_t g_logits_done = nullptr;
SemaphoreHandle_t g_fast_matvec_done = nullptr;
volatile bool g_logits_job_ok = false;
uint32_t g_spi_sequence = 0;
uint32_t g_spi_errors = 0;
uint64_t g_spi_wall_us = 0;
float g_pending_logit = -INFINITY;
uint16_t g_pending_token = UINT16_MAX;
uint32_t g_load_expected = 0;
uint32_t g_load_received = 0;
bool g_load_active = false;
volatile uint32_t g_ring_rx_count = 0;
volatile uint32_t g_ring_tx_count = 0;
volatile uint32_t g_ring_last_sequence = 0;
volatile uint8_t g_ring_state = 0;
uint32_t g_ring_receive_timeout_ms = 600000;
volatile int32_t g_ring_last_error = 0;

struct FastMatvecJob {
  const QuantMatrix* matrix;
  const float* input;
  float* output;
  uint32_t row_begin;
  uint32_t row_end;
};

FastMatvecJob g_fast_matvec_job{};

struct PipelineStreamState {
  ClusterPacket packet;
  const ProofPrompt* prompt;
  uint16_t output[32];
  uint16_t token;
  uint16_t position;
  uint16_t output_count;
  uint8_t stream_id;
  bool active;
  bool exact;
  uint64_t started_us;
  uint64_t ttft_us;
  uint64_t finished_us;
  uint64_t local_compute_us;
  uint64_t remote_compute_us;
};

PipelineStreamState g_pipeline_streams[kPipelineStreams]{};

static constexpr StageLocation kTransportRelayLocation = {
    5u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, UINT32_MAX, nullptr};

void* allocate_psram(size_t bytes) {
  void* result = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (result) memset(result, 0, bytes);
  return result;
}

const StageLocation* stage_by_index(uint32_t stage) {
  static constexpr const StageLocation* locations[] = {&kStage0Location,
      &kStage1Location, &kStage2Location, &kStage3Location, &kStage4Location,
      &kTransportRelayLocation};
  return stage < 6 ? locations[stage] : nullptr;
}

int stage_from_mac() {
  uint8_t mac[6]{};
  esp_read_mac(mac, ESP_MAC_WIFI_STA);
  static constexpr uint8_t known[6][6] = {
      {0xE8, 0xF6, 0x0A, 0xA3, 0x6E, 0x98},
      {0x14, 0xC1, 0x9F, 0xDA, 0x49, 0xC8},
      {0x14, 0xC1, 0x9F, 0xDA, 0x31, 0x2C},
      {0x14, 0xC1, 0x9F, 0xD9, 0xF7, 0xA8},
      {0x14, 0xC1, 0x9F, 0xDB, 0x18, 0x54},
      {0x90, 0x70, 0x69, 0x19, 0xBD, 0xCC},
  };
  for (int stage = 0; stage < 6; ++stage) {
    if (memcmp(mac, known[stage], sizeof(mac)) == 0) return stage;
  }
  return -1;
}

void set_stage_color(uint32_t stage) {
  static constexpr uint32_t colors[6] = {
      0x180000, 0x181000, 0x001800, 0x001818, 0x000018, 0x100018};
  rgbLedWrite(kRgbPin, colors[stage] >> 16, (colors[stage] >> 8) & 0xFF,
      colors[stage] & 0xFF);
}

bool allocate_runtime() {
  if (g_transport_relay) return true;
  const size_t local_cache_words = static_cast<size_t>(g_stage->layer_count) *
      kContextTokens * kKvWidth * kPipelineStreams;
  g_key_cache = static_cast<uint16_t*>(allocate_psram(local_cache_words * sizeof(uint16_t)));
  g_value_cache = static_cast<uint16_t*>(allocate_psram(local_cache_words * sizeof(uint16_t)));
  const size_t vocab_psram_bytes =
      static_cast<size_t>(g_stage->vocab_psram_rows) * kHiddenSize * sizeof(uint16_t);
  g_vocab_psram = vocab_psram_bytes
      ? static_cast<uint16_t*>(allocate_psram(vocab_psram_bytes))
      : nullptr;
  g_hidden = static_cast<float*>(allocate_psram(kHiddenSize * sizeof(float)));
  g_transfer_hidden_bf16 = static_cast<uint16_t*>(
      allocate_psram(kHiddenSize * sizeof(uint16_t)));
  g_scratch.normalized = static_cast<float*>(allocate_psram(kHiddenSize * sizeof(float)));
  g_scratch.query = static_cast<float*>(allocate_psram(kHiddenSize * sizeof(float)));
  g_scratch.key = static_cast<float*>(allocate_psram(kKvWidth * sizeof(float)));
  g_scratch.value = static_cast<float*>(allocate_psram(kKvWidth * sizeof(float)));
  g_scratch.attention = static_cast<float*>(allocate_psram(kHiddenSize * sizeof(float)));
  g_scratch.projection = static_cast<float*>(allocate_psram(kHiddenSize * sizeof(float)));
  g_scratch.gate = static_cast<float*>(allocate_psram(kIntermediateSize * sizeof(float)));
  g_scratch.up = static_cast<float*>(allocate_psram(kIntermediateSize * sizeof(float)));
  g_scratch.scores = static_cast<float*>(allocate_psram(kContextTokens * sizeof(float)));
  g_scratch.dot_lookup = static_cast<float*>(allocate_psram(
      ((kIntermediateSize + kWeightsPerByte - 1) / kWeightsPerByte) *
      kPackedCodeCount * 2u * sizeof(float)));
  return g_key_cache && g_value_cache &&
      (g_stage->vocab_psram_rows == 0 || g_vocab_psram) && g_hidden &&
      g_transfer_hidden_bf16 && g_scratch.normalized &&
      g_scratch.query && g_scratch.key && g_scratch.value && g_scratch.attention &&
      g_scratch.projection && g_scratch.gate && g_scratch.up && g_scratch.scores &&
      g_scratch.dot_lookup;
}

void fast_matvec_service(void*) {
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    const FastMatvecJob job = g_fast_matvec_job;
    if (job.matrix && job.input && job.output) {
      matvec_regular_rows(
          *job.matrix, job.input, job.output, job.row_begin, job.row_end);
    }
    xSemaphoreGive(g_fast_matvec_done);
  }
}

bool dual_core_fast_matvec(
    const QuantMatrix& matrix, const float* input, float* output) {
  if (!g_fast_matvec_task || !g_fast_matvec_done) return false;
  while (xSemaphoreTake(g_fast_matvec_done, 0) == pdTRUE) {}
  const uint32_t split = matrix.rows / 2u;
  g_fast_matvec_job = FastMatvecJob{
      &matrix, input, output, split, matrix.rows};
  xTaskNotifyGive(g_fast_matvec_task);
  matvec_regular_rows(matrix, input, output, 0, split);
  return xSemaphoreTake(g_fast_matvec_done, pdMS_TO_TICKS(600000)) == pdTRUE;
}

bool start_fast_matvec_executor() {
  g_fast_matvec_done = xSemaphoreCreateBinary();
  if (!g_fast_matvec_done) return false;
  const BaseType_t helper_core = g_stage && g_stage->stage == 0 ? 0 : 1;
  if (xTaskCreatePinnedToCore(fast_matvec_service, "pq-matvec-fast", 4096,
          nullptr, 2, &g_fast_matvec_task, helper_core) != pdPASS) {
    return false;
  }
  set_fast_matvec_executor(dual_core_fast_matvec);
  return true;
}

QuantMatrix bind_matrix(
    const uint8_t* mapped, uint32_t map_offset, const MatrixLocation& location) {
  return QuantMatrix{mapped + (location.code_offset - map_offset),
      reinterpret_cast<const uint16_t*>(mapped + (location.low_scale_offset - map_offset)),
      reinterpret_cast<const uint16_t*>(mapped + (location.high_scale_offset - map_offset)),
      location.rows, location.columns, location.row_bytes};
}

LayerWeights bind_layer(
    const uint8_t* mapped, uint32_t map_offset, const LayerLocation& location) {
  return LayerWeights{bind_matrix(mapped, map_offset, location.query),
      bind_matrix(mapped, map_offset, location.key),
      bind_matrix(mapped, map_offset, location.value),
      bind_matrix(mapped, map_offset, location.attention_output),
      bind_matrix(mapped, map_offset, location.gate),
      bind_matrix(mapped, map_offset, location.up),
      bind_matrix(mapped, map_offset, location.down),
      reinterpret_cast<const uint16_t*>(
          mapped + (location.input_norm_offset - map_offset)),
      reinterpret_cast<const uint16_t*>(
          mapped + (location.post_attention_norm_offset - map_offset))};
}

bool run_local_layers(bool fast_mode, uint8_t stream_id, uint32_t position,
                      float* hidden, uint64_t& compute_us) {
  if (stream_id >= kPipelineStreams) return false;
  if (position >= kContextTokens) return false;
  const uint64_t begin = esp_timer_get_time();
  const size_t cache_words = static_cast<size_t>(kContextTokens) * kKvWidth;
  for (uint32_t local = 0; local < g_stage->layer_count; ++local) {
    const LayerLocation& location = g_stage->layers[local];
    const uint32_t map_offset = location.query.code_offset;
    const uint32_t map_end = location.post_attention_norm_offset + kHiddenSize * sizeof(uint16_t);
    const void* mapped = nullptr;
    esp_partition_mmap_handle_t handle = 0;
    const esp_err_t map_result = esp_partition_mmap(g_model_partition, map_offset,
        map_end - map_offset, ESP_PARTITION_MMAP_DATA, &mapped, &handle);
    if (map_result != ESP_OK) return false;
    const LayerWeights weights = bind_layer(
        static_cast<const uint8_t*>(mapped), map_offset, location);
    const size_t stream_words = static_cast<size_t>(g_stage->layer_count) * cache_words;
    uint16_t* key = g_key_cache + stream_id * stream_words + local * cache_words;
    uint16_t* value = g_value_cache + stream_id * stream_words + local * cache_words;
    const bool ok = fast_mode
        ? run_layer_fast(weights, hidden, key, value, position, kContextTokens,
              g_weight_lut, g_scratch)
        : run_layer_regular(weights, hidden, key, value, position, kContextTokens,
              g_scratch);
    esp_partition_munmap(handle);
    if (!ok) return false;
    // The full stage is several seconds of continuous arithmetic. Give the
    // pinned core's idle task one tick between layers without changing math.
    vTaskDelay(1);
  }
  if (g_stage->stage == 4 && g_stage->final_norm_offset != UINT32_MAX) {
    const void* mapped = nullptr;
    esp_partition_mmap_handle_t handle = 0;
    const esp_err_t result = esp_partition_mmap(g_model_partition,
        g_stage->final_norm_offset, kHiddenSize * sizeof(uint16_t),
        ESP_PARTITION_MMAP_DATA, &mapped, &handle);
    if (result != ESP_OK) return false;
    rms_norm(hidden, static_cast<const uint16_t*>(mapped), kHiddenSize, 1.0e-5f,
        g_scratch.normalized);
    round_to_bf16_inplace(g_scratch.normalized, kHiddenSize);
    memcpy(hidden, g_scratch.normalized, kHiddenSize * sizeof(float));
    esp_partition_munmap(handle);
  }
  compute_us = esp_timer_get_time() - begin;
  return true;
}

bool owns_token(uint16_t token) {
  return token >= g_stage->vocab_first &&
      token < g_stage->vocab_first + g_stage->vocab_count;
}

bool local_embedding(uint16_t token, uint16_t* output) {
  if (!owns_token(token)) return false;
  const uint32_t local = token - g_stage->vocab_first;
  if (local < g_stage->vocab_flash_rows) {
    const uint32_t offset = g_stage->vocab_flash_offset +
        local * kHiddenSize * sizeof(uint16_t);
    const void* mapped = nullptr;
    esp_partition_mmap_handle_t handle = 0;
    if (esp_partition_mmap(g_model_partition, offset, kHiddenSize * sizeof(uint16_t),
            ESP_PARTITION_MMAP_DATA, &mapped, &handle) != ESP_OK) {
      return false;
    }
    memcpy(output, mapped, kHiddenSize * sizeof(uint16_t));
    esp_partition_munmap(handle);
  } else {
    const size_t psram_row = local - g_stage->vocab_flash_rows;
    memcpy(output, g_vocab_psram + psram_row * kHiddenSize,
        kHiddenSize * sizeof(uint16_t));
  }
  return true;
}

void update_best_row(const uint16_t* row, uint16_t token, const float* hidden,
                     float& best_logit, uint16_t& best_token) {
  float logit = 0.0f;
  for (uint32_t column = 0; column < kHiddenSize; ++column) {
    logit += hidden[column] * bf16_to_float(row[column]);
  }
  // The checkpoint LM head emits BF16 logits. Preserve that boundary before
  // the global shard tie-break so distributed argmax matches Transformers.
  logit = bf16_to_float(float_to_bf16(logit));
  if (logit > best_logit || (logit == best_logit && token < best_token)) {
    best_logit = logit;
    best_token = token;
  }
}

bool local_argmax(const uint16_t* hidden_bf16, float& best_logit, uint16_t& best_token) {
  bf16_to_float_vector(hidden_bf16, g_scratch.normalized, kHiddenSize);
  best_logit = -INFINITY;
  best_token = UINT16_MAX;
  constexpr uint32_t rows_per_map = 256;
  for (uint32_t first = 0; first < g_stage->vocab_flash_rows; first += rows_per_map) {
    const uint32_t count = min(rows_per_map, g_stage->vocab_flash_rows - first);
    const uint32_t offset = g_stage->vocab_flash_offset +
        first * kHiddenSize * sizeof(uint16_t);
    const size_t bytes = static_cast<size_t>(count) * kHiddenSize * sizeof(uint16_t);
    const void* mapped = nullptr;
    esp_partition_mmap_handle_t handle = 0;
    if (esp_partition_mmap(g_model_partition, offset, bytes, ESP_PARTITION_MMAP_DATA,
            &mapped, &handle) != ESP_OK) {
      return false;
    }
    const uint16_t* rows = static_cast<const uint16_t*>(mapped);
    for (uint32_t row = 0; row < count; ++row) {
      update_best_row(rows + static_cast<size_t>(row) * kHiddenSize,
          static_cast<uint16_t>(g_stage->vocab_first + first + row),
          g_scratch.normalized, best_logit, best_token);
      if ((row & 0xFFu) == 0xFFu) vTaskDelay(1);
    }
    esp_partition_munmap(handle);
  }
  for (uint32_t row = 0; row < g_stage->vocab_psram_rows; ++row) {
    update_best_row(g_vocab_psram + static_cast<size_t>(row) * kHiddenSize,
        static_cast<uint16_t>(g_stage->vocab_first + g_stage->vocab_flash_rows + row),
        g_scratch.normalized, best_logit, best_token);
    if ((row & 0xFFu) == 0xFFu) vTaskDelay(1);
  }
  return true;
}

void reset_local_cache() {
  const size_t words = static_cast<size_t>(g_stage->layer_count) *
      kContextTokens * kKvWidth * kPipelineStreams;
  memset(g_key_cache, 0, words * sizeof(uint16_t));
  memset(g_value_cache, 0, words * sizeof(uint16_t));
  g_pending_logit = -INFINITY;
  g_pending_token = UINT16_MAX;
}

int outgoing_sclk() {
  // Purple COM7 (stage 1) and red COM11 (stage 4) were proven on GPIO6.
  return g_stage->stage == 1 || g_stage->stage == 4 ? 6 : 2;
}

bool wait_pin_level(int pin, int level, uint64_t timeout_us) {
  const uint64_t started = esp_timer_get_time();
  uint32_t spins = 0;
  while (gpio_get_level(static_cast<gpio_num_t>(pin)) != level) {
    if (esp_timer_get_time() - started > timeout_us) return false;
    // Long waits occur while another ring stage computes. Yield periodically
    // so the pinned SPI task cannot starve the FreeRTOS idle watchdog.
    if (++spins % 500 == 0) vTaskDelay(1);
    else delayMicroseconds(2);
  }
  return true;
}

void incoming_ready(bool ready) {
  gpio_set_level(static_cast<gpio_num_t>(kInReady), ready ? 1 : 0);
}

bool init_ring_links() {
  gpio_set_direction(static_cast<gpio_num_t>(kInReady), GPIO_MODE_OUTPUT);
  incoming_ready(false);
  gpio_set_direction(static_cast<gpio_num_t>(kOutReady), GPIO_MODE_INPUT);
  gpio_set_pull_mode(static_cast<gpio_num_t>(kOutReady), GPIO_PULLDOWN_ONLY);

  spi_bus_config_t incoming = {};
  incoming.mosi_io_num = kInMosi;
  incoming.miso_io_num = kInMiso;
  incoming.sclk_io_num = kInSck;
  incoming.max_transfer_sz = sizeof(ClusterPacket);
  spi_slave_interface_config_t slave = {};
  slave.mode = 0;
  slave.spics_io_num = kInCs;
  slave.queue_size = 1;
  if (spi_slave_initialize(SPI2_HOST, &incoming, &slave, SPI_DMA_CH_AUTO) != ESP_OK) {
    return false;
  }

  spi_bus_config_t outgoing = {};
  outgoing.mosi_io_num = kOutMosi;
  outgoing.miso_io_num = kOutMiso;
  outgoing.sclk_io_num = outgoing_sclk();
  outgoing.max_transfer_sz = sizeof(ClusterPacket);
  if (spi_bus_initialize(SPI3_HOST, &outgoing, SPI_DMA_CH_AUTO) != ESP_OK) return false;
  spi_device_interface_config_t device = {};
  device.clock_speed_hz = kClusterSpiHz;
  device.mode = 0;
  device.spics_io_num = kOutCs;
  device.queue_size = 1;
  device.flags = SPI_DEVICE_HALFDUPLEX;
  return spi_bus_add_device(SPI3_HOST, &device, &g_downstream) == ESP_OK;
}

bool send_downstream(const ClusterPacket* transmit) {
  if (!wait_pin_level(kOutReady, 1, 600000000)) {
    g_ring_last_error = -1001;
    return false;
  }
  spi_transaction_t transaction = {};
  transaction.length = sizeof(ClusterPacket) * 8;
  transaction.tx_buffer = transmit;
  const esp_err_t result = spi_device_transmit(g_downstream, &transaction);
  if (result != ESP_OK) {
    g_ring_last_error = static_cast<int32_t>(result);
    return false;
  }
  if (!wait_pin_level(kOutReady, 0, 5000000)) {
    g_ring_last_error = -1002;
    return false;
  }
  g_ring_last_error = 0;
  return true;
}

bool queue_incoming(spi_slave_transaction_t& transaction, ClusterPacket* receive) {
  memset(receive, 0, sizeof(*receive));
  memset(&transaction, 0, sizeof(transaction));
  transaction.length = sizeof(ClusterPacket) * 8;
  transaction.rx_buffer = receive;
  if (spi_slave_queue_trans(SPI2_HOST, &transaction, portMAX_DELAY) != ESP_OK) return false;
  incoming_ready(true);
  return true;
}

bool finish_incoming(uint32_t timeout_ms) {
  spi_slave_transaction_t* completed = nullptr;
  const bool ok = spi_slave_get_trans_result(
      SPI2_HOST, &completed, pdMS_TO_TICKS(timeout_ms)) == ESP_OK;
  incoming_ready(false);
  delayMicroseconds(500);
  return ok;
}

bool master_ring_transfer(const ClusterPacket* transmit, ClusterPacket* receive) {
  spi_slave_transaction_t incoming = {};
  if (!queue_incoming(incoming, receive)) {
    g_ring_last_error = -1101;
    return false;
  }
  const uint64_t started = esp_timer_get_time();
  const bool sent = send_downstream(transmit);
  const bool received = finish_incoming(g_ring_receive_timeout_ms);
  if (!received) g_ring_last_error = -1102;
  g_spi_wall_us += esp_timer_get_time() - started;
  return sent && received;
}

void pipeline_receiver_service(void*) {
  for (;;) {
    uint8_t permit = 0;
    if (xQueueReceive(g_pipeline_receive_permits, &permit, portMAX_DELAY) !=
        pdTRUE) {
      continue;
    }
    ClusterPacket received = {};
    spi_slave_transaction_t transaction = {};
    if (!queue_incoming(transaction, &received) ||
        !finish_incoming(600000)) {
      ++g_spi_errors;
      memset(&received, 0, sizeof(received));
    }
    xQueueSend(g_pipeline_return_queue, &received, portMAX_DELAY);
  }
}

bool master_send(uint8_t target, ClusterKind kind, ClusterMode mode, uint16_t position,
                 uint16_t token, const uint16_t* payload, uint16_t payload_words,
                 bool response_required, ClusterPacket* response) {
  memset(g_spi_request, 0, sizeof(*g_spi_request));
  g_spi_request->magic = kClusterMagic;
  g_spi_request->sequence = ++g_spi_sequence;
  g_spi_request->target_stage = target;
  g_spi_request->source_stage = 0;
  g_spi_request->kind = kind;
  g_spi_request->mode = mode;
  g_spi_request->position = position;
  g_spi_request->token = token;
  g_spi_request->payload_words = payload_words;
  if (payload_words) memcpy(g_spi_request->payload, payload, payload_words * sizeof(uint16_t));
  cluster_packet_seal(*g_spi_request);
  memset(g_spi_reply, 0, sizeof(*g_spi_reply));
  const bool transferred = master_ring_transfer(g_spi_request, g_spi_reply);
  const bool valid = transferred && cluster_packet_valid(*g_spi_reply);
  const bool sequence_ok = valid && g_spi_reply->sequence == g_spi_sequence;
  if (!transferred || !valid || !sequence_ok) {
    ++g_spi_errors;
    Serial.printf("MASTER_SEND_FAIL phase=transport target=%u kind=%u seq=%u "
                  "transferred=%u valid=%u reply_seq=%u source=%u reply_kind=%u "
                  "ring_error=%d out_ready=%d\n",
        target, static_cast<unsigned>(kind), g_spi_sequence,
        transferred ? 1 : 0, valid ? 1 : 0, g_spi_reply->sequence,
        g_spi_reply->source_stage, g_spi_reply->kind,
        static_cast<int>(g_ring_last_error),
        gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
    return false;
  }
  if (!response_required) return true;
  if (
      g_spi_reply->sequence != g_spi_sequence ||
      g_spi_reply->source_stage != target ||
      g_spi_reply->kind != kClusterReply) {
    ++g_spi_errors;
    Serial.printf("MASTER_SEND_FAIL phase=response target=%u kind=%u seq=%u "
                  "reply_seq=%u source=%u reply_kind=%u\n",
        target, static_cast<unsigned>(kind), g_spi_sequence,
        g_spi_reply->sequence, g_spi_reply->source_stage, g_spi_reply->kind);
    return false;
  }
  if (response) *response = *g_spi_reply;
  return true;
}

void prepare_worker_reply(const ClusterPacket& request, ClusterPacket& reply) {
  memset(&reply, 0, sizeof(reply));
  reply.magic = kClusterMagic;
  reply.sequence = request.sequence;
  reply.target_stage = 0;
  reply.source_stage = g_stage->stage;
  reply.kind = request.kind >= kClusterPipelineEmbedding &&
          request.kind <= kClusterPipelineLogits
      ? request.kind
      : kClusterReply;
  reply.mode = request.mode;
  reply.stream_id = request.stream_id;
  reply.position = request.position;
  memcpy(reply.reserved, request.reserved, sizeof(reply.reserved));
}

bool worker_process(const ClusterPacket& request, ClusterPacket& reply,
                     bool& response_required) {
  response_required = false;
  if (!cluster_packet_valid(request)) return true;
  if (g_transport_relay) return true;
  const bool targeted = request.target_stage == g_stage->stage;
  const bool broadcast = request.target_stage == kBroadcastStage;
  if (!targeted && !broadcast) return true;
  if (request.kind == kClusterReset && broadcast) {
    reset_local_cache();
    return true;
  }
  if (request.kind == kClusterStartLogits && broadcast && request.payload_words == kHiddenSize) {
    // Run the exact local LM-head scan on the other core.  The SPI service must
    // immediately re-arm its receiver so replies from earlier shards can pass
    // through this node while all vocabulary shards scan concurrently.
    while (xSemaphoreTake(g_logits_done, 0) == pdTRUE) {}
    memcpy(g_logits_hidden_bf16, request.payload,
        kHiddenSize * sizeof(uint16_t));
    g_logits_job_ok = false;
    xTaskNotifyGive(g_logits_task);
    return true;
  }
  if (!targeted) return true;
  prepare_worker_reply(request, reply);
  if (request.kind == kClusterPipelineEmbedding) {
    const uint64_t begin = esp_timer_get_time();
    if (request.stream_id >= kPipelineStreams ||
        !local_embedding(request.token, reply.payload)) {
      return false;
    }
    reply.payload_words = kHiddenSize;
    reply.compute_us = static_cast<uint32_t>(esp_timer_get_time() - begin);
  } else if ((request.kind == kClusterRunLayers ||
              request.kind == kClusterPipelineLayers) &&
             request.payload_words == kHiddenSize) {
    bf16_to_float_vector(request.payload, g_hidden, kHiddenSize);
    uint64_t compute_us = 0;
    const uint8_t stream_id = request.kind == kClusterPipelineLayers
        ? request.stream_id
        : 0;
    if (!run_local_layers(request.mode == kClusterFast, stream_id, request.position,
            g_hidden, compute_us)) {
      return false;
    }
    float_to_bf16_vector(g_hidden, reply.payload, kHiddenSize);
    reply.payload_words = kHiddenSize;
    reply.compute_us = static_cast<uint32_t>(compute_us);
  } else if (request.kind == kClusterPipelineLogits &&
             request.payload_words == kHiddenSize) {
    const uint64_t begin = esp_timer_get_time();
    memcpy(reply.payload, request.payload, kHiddenSize * sizeof(uint16_t));
    reply.payload_words = kHiddenSize;
    reply.best_logit = request.best_logit;
    reply.best_token = request.best_token;
    float local_best = -INFINITY;
    uint16_t local_token = UINT16_MAX;
    if (!local_argmax(request.payload, local_best, local_token)) return false;
    if (local_best > reply.best_logit ||
        (local_best == reply.best_logit && local_token < reply.best_token)) {
      reply.best_logit = local_best;
      reply.best_token = local_token;
    }
    reply.compute_us = static_cast<uint32_t>(esp_timer_get_time() - begin);
  } else if (request.kind == kClusterCollectLogits) {
    if (xSemaphoreTake(g_logits_done, pdMS_TO_TICKS(600000)) != pdTRUE ||
        !g_logits_job_ok) {
      return false;
    }
    reply.best_logit = g_pending_logit;
    reply.best_token = g_pending_token;
  } else if (request.kind == kClusterFetchEmbedding) {
    if (!local_embedding(request.token, reply.payload)) return false;
    reply.payload_words = kHiddenSize;
  } else {
    return false;
  }
  cluster_packet_seal(reply);
  response_required = true;
  return true;
}

void logits_service(void*) {
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    g_logits_job_ok = local_argmax(
        g_logits_hidden_bf16, g_pending_logit, g_pending_token);
    xSemaphoreGive(g_logits_done);
  }
}

void worker_service(void*) {
  for (;;) {
    g_ring_state = 1;  // incoming transaction queued
    spi_slave_transaction_t receive = {};
    if (!queue_incoming(receive, g_spi_request)) {
      g_ring_state = 5;
      continue;
    }
    if (!finish_incoming(600000)) {
      g_ring_state = 5;
      continue;
    }
    ++g_ring_rx_count;
    g_ring_last_sequence = g_spi_request->sequence;
    if (!cluster_packet_valid(*g_spi_request)) {
      // SPI peripheral initialization can clock one zero-filled transaction.
      // Consume it locally so it cannot circulate and occupy every hop.
      g_ring_state = 7;
      continue;
    }
    g_ring_state = 2;  // processing or forwarding
    bool response_required = false;
    const bool ok = worker_process(*g_spi_request, *g_spi_reply, response_required);
    if (!ok) ++g_spi_errors;
    if (!response_required) memcpy(g_spi_reply, g_spi_request, sizeof(*g_spi_reply));
    g_ring_state = 3;  // waiting for downstream receiver
    if (!send_downstream(g_spi_reply)) {
      ++g_spi_errors;
      g_ring_state = 6;
      continue;
    }
    ++g_ring_tx_count;
    g_ring_state = 4;
  }
}

uint8_t token_owner(uint16_t token) {
  for (uint8_t stage = 0; stage < 5; ++stage) {
    const StageLocation* location = stage_by_index(stage);
    if (token >= location->vocab_first &&
        token < location->vocab_first + location->vocab_count) {
      return stage;
    }
  }
  return kBroadcastStage;
}

bool master_embedding(uint16_t token, uint16_t* output) {
  const uint8_t owner = token_owner(token);
  if (owner == 0) return local_embedding(token, output);
  if (owner == kBroadcastStage) return false;
  ClusterPacket& response = *g_command_response;
  memset(&response, 0, sizeof(response));
  if (!master_send(owner, kClusterFetchEmbedding, kClusterFast, 0, token,
          nullptr, 0, true, &response) || response.payload_words != kHiddenSize) {
    return false;
  }
  memcpy(output, response.payload, kHiddenSize * sizeof(uint16_t));
  return true;
}

bool master_forward_layers(uint16_t token, uint16_t position, ClusterMode mode,
                           uint16_t* final_hidden, uint64_t& local_compute_us,
                           uint64_t& remote_compute_us) {
  uint16_t* hidden_bf16 = g_transfer_hidden_bf16;
  if (!master_embedding(token, hidden_bf16)) return false;
  bf16_to_float_vector(hidden_bf16, g_hidden, kHiddenSize);
  uint64_t compute_us = 0;
  if (!run_local_layers(mode == kClusterFast, 0, position, g_hidden, compute_us)) {
    return false;
  }
  local_compute_us += compute_us;
  float_to_bf16_vector(g_hidden, hidden_bf16, kHiddenSize);
  for (uint8_t stage = 1; stage < 5; ++stage) {
    ClusterPacket& response = *g_command_response;
    memset(&response, 0, sizeof(response));
    if (!master_send(stage, kClusterRunLayers, mode, position, token,
            hidden_bf16, kHiddenSize, true, &response) ||
        response.payload_words != kHiddenSize) {
      return false;
    }
    remote_compute_us += response.compute_us;
    memcpy(hidden_bf16, response.payload, kHiddenSize * sizeof(uint16_t));
  }
  memcpy(final_hidden, hidden_bf16, kHiddenSize * sizeof(uint16_t));
  return true;
}

bool master_begin_logits(const uint16_t* hidden, ClusterMode mode) {
  return master_send(kBroadcastStage, kClusterStartLogits, mode, 0, 0,
      hidden, kHiddenSize, false, nullptr);
}

bool master_select_token(const uint16_t* hidden, ClusterMode mode, uint16_t& selected) {
  if (!master_begin_logits(hidden, mode)) return false;
  float best_logit = -INFINITY;
  uint16_t best_token = UINT16_MAX;
  if (!local_argmax(hidden, best_logit, best_token)) return false;
  for (uint8_t stage = 1; stage < 5; ++stage) {
    ClusterPacket& response = *g_command_response;
    memset(&response, 0, sizeof(response));
    if (!master_send(stage, kClusterCollectLogits, mode, 0, 0,
            nullptr, 0, true, &response)) {
      return false;
    }
    if (response.best_logit > best_logit ||
        (response.best_logit == best_logit && response.best_token < best_token)) {
      best_logit = response.best_logit;
      best_token = response.best_token;
    }
  }
  selected = best_token;
  return selected != UINT16_MAX;
}

bool master_reset_cluster() {
  reset_local_cache();
  return master_send(kBroadcastStage, kClusterReset, kClusterFast, 0, 0,
      nullptr, 0, false, nullptr);
}

bool run_proof_prompt(const ProofPrompt& prompt, ClusterMode mode) {
  if (!master_reset_cluster()) {
    Serial.printf("ERR PROOF_RESET spi_errors=%u ready=%d\n", g_spi_errors,
        gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
    return false;
  }
  g_spi_wall_us = 0;
  g_spi_errors = 0;
  uint64_t local_compute_us = 0;
  uint64_t remote_compute_us = 0;
  uint16_t* final_hidden = g_transfer_hidden_bf16;
  uint16_t output[32]{};
  const uint64_t started = esp_timer_get_time();
  uint16_t position = 0;
  for (uint16_t index = 0; index < prompt.input_count; ++index, ++position) {
    if (!master_forward_layers(prompt.input_ids[index], position, mode, final_hidden,
            local_compute_us, remote_compute_us)) {
      Serial.printf("ERR PROOF_PREFILL index=%u token=%u spi_errors=%u ready=%d\n",
          index, prompt.input_ids[index], g_spi_errors,
          gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
      return false;
    }
  }
  if (!master_select_token(final_hidden, mode, output[0])) {
    Serial.printf("ERR PROOF_SELECT index=0 spi_errors=%u ready=%d\n", g_spi_errors,
        gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
    return false;
  }
  const uint64_t ttft_us = esp_timer_get_time() - started;
  for (uint16_t index = 1; index < prompt.output_count; ++index, ++position) {
    if (!master_forward_layers(output[index - 1], position, mode, final_hidden,
            local_compute_us, remote_compute_us) ||
        !master_select_token(final_hidden, mode, output[index])) {
      return false;
    }
  }
  const uint64_t total_us = esp_timer_get_time() - started;
  bool exact = true;
  for (uint16_t index = 0; index < prompt.output_count; ++index) {
    if (output[index] != prompt.expected_ids[index]) exact = false;
  }
  const uint64_t decode_us = total_us - ttft_us;
  const float decode_tps = prompt.output_count > 1 && decode_us
      ? static_cast<float>(prompt.output_count - 1) * 1000000.0f /
          static_cast<float>(decode_us)
      : 0.0f;
  Serial.printf("{\"prompt\":\"%s\",\"mode\":\"%s\",\"output_ids\":[",
      prompt.id, mode == kClusterFast ? "fast" : "regular");
  for (uint16_t index = 0; index < prompt.output_count; ++index) {
    if (index) Serial.print(',');
    Serial.print(output[index]);
  }
  Serial.printf("],\"exact\":%s,\"tokens\":%u,\"ttft_ms\":%.3f,"
                "\"prompt_to_finish_ms\":%.3f,\"decode_tps\":%.6f,"
                "\"local_compute_ms\":%.3f,\"remote_compute_ms\":%.3f,"
                "\"spi_ms\":%.3f,\"spi_errors\":%u}\n",
      exact ? "true" : "false", prompt.output_count, ttft_us / 1000.0,
      total_us / 1000.0, decode_tps, local_compute_us / 1000.0,
      remote_compute_us / 1000.0, g_spi_wall_us / 1000.0, g_spi_errors);
  return exact;
}

bool run_proof_suite(ClusterMode mode) {
  bool all_exact = true;
  for (uint32_t index = 0; index < kProofPromptCount; ++index) {
    if (!run_proof_prompt(kProofPrompts[index], mode)) {
      Serial.printf("ERR BENCH prompt=%s\n", kProofPrompts[index].id);
      all_exact = false;
      break;
    }
  }
  Serial.printf("BENCH_DONE mode=%s prompts=%u all_exact=%u\n",
      mode == kClusterFast ? "fast" : "regular", kProofPromptCount,
      all_exact ? 1 : 0);
  return all_exact;
}

struct PipelineTrialResult {
  bool ok;
  bool all_exact;
  uint8_t streams;
  uint16_t tokens;
  uint64_t wall_us;
  float aggregate_tps;
};

bool pipeline_prepare_token(PipelineStreamState& stream) {
  if (!stream.prompt) return false;
  const ProofPrompt& prompt = *stream.prompt;
  memset(&stream.packet, 0, sizeof(stream.packet));
  stream.packet.magic = kClusterMagic;
  stream.packet.mode = kClusterFast;
  stream.packet.stream_id = stream.stream_id;
  stream.packet.token = stream.token;
  stream.packet.position = stream.position;
  const uint8_t owner = token_owner(stream.token);
  if (owner == kBroadcastStage) return false;
  if (owner != 0) {
    stream.packet.target_stage = owner;
    stream.packet.kind = kClusterPipelineEmbedding;
    return true;
  }
  const uint64_t begin = esp_timer_get_time();
  if (!local_embedding(stream.token, stream.packet.payload)) return false;
  bf16_to_float_vector(stream.packet.payload, g_hidden, kHiddenSize);
  uint64_t compute_us = 0;
  if (!run_local_layers(true, stream.stream_id, stream.position, g_hidden,
          compute_us)) {
    return false;
  }
  float_to_bf16_vector(g_hidden, stream.packet.payload, kHiddenSize);
  stream.local_compute_us += esp_timer_get_time() - begin;
  stream.packet.payload_words = kHiddenSize;
  stream.packet.target_stage = 1;
  stream.packet.kind = kClusterPipelineLayers;
  return true;
}

bool pipeline_send(PipelineStreamState& stream) {
  stream.packet.magic = kClusterMagic;
  stream.packet.sequence = ++g_spi_sequence;
  stream.packet.source_stage = 0;
  stream.packet.stream_id = stream.stream_id;
  stream.packet.mode = kClusterFast;
  stream.packet.compute_us = 0;
  cluster_packet_seal(stream.packet);
  memcpy(g_spi_request, &stream.packet, sizeof(*g_spi_request));
  const uint8_t permit = 1;
  if (!g_pipeline_receive_permits ||
      xQueueSend(g_pipeline_receive_permits, &permit, 0) != pdTRUE) {
    ++g_spi_errors;
    return false;
  }
  if (!send_downstream(g_spi_request)) {
    ++g_spi_errors;
    return false;
  }
  return true;
}

bool pipeline_advance(PipelineStreamState& stream,
                      const ClusterPacket& returned) {
  if (!stream.prompt) return false;
  const ProofPrompt& prompt = *stream.prompt;
  if (!cluster_packet_valid(returned) ||
      returned.stream_id != stream.stream_id ||
      returned.sequence != stream.packet.sequence ||
      returned.kind != stream.packet.kind) {
    ++g_spi_errors;
    return false;
  }
  stream.remote_compute_us += returned.compute_us;
  stream.packet = returned;
  if (returned.kind == kClusterPipelineEmbedding) {
    if (returned.payload_words != kHiddenSize) return false;
    const uint64_t begin = esp_timer_get_time();
    bf16_to_float_vector(returned.payload, g_hidden, kHiddenSize);
    uint64_t compute_us = 0;
    if (!run_local_layers(true, stream.stream_id, stream.position, g_hidden,
            compute_us)) {
      return false;
    }
    float_to_bf16_vector(g_hidden, stream.packet.payload, kHiddenSize);
    stream.local_compute_us += esp_timer_get_time() - begin;
    stream.packet.payload_words = kHiddenSize;
    stream.packet.target_stage = 1;
    stream.packet.kind = kClusterPipelineLayers;
    return true;
  }
  if (returned.kind == kClusterPipelineLayers) {
    if (returned.payload_words != kHiddenSize || returned.source_stage < 1 ||
        returned.source_stage > 5) {
      return false;
    }
    if (returned.source_stage < 5) {
      stream.packet.target_stage = returned.source_stage + 1;
      return true;
    }
    if (stream.position < prompt.input_count - 1) {
      ++stream.position;
      stream.token = prompt.input_ids[stream.position];
      return pipeline_prepare_token(stream);
    }
    const uint64_t begin = esp_timer_get_time();
    float best_logit = -INFINITY;
    uint16_t best_token = UINT16_MAX;
    if (!local_argmax(returned.payload, best_logit, best_token)) return false;
    stream.local_compute_us += esp_timer_get_time() - begin;
    stream.packet.best_logit = best_logit;
    stream.packet.best_token = best_token;
    stream.packet.target_stage = 1;
    stream.packet.kind = kClusterPipelineLogits;
    return true;
  }
  if (returned.kind == kClusterPipelineLogits) {
    if (returned.payload_words != kHiddenSize || returned.source_stage < 1 ||
        returned.source_stage > 5) {
      return false;
    }
    if (returned.source_stage < 5) {
      stream.packet.target_stage = returned.source_stage + 1;
      return true;
    }
    if (stream.output_count >= prompt.output_count ||
        returned.best_token == UINT16_MAX) {
      return false;
    }
    stream.output[stream.output_count++] = returned.best_token;
    if (stream.output_count == 1) {
      stream.ttft_us = esp_timer_get_time() - stream.started_us;
    }
    if (stream.output_count == prompt.output_count) {
      stream.finished_us = esp_timer_get_time();
      stream.active = false;
      stream.exact = true;
      for (uint16_t index = 0; index < prompt.output_count; ++index) {
        if (stream.output[index] != prompt.expected_ids[index]) {
          stream.exact = false;
        }
      }
      return true;
    }
    stream.token = returned.best_token;
    ++stream.position;
    return pipeline_prepare_token(stream);
  }
  return false;
}

void pipeline_print_stream(const char* trial, const PipelineStreamState& stream) {
  Serial.printf("{\"event\":\"interleave_stream\",\"trial\":\"%s\","
                "\"prompt\":\"%s\",\"stream\":%u,\"output_ids\":[",
      trial, stream.prompt->id, stream.stream_id);
  for (uint16_t index = 0; index < stream.output_count; ++index) {
    if (index) Serial.print(',');
    Serial.print(stream.output[index]);
  }
  Serial.printf("],\"exact\":%s,\"tokens\":%u,\"ttft_ms\":%.3f,"
                "\"prompt_to_finish_ms\":%.3f,\"local_compute_ms\":%.3f,"
                "\"remote_compute_ms\":%.3f}\n",
      stream.exact ? "true" : "false", stream.output_count,
      stream.ttft_us / 1000.0,
      (stream.finished_us - stream.started_us) / 1000.0,
      stream.local_compute_us / 1000.0, stream.remote_compute_us / 1000.0);
}

PipelineTrialResult run_pipeline_trial(const ProofPrompt& prompt,
                                       uint8_t stream_count,
                                       const char* trial,
                                       bool distinct_prompts = false) {
  PipelineTrialResult result{false, false, stream_count, 0, 0, 0.0f};
  if (stream_count == 0 || stream_count > kPipelineStreams ||
      !master_reset_cluster()) {
    return result;
  }
  g_spi_errors = 0;
  const uint64_t wall_begin = esp_timer_get_time();
  for (uint8_t id = 0; id < stream_count; ++id) {
    PipelineStreamState& stream = g_pipeline_streams[id];
    memset(&stream, 0, sizeof(stream));
    stream.prompt = distinct_prompts ? &kProofPrompts[id] : &prompt;
    stream.stream_id = id;
    stream.token = stream.prompt->input_ids[0];
    stream.active = true;
    stream.started_us = wall_begin;
  }

  uint8_t pending = 0;
  ClusterPacket stale = {};
  while (xQueueReceive(g_pipeline_return_queue, &stale, 0) == pdTRUE) {}

  for (uint8_t id = 0; id < stream_count; ++id) {
    if (!pipeline_prepare_token(g_pipeline_streams[id]) ||
        !pipeline_send(g_pipeline_streams[id])) return result;
    ++pending;
  }

  while (pending) {
    ClusterPacket returned = {};
    if (xQueueReceive(g_pipeline_return_queue, &returned,
                     pdMS_TO_TICKS(600000)) != pdTRUE) {
      ++g_spi_errors;
      return result;
    }
    --pending;
    const uint8_t id = returned.stream_id;
    if (id >= stream_count) {
      ++g_spi_errors;
      return result;
    }
    memcpy(g_command_response, &returned, sizeof(*g_command_response));
    PipelineStreamState& stream = g_pipeline_streams[id];
    if (!pipeline_advance(stream, *g_command_response)) return result;
    if (stream.active) {
      if (!pipeline_send(stream)) return result;
      ++pending;
    }
  }

  const uint64_t wall_end = esp_timer_get_time();
  result.ok = g_spi_errors == 0;
  result.all_exact = true;
  result.wall_us = wall_end - wall_begin;
  result.tokens = static_cast<uint16_t>(stream_count * prompt.output_count);
  result.aggregate_tps = result.wall_us
      ? static_cast<float>(result.tokens) * 1000000.0f /
          static_cast<float>(result.wall_us)
      : 0.0f;
  for (uint8_t id = 0; id < stream_count; ++id) {
    pipeline_print_stream(trial, g_pipeline_streams[id]);
    result.all_exact = result.all_exact && g_pipeline_streams[id].exact;
  }
  Serial.printf("{\"event\":\"interleave_trial\",\"trial\":\"%s\","
                "\"streams\":%u,\"tokens\":%u,\"wall_ms\":%.3f,"
                "\"aggregate_tok_s\":%.6f,\"all_exact\":%s,"
                "\"spi_errors\":%u}\n",
      trial, stream_count, result.tokens, result.wall_us / 1000.0,
      result.aggregate_tps, result.all_exact ? "true" : "false", g_spi_errors);
  return result;
}

uint32_t payload_digest(const uint16_t* payload, uint16_t words) {
  const uint8_t* bytes = reinterpret_cast<const uint8_t*>(payload);
  uint32_t hash = 2166136261u;
  for (size_t index = 0; index < static_cast<size_t>(words) * sizeof(uint16_t);
       ++index) {
    hash ^= bytes[index];
    hash *= 16777619u;
  }
  return hash;
}

bool prepare_chaincheck_input(uint16_t token, uint16_t* output) {
  if (!local_embedding(token, output)) return false;
  bf16_to_float_vector(output, g_hidden, kHiddenSize);
  uint64_t compute_us = 0;
  if (!run_local_layers(true, 0, 0, g_hidden, compute_us)) return false;
  float_to_bf16_vector(g_hidden, output, kHiddenSize);
  return true;
}

bool run_chain_prefix_check(uint8_t max_stop = 5) {
  const uint16_t token = kProofPrompts[0].input_ids[0];
  bool all_equal = true;
  for (uint8_t stop = 1; stop <= max_stop; ++stop) {
    if (!master_reset_cluster() ||
        !prepare_chaincheck_input(token, g_transfer_hidden_bf16)) {
      return false;
    }
    const uint32_t targeted_input =
        payload_digest(g_transfer_hidden_bf16, kHiddenSize);
    for (uint8_t stage = 1; stage <= stop; ++stage) {
      ClusterPacket& response = *g_command_response;
      if (!master_send(stage, kClusterRunLayers, kClusterFast, 0, token,
              g_transfer_hidden_bf16, kHiddenSize, true, &response) ||
          response.payload_words != kHiddenSize) {
        return false;
      }
      memcpy(g_transfer_hidden_bf16, response.payload,
             kHiddenSize * sizeof(uint16_t));
    }
    const uint32_t targeted = payload_digest(g_transfer_hidden_bf16, kHiddenSize);

    if (!master_reset_cluster() ||
        !prepare_chaincheck_input(token, g_transfer_hidden_bf16)) {
      return false;
    }
    const uint32_t chained_input =
        payload_digest(g_transfer_hidden_bf16, kHiddenSize);
    ClusterPacket& request = *g_spi_request;
    memset(&request, 0, sizeof(request));
    request.magic = kClusterMagic;
    request.sequence = ++g_spi_sequence;
    request.token = token;
    request.position = 0;
    request.payload_words = kHiddenSize;
    request.target_stage = 1;
    request.source_stage = 0;
    request.kind = kClusterPipelineLayers;
    request.mode = kClusterFast;
    request.stream_id = 0;
    request.reserved[0] = stop;
    memcpy(request.payload, g_transfer_hidden_bf16,
           kHiddenSize * sizeof(uint16_t));
    cluster_packet_seal(request);
    memset(g_spi_reply, 0, sizeof(*g_spi_reply));
    if (!master_ring_transfer(&request, g_spi_reply) ||
        !cluster_packet_valid(*g_spi_reply) ||
        g_spi_reply->sequence != request.sequence ||
        g_spi_reply->kind != kClusterPipelineLayers ||
        g_spi_reply->source_stage != stop ||
        g_spi_reply->payload_words != kHiddenSize) {
      ++g_spi_errors;
      return false;
    }
    const uint32_t chained = payload_digest(g_spi_reply->payload, kHiddenSize);
    const bool equal = targeted == chained;
    all_equal = all_equal && equal;
    Serial.printf("CHAINCHECK stage=%u input_target=%08x input_chain=%08x "
                  "targeted=%08x chained=%08x equal=%u\n",
                  stop, targeted_input, chained_input, targeted, chained,
                  equal ? 1 : 0);

    if (stop == 1) {
      if (!master_reset_cluster() ||
          !prepare_chaincheck_input(token, g_transfer_hidden_bf16)) {
        return false;
      }
      memset(&request, 0, sizeof(request));
      request.magic = kClusterMagic;
      request.sequence = ++g_spi_sequence;
      request.token = token;
      request.position = 0;
      request.payload_words = kHiddenSize;
      request.target_stage = 1;
      request.source_stage = 0;
      request.kind = kClusterPipelineLayers;
      request.mode = kClusterFast;
      request.stream_id = 0;
      memcpy(request.payload, g_transfer_hidden_bf16,
             kHiddenSize * sizeof(uint16_t));
      cluster_packet_seal(request);
      memset(g_spi_reply, 0, sizeof(*g_spi_reply));
      if (!master_ring_transfer(&request, g_spi_reply) ||
          !cluster_packet_valid(*g_spi_reply) ||
          g_spi_reply->sequence != request.sequence ||
          g_spi_reply->kind != kClusterPipelineLayers ||
          g_spi_reply->source_stage != 1 ||
          g_spi_reply->payload_words != kHiddenSize) {
        ++g_spi_errors;
        return false;
      }
      const uint32_t pipeline_targeted =
          payload_digest(g_spi_reply->payload, kHiddenSize);
      Serial.printf("CHAINCHECK_KIND stage=1 run_layers=%08x "
                    "pipeline_targeted=%08x equal=%u\n",
                    targeted, pipeline_targeted,
                    targeted == pipeline_targeted ? 1 : 0);
      all_equal = all_equal && targeted == pipeline_targeted;
    }
  }
  Serial.printf("CHAINCHECK_DONE all_equal=%u\n", all_equal ? 1 : 0);
  return all_equal;
}

bool run_interleave_one_prompt() {
  const ProofPrompt& prompt = kProofPrompts[0];
  const PipelineTrialResult single = run_pipeline_trial(prompt, 1, "single");
  if (!single.ok || !single.all_exact) {
    Serial.println("INTERLEAVE_DONE all_exact=0 phase=single");
    return false;
  }
  const PipelineTrialResult dual = run_pipeline_trial(prompt, 2, "dual");
  const bool exact = dual.ok && dual.all_exact;
  const float speedup = single.aggregate_tps > 0.0f
      ? dual.aggregate_tps / single.aggregate_tps
      : 0.0f;
  Serial.printf("{\"event\":\"interleave_comparison\","
                "\"single_tok_s\":%.6f,\"dual_tok_s\":%.6f,"
                "\"dual_over_single\":%.6f,\"all_exact\":%s}\n",
      single.aggregate_tps, dual.aggregate_tps, speedup,
      exact ? "true" : "false");
  Serial.printf("INTERLEAVE_DONE all_exact=%u\n", exact ? 1 : 0);
  return exact;
}

bool run_interleave_dual_only() {
  const PipelineTrialResult dual =
      run_pipeline_trial(kProofPrompts[0], 2, "dual-chain");
  const bool exact = dual.ok && dual.all_exact;
  Serial.printf("INTERLEAVE2_DONE all_exact=%u\n", exact ? 1 : 0);
  return exact;
}

bool run_distinct_context_five() {
  const PipelineTrialResult five =
      run_pipeline_trial(kProofPrompts[0], kProofPromptCount,
                         "five-context", true);
  const bool exact = five.ok && five.all_exact;
  Serial.printf("CONTEXT5_DONE prompts=%u tokens=%u wall_ms=%.3f "
                "aggregate_tok_s=%.6f all_exact=%u spi_errors=%u\n",
      kProofPromptCount, five.tokens, five.wall_us / 1000.0,
      five.aggregate_tps, exact ? 1 : 0, g_spi_errors);
  return exact;
}

bool run_interleave_five_prompts() {
  uint64_t single_wall_us = 0;
  uint64_t dual_wall_us = 0;
  uint16_t single_tokens = 0;
  uint16_t dual_tokens = 0;
  bool all_exact = true;
  for (uint32_t index = 0; index < kProofPromptCount; ++index) {
    const ProofPrompt& prompt = kProofPrompts[index];
    const PipelineTrialResult single = run_pipeline_trial(prompt, 1, "single");
    if (!single.ok || !single.all_exact) {
      Serial.printf("INTERLEAVE5_DONE all_exact=0 prompt=%s phase=single\n",
                    prompt.id);
      return false;
    }
    const PipelineTrialResult dual = run_pipeline_trial(prompt, 2, "dual");
    const bool exact = dual.ok && dual.all_exact;
    const float speedup = single.aggregate_tps > 0.0f
        ? dual.aggregate_tps / single.aggregate_tps
        : 0.0f;
    Serial.printf("{\"event\":\"interleave_prompt_comparison\","
                  "\"prompt\":\"%s\",\"single_tok_s\":%.6f,"
                  "\"dual_tok_s\":%.6f,\"dual_over_single\":%.6f,"
                  "\"all_exact\":%s}\n",
        prompt.id, single.aggregate_tps, dual.aggregate_tps, speedup,
        exact ? "true" : "false");
    if (!exact) {
      Serial.printf("INTERLEAVE5_DONE all_exact=0 prompt=%s phase=dual\n",
                    prompt.id);
      return false;
    }
    single_wall_us += single.wall_us;
    dual_wall_us += dual.wall_us;
    single_tokens += single.tokens;
    dual_tokens += dual.tokens;
    all_exact = all_exact && exact;
  }
  const float single_tps = single_wall_us
      ? static_cast<float>(single_tokens) * 1000000.0f /
          static_cast<float>(single_wall_us)
      : 0.0f;
  const float dual_tps = dual_wall_us
      ? static_cast<float>(dual_tokens) * 1000000.0f /
          static_cast<float>(dual_wall_us)
      : 0.0f;
  const float speedup = single_tps > 0.0f ? dual_tps / single_tps : 0.0f;
  Serial.printf("{\"event\":\"interleave_five_summary\","
                "\"prompts\":%u,\"single_tokens\":%u,\"dual_tokens\":%u,"
                "\"single_wall_ms\":%.3f,\"dual_wall_ms\":%.3f,"
                "\"single_tok_s\":%.6f,\"dual_tok_s\":%.6f,"
                "\"dual_over_single\":%.6f,\"all_exact\":%s}\n",
      kProofPromptCount, single_tokens, dual_tokens,
      single_wall_us / 1000.0, dual_wall_us / 1000.0,
      single_tps, dual_tps, speedup, all_exact ? "true" : "false");
  Serial.printf("INTERLEAVE5_DONE all_exact=%u\n", all_exact ? 1 : 0);
  return all_exact;
}

bool start_cluster_bus() {
  if (g_bus_started) return true;
  g_spi_request = static_cast<ClusterPacket*>(heap_caps_aligned_alloc(
      4, sizeof(ClusterPacket), MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL));
  g_spi_reply = static_cast<ClusterPacket*>(heap_caps_aligned_alloc(
      4, sizeof(ClusterPacket), MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL));
  if (g_stage->stage == 0) {
    g_command_response = static_cast<ClusterPacket*>(heap_caps_aligned_alloc(
        4, sizeof(ClusterPacket), MALLOC_CAP_INTERNAL));
  }
  if (!g_spi_request || !g_spi_reply ||
      (g_stage->stage == 0 && !g_command_response)) return false;
  if (!init_ring_links()) return false;
  if (g_stage->stage == 0) {
    g_pipeline_receive_permits =
        xQueueCreate(kPipelineStreams + 1, sizeof(uint8_t));
    g_pipeline_return_queue =
        xQueueCreate(kPipelineStreams + 1, sizeof(ClusterPacket));
    if (!g_pipeline_receive_permits || !g_pipeline_return_queue ||
        xTaskCreatePinnedToCore(pipeline_receiver_service, "pq-spi-return",
            8192, nullptr, 3, &g_pipeline_receiver_task, 0) != pdPASS) {
      return false;
    }
  } else {
    if (!g_transport_relay) {
      g_logits_hidden_bf16 = static_cast<uint16_t*>(heap_caps_aligned_alloc(
          4, kHiddenSize * sizeof(uint16_t), MALLOC_CAP_INTERNAL));
      g_logits_done = xSemaphoreCreateBinary();
      if (!g_logits_hidden_bf16 || !g_logits_done ||
          xTaskCreatePinnedToCore(logits_service, "pq-logits", 8192, nullptr,
              2, &g_logits_task, 1) != pdPASS) {
        return false;
      }
    }
    if (xTaskCreatePinnedToCore(worker_service, "pq-spi-worker", 8192, nullptr,
            3, &g_worker_task, 0) != pdPASS) {
      return false;
    }
  }
  g_bus_started = true;
  return true;
}

bool read_exact(uint8_t* destination, size_t bytes, uint32_t timeout_ms) {
  const uint32_t started = millis();
  size_t received = 0;
  while (received < bytes && millis() - started < timeout_ms) {
    const int available = Serial.available();
    if (available > 0) {
      received += Serial.readBytes(destination + received,
          min(static_cast<size_t>(available), bytes - received));
    } else {
      delay(1);
    }
  }
  return received == bytes;
}

void print_info() {
  const uint32_t layer_last = g_stage->layer_count
      ? g_stage->layer_first + g_stage->layer_count - 1u
      : 0u;
  Serial.printf("INFO stage=%u layers=%u-%u vocab=%u+%u psram_free=%u model=%u "
                "ready=%u bus=%u ring_state=%u ring_rx=%u ring_tx=%u ring_seq=%u "
                "in_ready=%d out_ready=%d out_sclk=%d spi_errors=%u "
                "ring_error=%d reset_reason=%d\n",
      g_stage->stage, g_stage->layer_first, layer_last, g_stage->vocab_first,
      g_stage->vocab_count, ESP.getFreePsram(), g_model_partition ? g_model_partition->size : 0,
      g_ready ? 1 : 0, g_bus_started ? 1 : 0, g_ring_state,
      g_ring_rx_count, g_ring_tx_count, g_ring_last_sequence,
      gpio_get_level(static_cast<gpio_num_t>(kInReady)),
      gpio_get_level(static_cast<gpio_num_t>(kOutReady)), outgoing_sclk(), g_spi_errors,
      static_cast<int>(g_ring_last_error),
      static_cast<int>(esp_reset_reason()));
}

void handle_command(String command) {
  command.trim();
  if (command == "INFO") {
    print_info();
    return;
  }
  if (command == "RESET") {
    reset_local_cache();
    Serial.println("OK RESET");
    return;
  }
  if (command == "STARTBUS") {
    if (!g_ready) {
      Serial.println("ERR STARTBUS_NOT_LOADED");
      return;
    }
    Serial.println(start_cluster_bus() ? "OK STARTBUS" : "ERR STARTBUS");
    return;
  }
  if (command == "STARTLINK") {
    Serial.println(start_cluster_bus() ? "OK STARTLINK" : "ERR STARTLINK");
    return;
  }
  if (command == "LINKTEST") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR LINKTEST_NOT_MASTER");
      return;
    }
    g_spi_errors = 0;
    g_ring_receive_timeout_ms = 30000;
    const bool ok = master_reset_cluster();
    g_ring_receive_timeout_ms = 600000;
    Serial.printf("LINKTEST pass=%u sequence=%u spi_errors=%u out_ready=%d\n",
        ok ? 1 : 0, g_spi_sequence, g_spi_errors,
        gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
    return;
  }
  if (command == "BENCH FAST" || command == "BENCH REGULAR") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR BENCH_NOT_MASTER");
      return;
    }
    run_proof_suite(command.endsWith("FAST") ? kClusterFast : kClusterRegular);
    return;
  }
  if (command == "BENCH ONE FAST" || command == "BENCH ONE REGULAR") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR BENCH_NOT_MASTER");
      return;
    }
    const ClusterMode mode = command.endsWith("FAST") ? kClusterFast : kClusterRegular;
    const bool exact = run_proof_prompt(kProofPrompts[0], mode);
    Serial.printf("BENCH_ONE_DONE mode=%s prompt=p01 all_exact=%u\n",
        mode == kClusterFast ? "fast" : "regular", exact ? 1 : 0);
    return;
  }
  if (command == "SELECTTEST") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR SELECTTEST_NOT_MASTER");
      return;
    }
    g_spi_errors = 0;
    const bool reset_ok = master_reset_cluster();
    uint16_t selected = UINT16_MAX;
    uint16_t* hidden = g_transfer_hidden_bf16;
    const bool embedding_ok = reset_ok &&
        local_embedding(kProofPrompts[0].input_ids[0], hidden);
    const uint64_t started = esp_timer_get_time();
    const bool select_ok = embedding_ok &&
        master_select_token(hidden, kClusterFast, selected);
    Serial.printf("SELECTTEST pass=%u reset=%u embedding=%u token=%u "
                  "elapsed_ms=%.3f spi_errors=%u ring_error=%d ready=%d\n",
        select_ok ? 1 : 0, reset_ok ? 1 : 0, embedding_ok ? 1 : 0,
        selected, (esp_timer_get_time() - started) / 1000.0, g_spi_errors,
        static_cast<int>(g_ring_last_error),
        gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
    return;
  }
  if (command == "BENCH INTERLEAVE1") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR BENCH_NOT_MASTER");
      return;
    }
    run_interleave_one_prompt();
    return;
  }
  if (command == "BENCH INTERLEAVE2") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR BENCH_NOT_MASTER");
      return;
    }
    run_interleave_dual_only();
    return;
  }
  if (command == "BENCH CONTEXT5") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR BENCH_NOT_MASTER");
      return;
    }
    run_distinct_context_five();
    return;
  }
  if (command == "CHAINCHECK") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR BENCH_NOT_MASTER");
      return;
    }
    run_chain_prefix_check();
    return;
  }
  if (command == "CHAINCHECK1") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR BENCH_NOT_MASTER");
      return;
    }
    run_chain_prefix_check(1);
    return;
  }
  if (command == "BUSTEST") {
    if (g_stage->stage != 0 || !g_bus_started) {
      Serial.println("ERR BUSTEST_NOT_MASTER");
      return;
    }
    Serial.printf("BUSTEST begin ready=%d\n",
        gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
    const bool reset_ok = master_reset_cluster();
    Serial.printf("BUSTEST reset=%u spi_errors=%u ready=%d\n", reset_ok ? 1 : 0,
        g_spi_errors, gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
    if (!reset_ok) return;
    uint16_t zero_hidden[kHiddenSize]{};
    const bool logits_started = master_begin_logits(zero_hidden, kClusterFast);
    Serial.printf("BUSTEST logits_start=%u spi_errors=%u ready=%d\n",
        logits_started ? 1 : 0, g_spi_errors,
        gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
    if (!logits_started) return;
    for (uint8_t stage = 1; stage < 5; ++stage) {
      ClusterPacket& response = *g_command_response;
      memset(&response, 0, sizeof(response));
      bool ok = master_send(stage, kClusterCollectLogits, kClusterFast, 0, 0,
          nullptr, 0, true, &response);
      Serial.printf("BUSTEST stage=%u collect=%u spi_errors=%u ready=%d\n", stage,
          ok ? 1 : 0, g_spi_errors,
          gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
      if (!ok) break;
      const StageLocation* location = stage_by_index(stage);
      ok = master_send(stage, kClusterFetchEmbedding, kClusterFast, 0,
          static_cast<uint16_t>(location->vocab_first), nullptr, 0, true, &response) &&
          response.payload_words == kHiddenSize;
      Serial.printf("BUSTEST stage=%u embedding=%u spi_errors=%u ready=%d\n", stage,
          ok ? 1 : 0, g_spi_errors,
          gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
      if (!ok) break;
      ok = master_send(stage, kClusterRunLayers, kClusterFast, 0, 0,
          zero_hidden, kHiddenSize, true, &response) &&
          response.payload_words == kHiddenSize;
      Serial.printf("BUSTEST stage=%u layers=%u compute_us=%u spi_errors=%u ready=%d\n",
          stage, ok ? 1 : 0, response.compute_us, g_spi_errors,
          gpio_get_level(static_cast<gpio_num_t>(kOutReady)));
      if (!ok) break;
    }
    Serial.println("BUSTEST done");
    return;
  }
  if (command.startsWith("LOADBEGIN ")) {
    const uint32_t bytes = static_cast<uint32_t>(command.substring(10).toInt());
    const uint32_t expected = g_stage->vocab_psram_rows * kHiddenSize * sizeof(uint16_t);
    if (bytes != expected) {
      Serial.println("ERR LOADBEGIN_SIZE");
      return;
    }
    g_ready = false;
    g_load_expected = bytes;
    g_load_received = 0;
    g_load_active = true;
    Serial.printf("OK LOADBEGIN bytes=%u\n", bytes);
    return;
  }
  if (command.startsWith("LOADCHUNK ")) {
    const int separator = command.indexOf(' ', 10);
    if (separator < 0) {
      Serial.println("ERR LOADCHUNK_ARGS");
      return;
    }
    const uint32_t offset = static_cast<uint32_t>(command.substring(10, separator).toInt());
    const uint32_t bytes = static_cast<uint32_t>(command.substring(separator + 1).toInt());
    if (g_load_expected == 0 || offset != g_load_received || bytes == 0 ||
        bytes > 32768 || offset + bytes > g_load_expected) {
      Serial.println("ERR LOADCHUNK_RANGE");
      return;
    }
    Serial.printf("OK LOADCHUNK_READY offset=%u bytes=%u\n", offset, bytes);
    Serial.flush();
    if (!read_exact(reinterpret_cast<uint8_t*>(g_vocab_psram) + offset, bytes, 15000)) {
      g_load_expected = 0;
      g_load_received = 0;
      Serial.println("ERR LOADCHUNK_DATA");
      return;
    }
    g_load_received += bytes;
    Serial.printf("OK LOADCHUNK offset=%u received=%u\n", offset, g_load_received);
    return;
  }
  if (command.startsWith("LOADB64 ")) {
    const int separator = command.indexOf(' ', 8);
    if (separator < 0) {
      Serial.println("ERR LOADB64_ARGS");
      return;
    }
    const uint32_t offset = static_cast<uint32_t>(command.substring(8, separator).toInt());
    const String encoded = command.substring(separator + 1);
    size_t decoded = 0;
    if (g_load_expected == 0 || offset != g_load_received || encoded.length() == 0 ||
        offset >= g_load_expected ||
        mbedtls_base64_decode(reinterpret_cast<uint8_t*>(g_vocab_psram) + offset,
            g_load_expected - offset, &decoded,
            reinterpret_cast<const uint8_t*>(encoded.c_str()), encoded.length()) != 0 ||
        decoded == 0 || decoded > 3072) {
      Serial.println("ERR LOADB64_DATA");
      return;
    }
    g_load_received += static_cast<uint32_t>(decoded);
    Serial.printf("OK LOADB64 offset=%u received=%u\n", offset, g_load_received);
    return;
  }
  if (command == "LOADEND") {
    if (!g_load_active || g_load_received != g_load_expected) {
      Serial.println("ERR LOADEND_COUNT");
      return;
    }
    g_ready = true;
    Serial.printf("OK LOAD bytes=%u\n", g_load_received);
    g_load_expected = 0;
    g_load_received = 0;
    g_load_active = false;
    return;
  }
  if (command.startsWith("RUN ")) {
    const int first_space = command.indexOf(' ', 4);
    if (first_space < 0) {
      Serial.println("ERR RUN_ARGS");
      return;
    }
    const String mode = command.substring(4, first_space);
    const uint32_t position = static_cast<uint32_t>(command.substring(first_space + 1).toInt());
    uint16_t hidden_bf16[kHiddenSize];
    if (!read_exact(reinterpret_cast<uint8_t*>(hidden_bf16), sizeof(hidden_bf16), 10000)) {
      Serial.println("ERR RUN_PAYLOAD");
      return;
    }
    bf16_to_float_vector(hidden_bf16, g_hidden, kHiddenSize);
    uint64_t compute_us = 0;
    const bool ok = run_local_layers(mode == "fast", 0, position, g_hidden, compute_us);
    if (!ok) {
      Serial.println("ERR RUN_COMPUTE");
      return;
    }
    float_to_bf16_vector(g_hidden, hidden_bf16, kHiddenSize);
    Serial.printf("RESULT bytes=%u compute_us=%llu\n", sizeof(hidden_bf16), compute_us);
    Serial.write(reinterpret_cast<const uint8_t*>(hidden_bf16), sizeof(hidden_bf16));
    Serial.flush();
    return;
  }
  Serial.println("ERR COMMAND");
}

}  // namespace

void setup() {
  Serial.setRxBufferSize(8192);
  Serial.begin(kSerialBaud);
  Serial.setTimeout(1000);
  delay(300);
  const int stage = stage_from_mac();
  if (stage < 0) {
    Serial.println("FATAL UNKNOWN_MAC");
    return;
  }
  g_transport_relay = stage == 5;
  g_stage = stage_by_index(static_cast<uint32_t>(stage));
  set_stage_color(g_stage->stage);
  g_model_partition = esp_partition_find_first(
      ESP_PARTITION_TYPE_DATA, static_cast<esp_partition_subtype_t>(0x40), "model");
  if (!g_model_partition || !psramFound() || !allocate_runtime() ||
      !start_fast_matvec_executor()) {
    Serial.println("FATAL INIT");
    return;
  }
  init_weight_lut(g_weight_lut);
  print_info();
}

void loop() {
  if (!g_stage || !g_model_partition) {
    delay(1000);
    return;
  }
  if (Serial.available()) {
    handle_command(Serial.readStringUntil('\n'));
  } else {
    delay(1);
  }
}
