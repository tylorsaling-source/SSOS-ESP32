#include <Arduino.h>
#include <driver/gpio.h>
#include <driver/spi_master.h>
#include <driver/spi_slave.h>
#include <esp_heap_caps.h>

#include "../quark_esp32/quark_model_data.h"
#include "../quark_esp32/quark_runtime.h"

#if defined(QUARK_ROLE_PAIR_PIPE_MASTER)
struct StreamState;
#endif

#if !defined(QUARK_ROLE_PAIR_PIPE_MASTER) && !defined(QUARK_ROLE_PAIR_PIPE_WORKER)
#error "Define exactly one QUARK_ROLE_PAIR_PIPE_MASTER or QUARK_ROLE_PAIR_PIPE_WORKER"
#endif

static constexpr uint32_t FRAME_MAGIC = 0x32504B51;  // QKP2
static constexpr size_t FRAME_BYTES = 512;
static constexpr size_t REPLY_BYTES = 20;
static constexpr int MODEL_DIM = 96;
static constexpr int STREAMS = 2;
static constexpr int LED_PIN = 48;
static constexpr int SCK_PIN = 12;
static constexpr int MOSI_PIN = 11;
static constexpr int MISO_PIN = 13;
static constexpr int CS_PIN = 10;
static constexpr int READY_PIN = 9;
static constexpr int SPI_CLOCK_HZ = 40000000;

struct __attribute__((packed)) WireFrame {
  uint32_t magic;
  uint32_t sequence;
  uint16_t token;
  uint16_t position;
  uint16_t result_token;
  uint16_t stream;
  uint32_t compute_us;
  float activation[MODEL_DIM];
  uint8_t reserved[FRAME_BYTES - 20 - MODEL_DIM * sizeof(float)];
};
static_assert(sizeof(WireFrame) == FRAME_BYTES, "DMA frame must be 512 bytes");

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

static Transformer models[STREAMS];
static bool model_ready = false;

static int argmax(const float *values, int count) {
  int best = 0;
  for (int i = 1; i < count; ++i) {
    if (values[i] > values[best]) best = i;
  }
  return best;
}

static void idle_color() {
#if defined(QUARK_ROLE_PAIR_PIPE_MASTER)
  rgbLedWrite(LED_PIN, 80, 0, 100);  // violet master
#else
  rgbLedWrite(LED_PIN, 0, 100, 0);   // green worker
#endif
}

#if defined(QUARK_ROLE_PAIR_PIPE_MASTER)

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

static spi_device_handle_t spi_device;
static WireFrame *tx_frame;
static WireFrame *rx_frame;

static bool wait_ready(int level, uint32_t timeout_us) {
  uint64_t start = esp_timer_get_time();
  while (gpio_get_level((gpio_num_t)READY_PIN) != level) {
    if (esp_timer_get_time() - start > timeout_us) return false;
    delayMicroseconds(2);
  }
  return true;
}

static bool transfer(size_t bytes, const void *tx, void *rx) {
  spi_transaction_t transaction = {};
  transaction.length = bytes * 8;
  transaction.tx_buffer = tx;
  transaction.rx_buffer = rx;
  return spi_device_transmit(spi_device, &transaction) == ESP_OK;
}

static int total_steps(const StreamState &stream) {
  return stream.prompt_count + stream.expected_count - 1;
}

static bool active(const StreamState &stream) {
  return stream.pos < total_steps(stream);
}

static void prepare(StreamState &stream, int stream_id) {
  uint64_t begin = esp_timer_get_time();
  float *activation = forward_partial(stream.model, stream.token, stream.pos,
                                      0, 2, nullptr, false);
  stream.master_us += esp_timer_get_time() - begin;
  memset(tx_frame, 0, FRAME_BYTES);
  tx_frame->magic = FRAME_MAGIC;
  tx_frame->sequence = (uint32_t)stream.pos + 1;
  tx_frame->token = (uint16_t)stream.token;
  tx_frame->position = (uint16_t)stream.pos;
  tx_frame->stream = (uint16_t)stream_id;
  memcpy(tx_frame->activation, activation, MODEL_DIM * sizeof(float));
  stream.prepared = true;
}

static bool dispatch(StreamState &stream) {
  uint64_t begin = esp_timer_get_time();
  if (!wait_ready(1, 2000000) || !transfer(FRAME_BYTES, tx_frame, nullptr) ||
      !wait_ready(0, 2000000)) {
    return false;
  }
  stream.transport_us += esp_timer_get_time() - begin;
  stream.prepared = false;
  return true;
}

static bool collect(StreamState &stream, int stream_id) {
  uint64_t begin = esp_timer_get_time();
  memset(rx_frame, 0, FRAME_BYTES);
  if (!wait_ready(1, 5000000) || !transfer(REPLY_BYTES, nullptr, rx_frame) ||
      !wait_ready(0, 2000000)) {
    return false;
  }
  stream.transport_us += esp_timer_get_time() - begin;
  if (rx_frame->magic != FRAME_MAGIC || rx_frame->stream != stream_id ||
      rx_frame->sequence != (uint32_t)stream.pos + 1) {
    return false;
  }
  stream.worker_us += rx_frame->compute_us;
  int next;
  if (stream.pos < stream.prompt_count - 1) {
    next = stream.prompt[stream.pos + 1];
  } else {
    next = rx_frame->result_token;
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

static void run_pipeline() {
  StreamState streams[STREAMS] = {
      {&models[0], PROMPT_A, (int)(sizeof(PROMPT_A) / sizeof(PROMPT_A[0])),
       EXPECTED_A, GENERATED, PROMPT_A[0], 0, 0, {}, 0, 0, 0, false},
      {&models[1], PROMPT_B, (int)(sizeof(PROMPT_B) / sizeof(PROMPT_B[0])),
       EXPECTED_B, GENERATED, PROMPT_B[0], 0, 0, {}, 0, 0, 0, false}};

  const uint64_t wall_begin = esp_timer_get_time();
  uint64_t decode_begin = 0;
  int inflight = 0;
  prepare(streams[0], 0);
  if (!dispatch(streams[0])) {
    Serial.println("{\"event\":\"pipeline_error\",\"phase\":\"initial_dispatch\"}");
    return;
  }

  while (inflight >= 0) {
    int other = 1 - inflight;
    if (active(streams[other]) && !streams[other].prepared) {
      if (!decode_begin && streams[other].pos >= streams[other].prompt_count - 1) {
        decode_begin = esp_timer_get_time();
      }
      prepare(streams[other], other);  // overlaps worker's current half
    }

    if (!collect(streams[inflight], inflight)) {
      Serial.printf("{\"event\":\"pipeline_error\",\"phase\":\"collect\","
                    "\"stream\":%d,\"pos\":%d}\n", inflight, streams[inflight].pos);
      return;
    }

    int next = -1;
    if (streams[other].prepared) {
      next = other;
    } else if (active(streams[inflight])) {
      if (!decode_begin && streams[inflight].pos >= streams[inflight].prompt_count - 1) {
        decode_begin = esp_timer_get_time();
      }
      prepare(streams[inflight], inflight);
      next = inflight;
    } else if (active(streams[other])) {
      if (!decode_begin && streams[other].pos >= streams[other].prompt_count - 1) {
        decode_begin = esp_timer_get_time();
      }
      prepare(streams[other], other);
      next = other;
    }

    if (next < 0) {
      inflight = -1;
      break;
    }
    if (!dispatch(streams[next])) {
      Serial.printf("{\"event\":\"pipeline_error\",\"phase\":\"dispatch\","
                    "\"stream\":%d,\"pos\":%d}\n", next, streams[next].pos);
      return;
    }
    inflight = next;
  }

  const uint64_t wall_end = esp_timer_get_time();
  if (!decode_begin) decode_begin = wall_begin;
  print_stream(streams[0], 0);
  print_stream(streams[1], 1);
  int total_matches = 0;
  for (int s = 0; s < STREAMS; ++s) {
    for (int i = 0; i < streams[s].expected_count; ++i) {
      if (streams[s].generated[i] == streams[s].expected[i]) ++total_matches;
    }
  }
  const uint64_t decode_wall_us = wall_end - decode_begin;
  Serial.printf("{\"event\":\"quark_pipeline_result\",\"model_params\":465504,"
                "\"streams\":2,\"oracle_match\":\"%d/48\",\"wall_us\":%llu,"
                "\"decode_wall_us\":%llu,\"aggregate_tok_s\":%.6f}\n",
                total_matches, wall_end - wall_begin, decode_wall_us,
                48.0 * 1000000.0 / (double)decode_wall_us);
}

static bool init_master_spi() {
  gpio_set_direction((gpio_num_t)READY_PIN, GPIO_MODE_INPUT);
  spi_bus_config_t bus = {};
  bus.mosi_io_num = MOSI_PIN;
  bus.miso_io_num = MISO_PIN;
  bus.sclk_io_num = SCK_PIN;
  bus.max_transfer_sz = FRAME_BYTES;
  if (spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO) != ESP_OK) return false;
  spi_device_interface_config_t device = {};
  device.clock_speed_hz = SPI_CLOCK_HZ;
  device.mode = 0;
  device.spics_io_num = CS_PIN;
  device.queue_size = 1;
  return spi_bus_add_device(SPI2_HOST, &device, &spi_device) == ESP_OK;
}

#else

static WireFrame *worker_rx;
static WireFrame *worker_tx;

static void IRAM_ATTR transaction_ready(spi_slave_transaction_t *) {
  gpio_set_level((gpio_num_t)READY_PIN, 1);
}

static void worker_loop(void *) {
  for (;;) {
    memset(worker_rx, 0, FRAME_BYTES);
    spi_slave_transaction_t receive = {};
    receive.length = FRAME_BYTES * 8;
    receive.rx_buffer = worker_rx;
    if (spi_slave_queue_trans(SPI2_HOST, &receive, portMAX_DELAY) != ESP_OK) continue;
    spi_slave_transaction_t *completed = nullptr;
    if (spi_slave_get_trans_result(SPI2_HOST, &completed, portMAX_DELAY) != ESP_OK) continue;
    gpio_set_level((gpio_num_t)READY_PIN, 0);
    if (worker_rx->magic != FRAME_MAGIC || worker_rx->stream >= STREAMS) continue;

    uint64_t begin = esp_timer_get_time();
    Transformer *model = &models[worker_rx->stream];
    float *logits = forward_partial(model, worker_rx->token, worker_rx->position,
                                    2, 4, worker_rx->activation, true);
    memset(worker_tx, 0, FRAME_BYTES);
    worker_tx->magic = FRAME_MAGIC;
    worker_tx->sequence = worker_rx->sequence;
    worker_tx->stream = worker_rx->stream;
    worker_tx->result_token = argmax(logits, model->config.vocab_size);
    worker_tx->compute_us = (uint32_t)(esp_timer_get_time() - begin);

    spi_slave_transaction_t response = {};
    response.length = REPLY_BYTES * 8;
    response.tx_buffer = worker_tx;
    if (spi_slave_queue_trans(SPI2_HOST, &response, portMAX_DELAY) != ESP_OK) continue;
    completed = nullptr;
    spi_slave_get_trans_result(SPI2_HOST, &completed, portMAX_DELAY);
    gpio_set_level((gpio_num_t)READY_PIN, 0);
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
  slave.post_setup_cb = transaction_ready;
  return spi_slave_initialize(SPI2_HOST, &bus, &slave, SPI_DMA_CH_AUTO) == ESP_OK;
}

#endif

void setup() {
  Serial.begin(115200);
  delay(1500);
  idle_color();
  for (int i = 0; i < STREAMS; ++i) {
    build_transformer_from_memory(&models[i], QUARK_MODEL_DATA, QUARK_MODEL_SIZE);
  }

#if defined(QUARK_ROLE_PAIR_PIPE_MASTER)
  tx_frame = (WireFrame *)heap_caps_aligned_alloc(
      16, FRAME_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
  rx_frame = (WireFrame *)heap_caps_aligned_alloc(
      16, FRAME_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
  if (!tx_frame || !rx_frame || !init_master_spi()) abort();
#else
  worker_rx = (WireFrame *)heap_caps_aligned_alloc(
      16, FRAME_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
  worker_tx = (WireFrame *)heap_caps_aligned_alloc(
      16, FRAME_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
  if (!worker_rx || !worker_tx || !init_worker_spi()) abort();
  xTaskCreatePinnedToCore(worker_loop, "quark_pipe_worker", 8192, nullptr, 2, nullptr, 1);
#endif
  model_ready = true;
  Serial.printf("{\"event\":\"pair_pipeline_ready\",\"role\":\"%s\","
                "\"contexts\":2,\"heap\":%u,\"psram\":%u,\"model_bytes\":%u}\n",
#if defined(QUARK_ROLE_PAIR_PIPE_MASTER)
                "master",
#else
                "worker",
#endif
                ESP.getFreeHeap(), ESP.getFreePsram(), (unsigned)QUARK_MODEL_SIZE);
}

void loop() {
  if (!model_ready) return;
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
#if defined(QUARK_ROLE_PAIR_PIPE_MASTER)
    if (command == "RUN") run_pipeline();
#else
    if (command == "RUN") Serial.println("{\"event\":\"worker_waiting\"}");
#endif
    idle_color();
  }
  delay(2);
}
