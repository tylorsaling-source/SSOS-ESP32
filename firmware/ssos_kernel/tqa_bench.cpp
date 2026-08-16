// Equal 9-MAC: custom 9-D vs ESP-NN vs precompiled TFLM 9→1.
// hello_world TFLM is kept and labeled UNEQUAL.
#include <Arduino.h>
#include <math.h>
#include <string.h>
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "model.h"
#include "g_fc9f.h"
#include "g_fc9s8.h"
#include "esp_nn.h"
#include "tqa_runtime.h"

static const float kW9[9] = {
    2.963291013f, 2.926582026f, 2.981645507f, 2.975527342f, 2.928876338f,
    2.933746679f, 1.077591796f, 2.90745369f, 2.919062847f};

static DRAM_ATTR float kW9_ram[9];
static DRAM_ATTR float kX_ram[9];
static DRAM_ATTR int8_t eq_w[9];
static DRAM_ATTR int8_t eq_x[9];
static int32_t eq_bias = 0;
alignas(16) static int8_t nn_out[8];

static const tflite::Model *hw_model = nullptr;
static tflite::MicroInterpreter *hw_interp = nullptr;
static TfLiteTensor *hw_in = nullptr;
static uint8_t hw_arena[4096];
static bool tfl_hw_ok = false;

static const tflite::Model *f9_model = nullptr;
static tflite::MicroInterpreter *f9_interp = nullptr;
static TfLiteTensor *f9_in = nullptr;
static TfLiteTensor *f9_out = nullptr;
static uint8_t f9_arena[4096];
static bool tfl_f9_ok = false;

static const tflite::Model *s9_model = nullptr;
static tflite::MicroInterpreter *s9_interp = nullptr;
static TfLiteTensor *s9_in = nullptr;
static uint8_t s9_arena[4096];
static bool tfl_s9_ok = false;

static inline float IRAM_ATTR tqa_unrolled(const float *x) {
  return kW9_ram[0] * x[0] + kW9_ram[1] * x[1] + kW9_ram[2] * x[2] +
         kW9_ram[3] * x[3] + kW9_ram[4] * x[4] + kW9_ram[5] * x[5] +
         kW9_ram[6] * x[6] + kW9_ram[7] * x[7] + kW9_ram[8] * x[8];
}

static inline int32_t IRAM_ATTR equal_s8_9() {
  int32_t acc = eq_bias;
  acc += (int32_t)eq_w[0] * (int32_t)eq_x[0];
  acc += (int32_t)eq_w[1] * (int32_t)eq_x[1];
  acc += (int32_t)eq_w[2] * (int32_t)eq_x[2];
  acc += (int32_t)eq_w[3] * (int32_t)eq_x[3];
  acc += (int32_t)eq_w[4] * (int32_t)eq_x[4];
  acc += (int32_t)eq_w[5] * (int32_t)eq_x[5];
  acc += (int32_t)eq_w[6] * (int32_t)eq_x[6];
  acc += (int32_t)eq_w[7] * (int32_t)eq_x[7];
  acc += (int32_t)eq_w[8] * (int32_t)eq_x[8];
  return acc;
}

static bool hw_init() {
  hw_model = tflite::GetModel(g_model);
  if (!hw_model || hw_model->version() != TFLITE_SCHEMA_VERSION) return false;
  static tflite::MicroMutableOpResolver<1> rhw;
  if (rhw.AddFullyConnected() != kTfLiteOk) return false;
  static tflite::MicroInterpreter ihw(hw_model, rhw, hw_arena, sizeof(hw_arena));
  hw_interp = &ihw;
  if (hw_interp->AllocateTensors() != kTfLiteOk) return false;
  hw_in = hw_interp->input(0);
  return hw_in != nullptr;
}

static bool hw_one(float x) {
  if (!tfl_hw_ok || !hw_in) return false;
  hw_in->data.int8[0] = (int8_t)(x / hw_in->params.scale + hw_in->params.zero_point);
  return hw_interp->Invoke() == kTfLiteOk;
}

static bool f9_init() {
  f9_model = tflite::GetModel(g_fc9f);
  if (!f9_model || f9_model->version() != TFLITE_SCHEMA_VERSION) return false;
  static tflite::MicroMutableOpResolver<1> rf9;
  if (rf9.AddFullyConnected() != kTfLiteOk) return false;
  static tflite::MicroInterpreter if9(f9_model, rf9, f9_arena, sizeof(f9_arena));
  f9_interp = &if9;
  if (f9_interp->AllocateTensors() != kTfLiteOk) return false;
  f9_in = f9_interp->input(0);
  f9_out = f9_interp->output(0);
  return f9_in && f9_out && f9_in->bytes >= 9 * sizeof(float);
}

static bool f9_one() {
  if (!tfl_f9_ok || !f9_in) return false;
  memcpy(f9_in->data.f, kX_ram, 9 * sizeof(float));
  return f9_interp->Invoke() == kTfLiteOk;
}

static bool s9_init() {
  s9_model = tflite::GetModel(g_fc9s8);
  if (!s9_model || s9_model->version() != TFLITE_SCHEMA_VERSION) return false;
  static tflite::MicroMutableOpResolver<1> rs9;
  if (rs9.AddFullyConnected() != kTfLiteOk) return false;
  static tflite::MicroInterpreter is9(s9_model, rs9, s9_arena, sizeof(s9_arena));
  s9_interp = &is9;
  if (s9_interp->AllocateTensors() != kTfLiteOk) return false;
  s9_in = s9_interp->input(0);
  return s9_in && s9_in->bytes >= 9;
}

static bool s9_one() {
  if (!tfl_s9_ok || !s9_in) return false;
  memcpy(s9_in->data.int8, eq_x, 9);
  return s9_interp->Invoke() == kTfLiteOk;
}

static void sort32(uint32_t *a, int n) {
  for (int i = 1; i < n; ++i) {
    uint32_t v = a[i];
    int j = i;
    while (j > 0 && a[j - 1] > v) {
      a[j] = a[j - 1];
      --j;
    }
    a[j] = v;
  }
}

static void print_pct(const char *tag, uint32_t *s, int n) {
  sort32(s, n);
  uint32_t p50 = s[n / 2];
  uint32_t p95 = s[(n * 95) / 100];
  uint32_t p99 = s[(n * 99) / 100];
  uint32_t lo = s[0], hi = s[n - 1];
  Serial.printf("OK %s p50=%lu p95=%lu p99=%lu min=%lu max=%lu n=%d CCOUNT\n",
                tag, (unsigned long)p50, (unsigned long)p95, (unsigned long)p99,
                (unsigned long)lo, (unsigned long)hi, n);
}

void tqaBenchInit() {
  memcpy(kW9_ram, kW9, sizeof(kW9));
  tfl_hw_ok = hw_init();
  // 9→1 models are initialized in BENCH only — a bad model must not boot-loop.
}

void tqaBenchRun() {
  const int N = 2000;
  float xf[9];
  for (int i = 0; i < 9; ++i) xf[i] = 0.1f * (float)(i + 1);
  float nrm = 0;
  for (int i = 0; i < 9; ++i) nrm += xf[i] * xf[i];
  nrm = sqrtf(nrm);
  for (int i = 0; i < 9; ++i) {
    xf[i] /= nrm;
    kX_ram[i] = xf[i];
    int ww = (int)lroundf(kW9[i] * 20.0f);
    int xx = (int)lroundf(xf[i] / 0.05f);
    if (ww > 127) ww = 127;
    if (ww < -128) ww = -128;
    if (xx > 127) xx = 127;
    if (xx < -128) xx = -128;
    eq_w[i] = (int8_t)ww;
    eq_x[i] = (int8_t)xx;
  }

  Serial.printf("OK tflm9f_init...\n");
  tfl_f9_ok = f9_init();
  Serial.printf("OK tflm9f_init %s\n", tfl_f9_ok ? "ok" : "FAIL");
  Serial.printf("OK tflm9s8_init...\n");
  tfl_s9_ok = s9_init();
  Serial.printf("OK tflm9s8_init %s\n", tfl_s9_ok ? "ok" : "FAIL");

  volatile float sink_f = 0;
  volatile int32_t sink_i = 0;
  for (int i = 0; i < 50; ++i) {
    sink_f += tqa_unrolled(kX_ram);
    sink_i += equal_s8_9();
    if (tfl_hw_ok) hw_one(0.5f);
    if (tfl_f9_ok) {
      f9_one();
      sink_f += f9_out->data.f[0];
    }
    if (tfl_s9_ok) s9_one();
  }

  float y_custom = tqa_unrolled(kX_ram);
  float y_tflm = 0;
  if (tfl_f9_ok && f9_one()) y_tflm = f9_out->data.f[0];
  Serial.printf("OK match custom=%.6f tflm9f=%.6f absdiff=%.3e EQUAL_MATH %s\n",
                (double)y_custom, (double)y_tflm,
                (double)fabsf(y_custom - y_tflm),
                (tfl_f9_ok && fabsf(y_custom - y_tflm) < 1e-4f) ? "yes" : "no");

  uint32_t c0, c1, t0, t1;

  c0 = ESP.getCycleCount();
  sink_f += tqa_unrolled(kX_ram);
  c1 = ESP.getCycleCount();
  Serial.printf("OK 9d_f32_cold cy=%lu CCOUNT\n", (unsigned long)(c1 - c0));

  c0 = ESP.getCycleCount();
  t0 = micros();
  for (int i = 0; i < N; ++i) sink_f += tqa_unrolled(kX_ram);
  t1 = micros();
  c1 = ESP.getCycleCount();
  uint32_t us_a = t1 - t0, cy_a = c1 - c0;

  c0 = ESP.getCycleCount();
  t0 = micros();
  for (int i = 0; i < N; ++i) sink_i += equal_s8_9();
  t1 = micros();
  c1 = ESP.getCycleCount();
  uint32_t us_b = t1 - t0, cy_b = c1 - c0;

  c0 = ESP.getCycleCount();
  t0 = micros();
  for (int i = 0; i < N; ++i) {
    esp_nn_fully_connected_s8_ansi(eq_x, 0, 9, eq_w, 0, &eq_bias, nn_out, 1, 0, 0,
                                   (1 << 30), -128, 127);
    sink_i += nn_out[0];
  }
  t1 = micros();
  c1 = ESP.getCycleCount();
  uint32_t us_c = t1 - t0, cy_c = c1 - c0;

  uint32_t us_f9 = 0, cy_f9 = 0, failf9 = 0;
  if (tfl_f9_ok) {
    c0 = ESP.getCycleCount();
    t0 = micros();
    for (int i = 0; i < N; ++i) {
      if (!f9_one()) failf9++;
    }
    t1 = micros();
    c1 = ESP.getCycleCount();
    us_f9 = t1 - t0;
    cy_f9 = c1 - c0;
  }

  uint32_t us_s9 = 0, cy_s9 = 0, fails9 = 0;
  if (tfl_s9_ok) {
    c0 = ESP.getCycleCount();
    t0 = micros();
    for (int i = 0; i < N; ++i) {
      if (!s9_one()) fails9++;
    }
    t1 = micros();
    c1 = ESP.getCycleCount();
    us_s9 = t1 - t0;
    cy_s9 = c1 - c0;
  }

  uint32_t us_hw = 0, cy_hw = 0;
  int failhw = 0;
  if (tfl_hw_ok) {
    c0 = ESP.getCycleCount();
    t0 = micros();
    for (int i = 0; i < N; ++i) {
      if (!hw_one((float)(i % 100) / 100.0f)) failhw++;
    }
    t1 = micros();
    c1 = ESP.getCycleCount();
    us_hw = t1 - t0;
    cy_hw = c1 - c0;
  }

  const int P = 128;
  uint32_t samp[128];
  noInterrupts();
  for (int i = 0; i < P; ++i) {
    c0 = ESP.getCycleCount();
    sink_f += tqa_unrolled(kX_ram);
    c1 = ESP.getCycleCount();
    samp[i] = c1 - c0;
  }
  interrupts();
  print_pct("9d_f32", samp, P);

  noInterrupts();
  for (int i = 0; i < P; ++i) {
    c0 = ESP.getCycleCount();
    sink_i += equal_s8_9();
    c1 = ESP.getCycleCount();
    samp[i] = c1 - c0;
  }
  interrupts();
  print_pct("9d_s8", samp, P);

  noInterrupts();
  for (int i = 0; i < P; ++i) {
    c0 = ESP.getCycleCount();
    esp_nn_fully_connected_s8_ansi(eq_x, 0, 9, eq_w, 0, &eq_bias, nn_out, 1, 0, 0,
                                   (1 << 30), -128, 127);
    sink_i += nn_out[0];
    c1 = ESP.getCycleCount();
    samp[i] = c1 - c0;
  }
  interrupts();
  print_pct("espnn9", samp, P);

  if (tfl_f9_ok) {
    for (int i = 0; i < P; ++i) {
      c0 = ESP.getCycleCount();
      f9_one();
      c1 = ESP.getCycleCount();
      samp[i] = c1 - c0;
    }
    print_pct("tflm9f", samp, P);
  }

  // --- fused 9→8: measured directly, not 8 × 9→1 ---
  DRAM_ATTR static float y_fuse[8];
  DRAM_ATTR static float y_eight[8];
  tensorFuse98(kX_ram, y_fuse);
  tensorEightDots(kX_ram, y_eight);
  float maxdiff = 0;
  for (int k = 0; k < 8; ++k) {
    float d = fabsf(y_fuse[k] - y_eight[k]);
    if (d > maxdiff) maxdiff = d;
  }
  Serial.printf("OK match98 fuse0=%.6f eight0=%.6f y0_vs_9d=%.3e maxdiff8=%.3e EQUAL_MATH %s\n",
                (double)y_fuse[0], (double)y_eight[0],
                (double)fabsf(y_fuse[0] - y_custom), (double)maxdiff,
                (maxdiff < 1e-5f && fabsf(y_fuse[0] - y_custom) < 1e-4f) ? "yes" : "no");

  c0 = ESP.getCycleCount();
  tensorFuse98(kX_ram, y_fuse);
  c1 = ESP.getCycleCount();
  Serial.printf("OK fuse98_cold cy=%lu CCOUNT\n", (unsigned long)(c1 - c0));

  volatile float sink8 = 0;
  c0 = ESP.getCycleCount();
  t0 = micros();
  for (int i = 0; i < N; ++i) {
    tensorFuse98(kX_ram, y_fuse);
    sink8 += y_fuse[0] + y_fuse[7];
  }
  t1 = micros();
  c1 = ESP.getCycleCount();
  uint32_t us_f98 = t1 - t0, cy_f98 = c1 - c0;

  c0 = ESP.getCycleCount();
  t0 = micros();
  for (int i = 0; i < N; ++i) {
    tensorEightDots(kX_ram, y_eight);
    sink8 += y_eight[0] + y_eight[7];
  }
  t1 = micros();
  c1 = ESP.getCycleCount();
  uint32_t us_8x = t1 - t0, cy_8x = c1 - c0;

  c0 = ESP.getCycleCount();
  t0 = micros();
  for (int i = 0; i < N; ++i) tensorOnRecv(2, 32);
  t1 = micros();
  c1 = ESP.getCycleCount();
  uint32_t us_recv = t1 - t0, cy_recv = c1 - c0;

  c0 = ESP.getCycleCount();
  t0 = micros();
  for (int i = 0; i < N; ++i) tensorOnRecvNaive8(2, 32);
  t1 = micros();
  c1 = ESP.getCycleCount();
  uint32_t us_r8 = t1 - t0, cy_r8 = c1 - c0;

  noInterrupts();
  for (int i = 0; i < P; ++i) {
    c0 = ESP.getCycleCount();
    tensorFuse98(kX_ram, y_fuse);
    c1 = ESP.getCycleCount();
    samp[i] = c1 - c0;
  }
  interrupts();
  print_pct("fuse98", samp, P);

  noInterrupts();
  for (int i = 0; i < P; ++i) {
    c0 = ESP.getCycleCount();
    tensorEightDots(kX_ram, y_eight);
    c1 = ESP.getCycleCount();
    samp[i] = c1 - c0;
  }
  interrupts();
  print_pct("eight9to1", samp, P);

  const int scales[4] = {1, 10, 100, 1000};
  for (int s = 0; s < 4; ++s) {
    t0 = micros();
    c0 = ESP.getCycleCount();
    for (int i = 0; i < scales[s]; ++i) tensorOnRecv(2, 32);
    c1 = ESP.getCycleCount();
    t1 = micros();
    Serial.printf("OK scale n=%d us=%lu cy=%lu us_each=%.3f fused_recv\n", scales[s],
                  (unsigned long)(t1 - t0), (unsigned long)(c1 - c0),
                  (t1 - t0) / (float)scales[s]);
  }

  Serial.printf("OK bench n=%d cpu_mhz=%lu equal=9mac sink=%.3f/%ld\n", N,
                (unsigned long)ESP.getCpuFreqMHz(), (double)sink_f, (long)sink_i);
  Serial.printf("OK 9d_f32   us=%lu cy=%lu us_each=%.3f cy_each=%.1f EQUAL 9fmac IRAM\n",
                (unsigned long)us_a, (unsigned long)cy_a, us_a / (float)N, cy_a / (float)N);
  Serial.printf("OK 9d_s8    us=%lu cy=%lu us_each=%.3f cy_each=%.1f EQUAL 9imac\n",
                (unsigned long)us_b, (unsigned long)cy_b, us_b / (float)N, cy_b / (float)N);
  Serial.printf("OK espnn9   us=%lu cy=%lu us_each=%.3f cy_each=%.1f EQUAL 9imac esp_nn_fc_ansi\n",
                (unsigned long)us_c, (unsigned long)cy_c, us_c / (float)N, cy_c / (float)N);
  if (tfl_f9_ok) {
    Serial.printf("OK tflm9f   us=%lu cy=%lu us_each=%.3f cy_each=%.1f EQUAL 9fmac tflm_fc fails=%lu\n",
                  (unsigned long)us_f9, (unsigned long)cy_f9, us_f9 / (float)N,
                  cy_f9 / (float)N, (unsigned long)failf9);
    Serial.printf("OK ratio_equal tflm9f/9d_f32=%.2f  (same 9-MAC float)\n",
                  us_f9 / (float)us_a);
  } else {
    Serial.printf("OK tflm9f   FAIL init (not timed)\n");
  }
  if (tfl_s9_ok) {
    Serial.printf("OK tflm9s8  us=%lu cy=%lu us_each=%.3f cy_each=%.1f EQUAL 9imac tflm_fc fails=%lu\n",
                  (unsigned long)us_s9, (unsigned long)cy_s9, us_s9 / (float)N,
                  cy_s9 / (float)N, (unsigned long)fails9);
    Serial.printf("OK ratio_equal tflm9s8/9d_s8=%.2f  (same 9-MAC int8)\n",
                  us_s9 / (float)us_b);
  } else {
    Serial.printf("OK tflm9s8  FAIL init (not timed)\n");
  }
  Serial.printf("OK ratio_equal espnn9/9d_f32=%.2f 9d_s8/9d_f32=%.2f\n",
                us_c / (float)us_a, us_b / (float)us_a);
  if (tfl_hw_ok) {
    Serial.printf("OK tflm_hw  us=%lu cy=%lu us_each=%.3f cy_each=%.1f UNEQUAL hello_world fails=%d\n",
                  (unsigned long)us_hw, (unsigned long)cy_hw, us_hw / (float)N,
                  cy_hw / (float)N, failhw);
    Serial.printf("NOTE tflm_hw is a different model. Do not use as the equal ratio.\n");
  }
  Serial.printf("OK fuse98    us=%lu cy=%lu us_each=%.3f cy_each=%.1f EQUAL 9to8 72w IRAM sink=%.3f\n",
                (unsigned long)us_f98, (unsigned long)cy_f98, us_f98 / (float)N,
                cy_f98 / (float)N, (double)sink8);
  Serial.printf("OK eight9to1 us=%lu cy=%lu us_each=%.3f cy_each=%.1f EQUAL 8x9to1 (not fused)\n",
                (unsigned long)us_8x, (unsigned long)cy_8x, us_8x / (float)N, cy_8x / (float)N);
  Serial.printf("OK ratio_equal eight9to1/fuse98=%.2f  (same 72 MAC, fused vs 8 dispatches)\n",
                us_8x / (float)us_f98);
  Serial.printf("OK recv_fuse us=%lu cy=%lu us_each=%.3f cy_each=%.1f OS parse+9to8+batch\n",
                (unsigned long)us_recv, (unsigned long)cy_recv, us_recv / (float)N,
                cy_recv / (float)N);
  Serial.printf("OK recv_x8   us=%lu cy=%lu us_each=%.3f cy_each=%.1f 8x prepare+dot+apply\n",
                (unsigned long)us_r8, (unsigned long)cy_r8, us_r8 / (float)N, cy_r8 / (float)N);
  Serial.printf("OK ratio_os  recv_x8/recv_fuse=%.2f  (do not use 8*9d_f32 as 9to8)\n",
                us_r8 / (float)us_recv);
}
