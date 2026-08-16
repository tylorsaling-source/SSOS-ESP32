// Live 9-D tensor. Fused 9→8 is the OS matcher: one parse, 72 weights, 8 outputs.
#include "tqa_runtime.h"
#include <Arduino.h>
#include <math.h>
#include <string.h>

static const float kSeed[9] = {
    2.963291013f, 2.926582026f, 2.981645507f, 2.975527342f, 2.928876338f,
    2.933746679f, 1.077591796f, 2.90745369f, 2.919062847f};

static const char *kName[9] = {
    "packet_scale", "9beat", "rest_recovery", "flush_breath", "burst_energy",
    "cache_res", "flush_margin", "recovery_gap", "power_wave_fit"};

// Row-major 8×9. Row 0 is the original 9→1 seed so y0 matches 9d_f32.
static DRAM_ATTR alignas(16) float w72[72];
static DRAM_ATTR float x[9];
static DRAM_ATTR float y8[8];
static float score = 0;
static uint16_t burst = 2;
static uint16_t rest_ms = 2;
static uint16_t flush_n = 8;
static uint16_t scale = 8;
static uint32_t win_n = 0;
static uint32_t win_t0 = 0;
static uint32_t last_rate = 0;
static uint32_t rest_until = 0;
static uint8_t last_get_hit = 1;
static uint8_t recent_fault = 0;
static uint32_t since_flush = 0;
static uint8_t pending_ack = 0;

static float clampf(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

static void seed_w72() {
  for (int r = 0; r < 8; ++r) {
    for (int i = 0; i < 9; ++i) {
      float s = kSeed[(i + r) % 9];
      if (r == 0)
        w72[r * 9 + i] = kSeed[i];
      else
        w72[r * 9 + i] = s * (0.85f + 0.05f * (float)r);
    }
  }
}

// Load x into registers once, then eight unrolled rows over contiguous W.
void IRAM_ATTR tensorFuse98(const float *xin, float *yout) {
  const float x0 = xin[0], x1 = xin[1], x2 = xin[2], x3 = xin[3], x4 = xin[4];
  const float x5 = xin[5], x6 = xin[6], x7 = xin[7], x8 = xin[8];
  const float *w = w72;
  yout[0] = w[0]*x0+w[1]*x1+w[2]*x2+w[3]*x3+w[4]*x4+w[5]*x5+w[6]*x6+w[7]*x7+w[8]*x8;
  w += 9;
  yout[1] = w[0]*x0+w[1]*x1+w[2]*x2+w[3]*x3+w[4]*x4+w[5]*x5+w[6]*x6+w[7]*x7+w[8]*x8;
  w += 9;
  yout[2] = w[0]*x0+w[1]*x1+w[2]*x2+w[3]*x3+w[4]*x4+w[5]*x5+w[6]*x6+w[7]*x7+w[8]*x8;
  w += 9;
  yout[3] = w[0]*x0+w[1]*x1+w[2]*x2+w[3]*x3+w[4]*x4+w[5]*x5+w[6]*x6+w[7]*x7+w[8]*x8;
  w += 9;
  yout[4] = w[0]*x0+w[1]*x1+w[2]*x2+w[3]*x3+w[4]*x4+w[5]*x5+w[6]*x6+w[7]*x7+w[8]*x8;
  w += 9;
  yout[5] = w[0]*x0+w[1]*x1+w[2]*x2+w[3]*x3+w[4]*x4+w[5]*x5+w[6]*x6+w[7]*x7+w[8]*x8;
  w += 9;
  yout[6] = w[0]*x0+w[1]*x1+w[2]*x2+w[3]*x3+w[4]*x4+w[5]*x5+w[6]*x6+w[7]*x7+w[8]*x8;
  w += 9;
  yout[7] = w[0]*x0+w[1]*x1+w[2]*x2+w[3]*x3+w[4]*x4+w[5]*x5+w[6]*x6+w[7]*x7+w[8]*x8;
}

// Eight separate 9→1 dispatches. Exists only so BENCH does not fake 9→8 as 8× 9→1.
void IRAM_ATTR tensorEightDots(const float *xin, float *yout) {
  for (int r = 0; r < 8; ++r) {
    const float *w = w72 + r * 9;
    yout[r] = w[0]*xin[0]+w[1]*xin[1]+w[2]*xin[2]+w[3]*xin[3]+w[4]*xin[4]+
              w[5]*xin[5]+w[6]*xin[6]+w[7]*xin[7]+w[8]*xin[8];
  }
}

static void IRAM_ATTR apply_batch() {
  score = y8[0];
  scale = (uint16_t)clampf(1.0f + y8[1] * 0.35f, 1, 16);
  burst = (uint16_t)clampf(1.0f + y8[2] * 0.25f, 1, 8);
  rest_ms = (uint16_t)clampf(y8[3] * 0.8f, 0, 40);
  flush_n = (uint16_t)clampf(4.0f + y8[4] * 0.6f, 4, 24);
  pending_ack = 1;
  (void)y8[5];
  (void)y8[6];
  (void)y8[7];
}

static void fill_x(uint8_t used, uint8_t cap) {
  float full = cap ? (float)used / (float)cap : 0;
  uint32_t now = millis();
  float beat = (float)((now / 111u) % 9u) / 8.0f;
  x[0] = full;
  x[1] = beat;
  x[2] = rest_ms > 0 ? 0.7f : 0.2f;
  x[3] = flush_n ? (float)since_flush / (float)flush_n : 0;
  if (x[3] > 1) x[3] = 1;
  x[4] = burst ? (float)win_n / (float)burst : 0;
  if (x[4] > 1) x[4] = 1;
  x[5] = last_get_hit ? 0.8f : 0.2f;
  x[6] = 1.0f - full;
  x[7] = recent_fault ? 1.0f : 0.1f;
  x[8] = clampf((score + 8.0f) / 24.0f, 0, 1);
}

static void learn_batch(bool better) {
  const float lr = 0.03f;
  const float s = better ? lr : -lr;
  for (int r = 0; r < 8; ++r) {
    float *row = w72 + r * 9;
    for (int i = 0; i < 9; ++i) {
      row[i] += s * x[i];
      row[i] = clampf(row[i], 0.25f, 4.0f);
    }
  }
}

static void maybe_adapt() {
  if (win_n < burst) return;
  uint32_t dt = millis() - win_t0;
  if (dt < 1) dt = 1;
  uint32_t rate = (win_n * 1000u) / dt;
  bool better = last_rate == 0 || rate >= last_rate;
  if (last_rate) learn_batch(better);
  last_rate = rate;
  win_n = 0;
  win_t0 = millis();
  if (rest_ms) rest_until = millis() + rest_ms;
  pending_ack = 0;
}

void tensorInit() {
  seed_w72();
  memset(x, 0, sizeof(x));
  memset(y8, 0, sizeof(y8));
  x[1] = 0.5f;
  x[2] = 0.5f;
  x[6] = 1.0f;
  win_t0 = millis();
  tensorFuse98(x, y8);
  apply_batch();
}

void tensorOnRecv(uint8_t used, uint8_t cap) {
  ++win_n;
  ++since_flush;
  fill_x(used, cap);
  tensorFuse98(x, y8);
  apply_batch();
  maybe_adapt();
}

// Eight prepare+dot+apply passes. Bench only — not the live path.
void tensorOnRecvNaive8(uint8_t used, uint8_t cap) {
  ++win_n;
  ++since_flush;
  for (int k = 0; k < 8; ++k) {
    fill_x(used, cap);
    const float *w = w72 + k * 9;
    y8[k] = w[0]*x[0]+w[1]*x[1]+w[2]*x[2]+w[3]*x[3]+w[4]*x[4]+
            w[5]*x[5]+w[6]*x[6]+w[7]*x[7]+w[8]*x[8];
  }
  apply_batch();
  maybe_adapt();
}

void tensorOnGet(bool hit) {
  last_get_hit = hit ? 1 : 0;
  fill_x(0, 1);
  tensorFuse98(x, y8);
  apply_batch();
}

void tensorOnFault() {
  recent_fault = 1;
  fill_x(0, 1);
  tensorFuse98(x, y8);
  apply_batch();
  rest_until = millis() + (uint32_t)(4 + w72[6 * 9 + 7] * 6.0f);
}

void tensorTick() {
  if (recent_fault && millis() > rest_until) recent_fault = 0;
}

void tensorPrint() {
  Serial.printf("OK tensor score=%.3f burst=%u rest_ms=%u flush_n=%u scale=%u rate=%lu fuse=9to8\n",
                (double)score, burst, rest_ms, flush_n, scale, (unsigned long)last_rate);
  Serial.print("OK y8=");
  for (int i = 0; i < 8; ++i) Serial.printf("%s%.3f", i ? "," : "", (double)y8[i]);
  Serial.println();
  Serial.print("OK x=");
  for (int i = 0; i < 9; ++i) Serial.printf("%s%.3f", i ? "," : "", (double)x[i]);
  Serial.println();
  Serial.printf("OK axis=%s\n", kName[tensorDominant()]);
}

void tensorResetSeed() {
  seed_w72();
  tensorFuse98(x, y8);
  apply_batch();
}

bool tensorSetW(int i, float v) {
  if (i < 0 || i > 8) return false;
  w72[i] = clampf(v, 0.25f, 4.0f);
  tensorFuse98(x, y8);
  apply_batch();
  return true;
}

uint16_t tensorBurst() { return burst; }
uint16_t tensorRestMs() { return rest_ms; }
uint16_t tensorFlushN() { return flush_n; }
uint16_t tensorScale() { return scale; }
float tensorScore() { return score; }

int tensorDominant() {
  int best = 0;
  float mag = fabsf(w72[0] * x[0]);
  for (int i = 1; i < 9; ++i) {
    float m = fabsf(w72[i] * x[i]);
    if (m > mag) {
      mag = m;
      best = i;
    }
  }
  return best;
}

void tensorLoadW(const float in[9]) {
  memcpy(w72, in, 9 * sizeof(float));
  tensorFuse98(x, y8);
  apply_batch();
}
void tensorSaveW(float out[9]) { memcpy(out, w72, 9 * sizeof(float)); }

uint32_t tensorRestUntil() { return rest_until; }
uint32_t tensorSinceFlush() { return since_flush; }
void tensorClearFlush() { since_flush = 0; }

const float *tensorW72() { return w72; }
void tensorCopyY8(float out[8]) { memcpy(out, y8, sizeof(y8)); }
void tensorCopyX(float out[9]) { memcpy(out, x, sizeof(x)); }
