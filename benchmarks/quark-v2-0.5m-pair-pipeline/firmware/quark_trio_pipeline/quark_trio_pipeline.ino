#include <Arduino.h>
#include <driver/gpio.h>
#include <driver/spi_master.h>
#include <driver/spi_slave.h>
#include <esp_heap_caps.h>
#include <hal/gpio_ll.h>
#include <soc/gpio_struct.h>

#include "../quark_esp32/quark_model_data.h"
#include "../quark_esp32/quark_runtime.h"

#if defined(QUARK_ROLE_TRIO_PIPE_MASTER)
struct StreamState;
struct Lane;
#endif

#if !defined(QUARK_ROLE_TRIO_PIPE_MASTER) && !defined(QUARK_ROLE_TRIO_PIPE_WORKER1) && !defined(QUARK_ROLE_TRIO_PIPE_WORKER2)
#error "Define one QUARK_ROLE_TRIO_PIPE_MASTER, QUARK_ROLE_TRIO_PIPE_WORKER1, or QUARK_ROLE_TRIO_PIPE_WORKER2"
#endif

static constexpr uint32_t FRAME_MAGIC = 0x34544B51;  // QKT4
static constexpr size_t FRAME_BYTES = 512;
static constexpr size_t REPLY_BYTES = 24;
static constexpr int MODEL_DIM = 96;
static constexpr int STREAMS = 2;
static constexpr int LANES = 2;
static constexpr int LED_PIN = 48;
static constexpr int SCK_PIN = 12;
static constexpr int MOSI_PIN = 11;
static constexpr int MISO_PIN = 13;
static constexpr int CS_PIN = 10;
static constexpr int READY_PIN = 9;
static constexpr int SCK2_PIN = 6;
static constexpr int MOSI2_PIN = 7;
static constexpr int MISO2_PIN = 15;
static constexpr int CS2_PIN = 14;
static constexpr int READY2_PIN = 8;
static constexpr int SPI_CLOCK_HZ = 40000000;

struct __attribute__((packed)) WireFrame {
  uint32_t magic;
  uint32_t sequence;
  uint16_t token;
  uint16_t position;
  uint16_t result_token;
  uint16_t stream;
  uint32_t compute_us;
  uint32_t checksum;
  float activation[MODEL_DIM];
  uint8_t reserved[FRAME_BYTES - 24 - MODEL_DIM * sizeof(float)];
};
static_assert(sizeof(WireFrame) == FRAME_BYTES, "DMA frame must be 512 bytes");
static constexpr size_t REQUEST_BYTES = 24 + MODEL_DIM * sizeof(float);

static uint32_t fnv1a_update(uint32_t hash, const void *data, size_t bytes) {
  const uint8_t *p = static_cast<const uint8_t *>(data);
  for (size_t i = 0; i < bytes; ++i) hash = (hash ^ p[i]) * 16777619u;
  return hash;
}

static uint32_t request_checksum(const WireFrame *frame) {
  uint32_t hash = fnv1a_update(2166136261u, frame, 20);
  return fnv1a_update(hash, frame->activation, MODEL_DIM * sizeof(float));
}

static uint32_t response_checksum(const WireFrame *frame) {
  return fnv1a_update(2166136261u, frame, 20);
}

static const uint16_t PROMPT_A[] = {37, 86, 88, 358, 294, 431, 484,
                                    479, 333, 272, 326, 315, 225};
static const uint16_t EXPECTED_A[] = {339, 93, 469, 84, 427, 407, 293, 314,
                                      71, 465, 262, 280, 437, 294, 344, 289,
                                      271, 93, 310, 406, 18, 203, 461, 265};
static const uint16_t PROMPT_B[] = {461, 271, 71, 77, 302, 358, 294,
                                    291, 323, 76, 364, 315, 225};
static const uint16_t EXPECTED_B[] = {339, 93, 469, 84, 427, 407, 293, 314,
                                      71, 465, 262, 280, 437, 294, 344, 289,
                                      271, 93, 310, 406, 18, 203, 461, 265};
static constexpr int GENERATED = 24;

#if defined(QUARK_ROLE_TRIO_PIPE_MASTER)
static Transformer models[STREAMS * LANES];
#else
static Transformer models[STREAMS];
#endif
static bool model_ready = false;

static int argmax(const float *values, int count) {
  int best = 0;
  for (int i = 1; i < count; ++i) {
    if (values[i] > values[best]) best = i;
  }
  return best;
}

static void idle_color() {
#if defined(QUARK_ROLE_TRIO_PIPE_MASTER)
  rgbLedWrite(LED_PIN, 80, 0, 100);  // violet master
#elif defined(QUARK_ROLE_TRIO_PIPE_WORKER2)
  rgbLedWrite(LED_PIN, 100, 35, 0);  // orange worker 2
#else
  rgbLedWrite(LED_PIN, 0, 100, 0);   // green worker
#endif
}

#if defined(QUARK_ROLE_TRIO_PIPE_MASTER)

struct StreamState {
  Transformer *model;
  const uint16_t *prompt;
  int prompt_count;
  const uint16_t *expected;
  int expected_count;
  int token;
  int pos;
  int out_count;
  uint16_t generated[GENERATED];
  uint64_t master_us;
  uint64_t worker_us;
  uint64_t transport_us;
  bool prepared;
};

struct Lane {
  int id;
  spi_host_device_t host;
  int sck;
  int mosi;
  int miso;
  int cs;
  int ready;
  spi_device_handle_t device;
  WireFrame *tx_frame;
  WireFrame *retry_frame;
  WireFrame *rx_frame;
  uint32_t retries;
};

static Lane lanes[LANES] = {
    {0, SPI2_HOST, SCK_PIN, MOSI_PIN, MISO_PIN, CS_PIN, READY_PIN,
     nullptr, nullptr, nullptr, nullptr, 0},
    {1, SPI3_HOST, SCK2_PIN, MOSI2_PIN, MISO2_PIN, CS2_PIN, READY2_PIN,
     nullptr, nullptr, nullptr, nullptr, 0}};

static bool wait_ready(Lane &lane, int level, uint32_t timeout_us) {
  uint64_t start = esp_timer_get_time();
  while (gpio_get_level((gpio_num_t)lane.ready) != level) {
    if (esp_timer_get_time() - start > timeout_us) return false;
    delayMicroseconds(2);
  }
  return true;
}

static bool transfer(Lane &lane, size_t bytes, const void *tx, void *rx) {
  spi_transaction_t transaction = {};
  transaction.length = bytes * 8;
  transaction.tx_buffer = tx;
  transaction.rx_buffer = rx;
  return spi_device_transmit(lane.device, &transaction) == ESP_OK;
}

static int total_steps(const StreamState &stream) {
  return stream.prompt_count + stream.expected_count - 1;
}

static bool active(const StreamState &stream) {
  return stream.pos < total_steps(stream);
}

static void prepare(Lane &lane, StreamState &stream, int stream_id) {
  uint64_t begin = esp_timer_get_time();
  float *activation = forward_partial(stream.model, stream.token, stream.pos,
                                      0, 2, nullptr, false);
  stream.master_us += esp_timer_get_time() - begin;
  memset(lane.tx_frame, 0, FRAME_BYTES);
  lane.tx_frame->magic = FRAME_MAGIC;
  lane.tx_frame->sequence = (uint32_t)stream.pos + 1;
  lane.tx_frame->token = (uint16_t)stream.token;
  lane.tx_frame->position = (uint16_t)stream.pos;
  lane.tx_frame->stream = (uint16_t)stream_id;
  memcpy(lane.tx_frame->activation, activation, MODEL_DIM * sizeof(float));
  lane.tx_frame->checksum = request_checksum(lane.tx_frame);
  stream.prepared = true;
}

static bool dispatch(Lane &lane, StreamState &stream) {
  uint64_t begin = esp_timer_get_time();
  memcpy(lane.retry_frame, lane.tx_frame, REQUEST_BYTES);
  if (!wait_ready(lane, 1, 2000000) ||
      !transfer(lane, REQUEST_BYTES, lane.tx_frame, nullptr) ||
      !wait_ready(lane, 0, 2000000)) {
    return false;
  }
  stream.transport_us += esp_timer_get_time() - begin;
  stream.prepared = false;
  return true;
}

static bool redispatch(Lane &lane, StreamState &stream) {
  uint64_t begin = esp_timer_get_time();
  bool ok = wait_ready(lane, 1, 2000000) &&
            transfer(lane, REQUEST_BYTES, lane.retry_frame, nullptr) &&
            wait_ready(lane, 0, 2000000);
  stream.transport_us += esp_timer_get_time() - begin;
  return ok;
}

static bool collect(Lane &lane, StreamState &stream, int stream_id) {
  for (int attempt = 0; attempt < 3; ++attempt) {
    uint64_t begin = esp_timer_get_time();
    memset(lane.rx_frame, 0, FRAME_BYTES);
    bool ready_high = wait_ready(lane, 1, 5000000);
    bool transferred = ready_high &&
                       transfer(lane, REPLY_BYTES, nullptr, lane.rx_frame);
    bool ready_low = transferred && wait_ready(lane, 0, 2000000);
    bool received = ready_high && transferred && ready_low;
    stream.transport_us += esp_timer_get_time() - begin;
    bool valid = received && lane.rx_frame->magic == FRAME_MAGIC &&
                 lane.rx_frame->stream == stream_id &&
                 lane.rx_frame->sequence == (uint32_t)stream.pos + 1 &&
                 lane.rx_frame->checksum == response_checksum(lane.rx_frame) &&
                 lane.rx_frame->result_token != UINT16_MAX;
    if (valid) break;
    ++lane.retries;
    if (attempt == 2) {
      Serial.printf("{\"event\":\"packet_retry_failure\",\"lane\":%d,"
                    "\"stream\":%d,\"pos\":%d,\"ready_high\":%s,"
                    "\"transferred\":%s,\"ready_low\":%s,"
                    "\"magic\":\"0x%08x\",\"sequence\":%u,"
                    "\"reply_stream\":%u,\"result_token\":%u,"
                    "\"checksum\":\"0x%08x\",\"computed\":\"0x%08x\"}\n",
                    lane.id + 1, stream_id, stream.pos,
                    ready_high ? "true" : "false",
                    transferred ? "true" : "false",
                    ready_low ? "true" : "false",
                    lane.rx_frame->magic, lane.rx_frame->sequence,
                    lane.rx_frame->stream, lane.rx_frame->result_token,
                    lane.rx_frame->checksum, response_checksum(lane.rx_frame));
      return false;
    }
    if (!redispatch(lane, stream)) return false;
  }
  stream.worker_us += lane.rx_frame->compute_us;
  int next;
  if (stream.pos < stream.prompt_count - 1) {
    next = stream.prompt[stream.pos + 1];
  } else {
    next = lane.rx_frame->result_token;
    stream.generated[stream.out_count++] = (uint16_t)next;
  }
  stream.token = next;
  ++stream.pos;
  return true;
}

static void print_stream(const StreamState &stream, int stream_id) {
  int matches = 0;
  for (int i = 0; i < stream.expected_count; ++i) {
    if (stream.generated[i] == stream.expected[i]) ++matches;
  }
  Serial.printf("{\"event\":\"quark_pipeline_stream\",\"stream\":%d,", stream_id);
  Serial.printf("\"oracle_match\":\"%d/%d\",\"master_us\":%llu,", matches,
                stream.expected_count, stream.master_us);
  Serial.printf("\"worker_us\":%llu,\"transport_us\":%llu,\"tokens\":[",
                stream.worker_us, stream.transport_us);
  for (int i = 0; i < stream.expected_count; ++i) {
    Serial.printf("%s%u", i ? "," : "", stream.generated[i]);
  }
  Serial.println("]}");
}

struct LaneRun {
  Lane *lane;
  StreamState streams[STREAMS];
  TaskHandle_t controller;
  volatile bool *start;
  bool ok;
  const char *phase;
  int failed_stream;
  uint64_t decode_begin;
  uint64_t wall_end;
};

static void run_lane_pipeline(void *arg) {
  LaneRun *run = static_cast<LaneRun *>(arg);
  if (!run->lane->device && !init_lane_spi(*run->lane)) {
    run->ok = false;
    run->phase = "spi_init";
    run->failed_stream = -1;
    run->wall_end = esp_timer_get_time();
    xTaskNotifyGive(run->controller);
    vTaskDelete(nullptr);
    return;
  }
  while (!*run->start) vTaskDelay(1);
  run->ok = true;
  int inflight = 0;
  prepare(*run->lane, run->streams[0], 0);
  if (!dispatch(*run->lane, run->streams[0])) {
    run->ok = false;
    run->phase = "initial_dispatch";
    run->failed_stream = 0;
  }

  while (run->ok && inflight >= 0) {
    int other = 1 - inflight;
    if (active(run->streams[other]) && !run->streams[other].prepared) {
      if (!run->decode_begin &&
          run->streams[other].pos >= run->streams[other].prompt_count - 1) {
        run->decode_begin = esp_timer_get_time();
      }
      prepare(*run->lane, run->streams[other], other);
    }

    if (!collect(*run->lane, run->streams[inflight], inflight)) {
      run->ok = false;
      run->phase = "collect";
      run->failed_stream = inflight;
      break;
    }

    int next = -1;
    if (run->streams[other].prepared) {
      next = other;
    } else if (active(run->streams[inflight])) {
      if (!run->decode_begin &&
          run->streams[inflight].pos >= run->streams[inflight].prompt_count - 1) {
        run->decode_begin = esp_timer_get_time();
      }
      prepare(*run->lane, run->streams[inflight], inflight);
      next = inflight;
    } else if (active(run->streams[other])) {
      if (!run->decode_begin &&
          run->streams[other].pos >= run->streams[other].prompt_count - 1) {
        run->decode_begin = esp_timer_get_time();
      }
      prepare(*run->lane, run->streams[other], other);
      next = other;
    }

    if (next < 0) break;
    if (!dispatch(*run->lane, run->streams[next])) {
      run->ok = false;
      run->phase = "dispatch";
      run->failed_stream = next;
      break;
    }
    inflight = next;
  }
  run->wall_end = esp_timer_get_time();
  xTaskNotifyGive(run->controller);
  vTaskDelete(nullptr);
}

static void run_trio_pipeline() {
  volatile bool start = false;
  TaskHandle_t controller = xTaskGetCurrentTaskHandle();
  for (int lane = 0; lane < LANES; ++lane) lanes[lane].retries = 0;
  LaneRun runs[LANES] = {
      {&lanes[0], {{&models[0], PROMPT_A, (int)(sizeof(PROMPT_A) / sizeof(PROMPT_A[0])), EXPECTED_A, GENERATED, PROMPT_A[0], 0, 0, {}, 0, 0, 0, false},
                   {&models[1], PROMPT_B, (int)(sizeof(PROMPT_B) / sizeof(PROMPT_B[0])), EXPECTED_B, GENERATED, PROMPT_B[0], 0, 0, {}, 0, 0, 0, false}},
       controller, &start, false, nullptr, -1, 0, 0},
      {&lanes[1], {{&models[2], PROMPT_A, (int)(sizeof(PROMPT_A) / sizeof(PROMPT_A[0])), EXPECTED_A, GENERATED, PROMPT_A[0], 0, 0, {}, 0, 0, 0, false},
                   {&models[3], PROMPT_B, (int)(sizeof(PROMPT_B) / sizeof(PROMPT_B[0])), EXPECTED_B, GENERATED, PROMPT_B[0], 0, 0, {}, 0, 0, 0, false}},
       controller, &start, false, nullptr, -1, 0, 0}};

  const uint64_t wall_begin = esp_timer_get_time();
  int created = 0;
  for (int lane = 0; lane < LANES; ++lane) {
    TaskHandle_t task = nullptr;
    if (xTaskCreatePinnedToCore(run_lane_pipeline,
                                lane == 0 ? "quark_lane_1" : "quark_lane_2",
                                12288, &runs[lane], 2, &task, lane) == pdPASS) {
      ++created;
    } else {
      runs[lane].phase = "task_create";
    }
  }
  start = true;
  for (int i = 0; i < created; ++i) {
    if (ulTaskNotifyTake(pdFALSE, pdMS_TO_TICKS(30000)) == 0) {
      Serial.println("{\"event\":\"trio_pipeline_error\",\"phase\":\"task_timeout\"}");
      return;
    }
  }
  for (int lane = 0; lane < LANES; ++lane) {
    if (!runs[lane].ok) {
      Serial.printf("{\"event\":\"trio_pipeline_error\",\"lane\":%d,"
                    "\"phase\":\"%s\",\"stream\":%d,\"pos\":%d}\n",
                    lane + 1, runs[lane].phase ? runs[lane].phase : "unknown",
                    runs[lane].failed_stream,
                    runs[lane].failed_stream >= 0
                        ? runs[lane].streams[runs[lane].failed_stream].pos : -1);
      return;
    }
  }

  uint64_t wall_end = max(runs[0].wall_end, runs[1].wall_end);
  uint64_t decode_begin = min(runs[0].decode_begin, runs[1].decode_begin);
  int total_matches = 0;
  for (int lane = 0; lane < LANES; ++lane) {
    for (int stream = 0; stream < STREAMS; ++stream) {
      print_stream(runs[lane].streams[stream], lane * STREAMS + stream);
      for (int i = 0; i < GENERATED; ++i) {
        if (runs[lane].streams[stream].generated[i] ==
            runs[lane].streams[stream].expected[i]) ++total_matches;
      }
    }
  }
  const uint64_t decode_wall_us = wall_end - decode_begin;
  Serial.printf("{\"event\":\"quark_trio_pipeline_result\",\"model_params\":465504,"
                "\"lanes\":2,\"streams\":4,\"oracle_match\":\"%d/96\","
                "\"wall_us\":%llu,\"decode_wall_us\":%llu,"
                "\"aggregate_tok_s\":%.6f,\"retries\":[%u,%u]}\n", total_matches,
                wall_end - wall_begin, decode_wall_us,
                96.0 * 1000000.0 / (double)decode_wall_us,
                lanes[0].retries, lanes[1].retries);
}

static bool init_lane_spi(Lane &lane) {
  gpio_set_direction((gpio_num_t)lane.ready, GPIO_MODE_INPUT);
  spi_bus_config_t bus = {};
  bus.mosi_io_num = lane.mosi;
  bus.miso_io_num = lane.miso;
  bus.sclk_io_num = lane.sck;
  bus.max_transfer_sz = FRAME_BYTES;
  if (spi_bus_initialize(lane.host, &bus, SPI_DMA_CH_AUTO) != ESP_OK) return false;
  spi_device_interface_config_t device = {};
  device.clock_speed_hz = SPI_CLOCK_HZ;
  device.mode = 0;
  device.spics_io_num = lane.cs;
  device.queue_size = 1;
  return spi_bus_add_device(lane.host, &device, &lane.device) == ESP_OK;
}

#else

static WireFrame *worker_rx;
static WireFrame *worker_tx;

static void worker_miso_enabled(bool enabled) {
  // Queueing a slave transaction can return output-enable control to the SPI
  // peripheral. Override only the pad OE: high-Z while receiving, driven only
  // after the response has been queued. This is the proven pair behavior.
  gpio_ll_set_output_enable_ctrl(&GPIO, MISO_PIN, false, false);
  if (enabled) gpio_ll_output_enable(&GPIO, MISO_PIN);
  else gpio_ll_output_disable(&GPIO, MISO_PIN);
}

static void worker_loop(void *) {
  for (;;) {
    memset(worker_rx, 0, FRAME_BYTES);
    spi_slave_transaction_t receive = {};
    receive.length = REQUEST_BYTES * 8;
    receive.rx_buffer = worker_rx;
    if (spi_slave_queue_trans(SPI2_HOST, &receive, portMAX_DELAY) != ESP_OK) continue;
    worker_miso_enabled(false);
    gpio_set_level((gpio_num_t)READY_PIN, 1);
    spi_slave_transaction_t *completed = nullptr;
    if (spi_slave_get_trans_result(SPI2_HOST, &completed, portMAX_DELAY) != ESP_OK) continue;
    gpio_set_level((gpio_num_t)READY_PIN, 0);
    memset(worker_tx, 0, FRAME_BYTES);
    worker_tx->magic = FRAME_MAGIC;
    worker_tx->sequence = worker_rx->sequence;
    worker_tx->stream = worker_rx->stream;
    worker_tx->result_token = UINT16_MAX;
    bool valid_request = worker_rx->magic == FRAME_MAGIC &&
                         worker_rx->stream < STREAMS &&
                         worker_rx->checksum == request_checksum(worker_rx);
    if (valid_request) {
      uint64_t begin = esp_timer_get_time();
      Transformer *model = &models[worker_rx->stream];
      float *logits = forward_partial(model, worker_rx->token, worker_rx->position,
                                      2, 4, worker_rx->activation, true);
      worker_tx->result_token = argmax(logits, model->config.vocab_size);
      worker_tx->compute_us = (uint32_t)(esp_timer_get_time() - begin);
    }
    worker_tx->checksum = response_checksum(worker_tx);

    spi_slave_transaction_t response = {};
    response.length = REPLY_BYTES * 8;
    response.tx_buffer = worker_tx;
    if (spi_slave_queue_trans(SPI2_HOST, &response, portMAX_DELAY) != ESP_OK) continue;
    worker_miso_enabled(true);
    gpio_set_level((gpio_num_t)READY_PIN, 1);
    completed = nullptr;
    spi_slave_get_trans_result(SPI2_HOST, &completed, portMAX_DELAY);
    gpio_set_level((gpio_num_t)READY_PIN, 0);
    worker_miso_enabled(false);
    delayMicroseconds(50);  // Make the response-to-next-request edge observable.
  }
}

static bool init_worker_spi() {
  gpio_set_direction((gpio_num_t)READY_PIN, GPIO_MODE_OUTPUT);
  gpio_set_level((gpio_num_t)READY_PIN, 0);
  spi_bus_config_t bus = {};
  bus.mosi_io_num = MOSI_PIN;
  bus.miso_io_num = MISO_PIN;
  bus.sclk_io_num = SCK_PIN;
  bus.max_transfer_sz = FRAME_BYTES;
  spi_slave_interface_config_t slave = {};
  slave.mode = 0;
  slave.spics_io_num = CS_PIN;
  slave.queue_size = 1;
  if (spi_slave_initialize(SPI2_HOST, &bus, &slave, SPI_DMA_CH_AUTO) != ESP_OK) return false;
  worker_miso_enabled(false);
  return true;
}

#endif

void setup() {
  Serial.begin(115200);
  delay(1500);
  idle_color();
  const int model_contexts =
#if defined(QUARK_ROLE_TRIO_PIPE_MASTER)
      STREAMS * LANES;
#else
      STREAMS;
#endif
  for (int i = 0; i < model_contexts; ++i) {
    build_transformer_from_memory(&models[i], QUARK_MODEL_DATA, QUARK_MODEL_SIZE);
  }

#if defined(QUARK_ROLE_TRIO_PIPE_MASTER)
  for (int lane = 0; lane < LANES; ++lane) {
    lanes[lane].tx_frame = (WireFrame *)heap_caps_aligned_alloc(
        16, FRAME_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    lanes[lane].retry_frame = (WireFrame *)heap_caps_aligned_alloc(
        16, FRAME_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    lanes[lane].rx_frame = (WireFrame *)heap_caps_aligned_alloc(
        16, FRAME_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (!lanes[lane].tx_frame || !lanes[lane].retry_frame ||
        !lanes[lane].rx_frame) abort();
  }
#else
  worker_rx = (WireFrame *)heap_caps_aligned_alloc(
      16, FRAME_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
  worker_tx = (WireFrame *)heap_caps_aligned_alloc(
      16, FRAME_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
  if (!worker_rx || !worker_tx || !init_worker_spi()) abort();
  xTaskCreatePinnedToCore(worker_loop, "quark_pipe_worker", 8192, nullptr, 2, nullptr, 1);
#endif
  model_ready = true;
  Serial.printf("{\"event\":\"trio_pipeline_ready\",\"role\":\"%s\","
                "\"contexts\":%d,\"heap\":%u,\"psram\":%u,\"model_bytes\":%u}\n",
#if defined(QUARK_ROLE_TRIO_PIPE_MASTER)
                "master",
#elif defined(QUARK_ROLE_TRIO_PIPE_WORKER2)
                "worker2",
#else
                "worker1",
#endif
                model_contexts, ESP.getFreeHeap(), ESP.getFreePsram(),
                (unsigned)QUARK_MODEL_SIZE);
}

void loop() {
  if (!model_ready) return;
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
#if defined(QUARK_ROLE_TRIO_PIPE_MASTER)
    if (command == "RUN") run_trio_pipeline();
#else
    if (command == "RUN") Serial.println("{\"event\":\"worker_waiting\"}");
#endif
    idle_color();
  }
  delay(2);
}
