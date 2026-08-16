// SSOS packet controller — replaceable node, not a one-off toy OS.
// Model-agnostic: payload is opaque. Protocol is ssos.packet.v1.
// Same image + DUMP|PKT lines installs a replacement controller.

#include <Arduino.h>
#include <Preferences.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "tqa_bench.h"
#include "tqa_runtime.h"

struct Packet;

constexpr uint8_t DIMS = 9;
constexpr uint8_t PKT_MAX = 32;
constexpr uint8_t ID_MAX = 40;
constexpr uint8_t HASH_MAX = 16;
constexpr uint8_t PERM_MAX = 20;
constexpr uint8_t BODY_MAX = 64;
constexpr uint8_t CMD_LINE_MAX = 240;
constexpr uint8_t ROLE_MAX = 16;
// Lonely Binary Gold Edition: WS2812 already on GPIO48.
// Colors are the 9-D tensor QA face, not decoration.
constexpr uint8_t RGB_PIN = 48;

enum TqaAxis : uint8_t {
  TQA_START = 0,           // green — boot only
  TQA_PACKET_SCALE,        // yellow
  TQA_NINEBEAT,            // amber — idle / identity
  TQA_REST_RECOVERY,       // cyan
  TQA_FLUSH_BREATH,        // teal
  TQA_BURST_ENERGY,        // orange
  TQA_CACHE_RESONANCE,     // violet
  TQA_FLUSH_MARGIN,        // blue
  TQA_RECOVERY_GAP,        // magenta
  TQA_POWER_WAVE,          // white
  TQA_FAULT                // red
};

static void rgbSet(uint8_t r, uint8_t g, uint8_t b) {
  rgbLedWrite(RGB_PIN, r, g, b);
}

static void tqaShow(TqaAxis a) {
  switch (a) {
    case TQA_START:            rgbSet(0, 48, 0); break;
    case TQA_PACKET_SCALE:     rgbSet(48, 40, 0); break;
    case TQA_NINEBEAT:         rgbSet(48, 28, 0); break;
    case TQA_REST_RECOVERY:    rgbSet(0, 36, 40); break;
    case TQA_FLUSH_BREATH:     rgbSet(0, 40, 28); break;
    case TQA_BURST_ENERGY:     rgbSet(48, 16, 0); break;
    case TQA_CACHE_RESONANCE:  rgbSet(28, 0, 48); break;
    case TQA_FLUSH_MARGIN:     rgbSet(0, 12, 48); break;
    case TQA_RECOVERY_GAP:     rgbSet(40, 0, 32); break;
    case TQA_POWER_WAVE:       rgbSet(40, 40, 40); break;
    case TQA_FAULT: default:   rgbSet(48, 0, 0); break;
  }
}

enum Role : uint8_t {
  ROLE_EMPTY = 0,
  ROLE_NOTE,
  ROLE_DOCUMENT,
  ROLE_EXECUTABLE,
  ROLE_RUNTIME,
  ROLE_BOOT,
  ROLE_PAYLOAD,
  ROLE_ARCHIVE,
  ROLE_FIRMWARE,
  ROLE_COUNT
};

struct Packet {
  uint8_t used;
  uint8_t role;
  int16_t d[DIMS];
  uint16_t gen;
  char id[ID_MAX];
  char hash[HASH_MAX + 1];
  char perm[PERM_MAX];
  char body[BODY_MAX];
};

static Packet bank[PKT_MAX];
static uint16_t nextGen = 1;
static uint32_t bootCount = 0;
static uint32_t recvCount = 0;
static Preferences prefs;
static char lineBuf[CMD_LINE_MAX];
static uint8_t lineLen = 0;

static const char *roleName(uint8_t role) {
  switch (role) {
    case ROLE_NOTE: return "note";
    case ROLE_DOCUMENT: return "document";
    case ROLE_EXECUTABLE: return "executable";
    case ROLE_RUNTIME: return "runtime";
    case ROLE_BOOT: return "boot";
    case ROLE_PAYLOAD: return "payload";
    case ROLE_ARCHIVE: return "archive";
    case ROLE_FIRMWARE: return "firmware";
    default: return "empty";
  }
}

static int roleFromName(const char *name) {
  for (uint8_t r = 1; r < ROLE_COUNT; ++r)
    if (strcmp(name, roleName(r)) == 0) return r;
  return -1;
}

static uint32_t fnv1a(const char *s) {
  uint32_t h = 2166136261u;
  while (*s) {
    h ^= (uint8_t)*s++;
    h *= 16777619u;
  }
  return h;
}

static void hashOf(const char *s, char out[HASH_MAX + 1]) {
  snprintf(out, HASH_MAX + 1, "%08x", (unsigned)fnv1a(s));
}

static void zeroDims(int16_t *d) { memset(d, 0, sizeof(int16_t) * DIMS); }

static int findById(const char *id) {
  for (uint8_t i = 0; i < PKT_MAX; ++i)
    if (bank[i].used && strcmp(bank[i].id, id) == 0) return i;
  return -1;
}

static int findByCoord(const int16_t *d) {
  for (uint8_t i = 0; i < PKT_MAX; ++i)
    if (bank[i].used && memcmp(bank[i].d, d, sizeof(int16_t) * DIMS) == 0) return i;
  return -1;
}

static int allocSlot() {
  for (uint8_t i = 0; i < PKT_MAX; ++i)
    if (!bank[i].used) return i;
  return -1;
}

static uint8_t packetCount() {
  uint8_t n = 0;
  for (uint8_t i = 0; i < PKT_MAX; ++i)
    if (bank[i].used) ++n;
  return n;
}

static void printCoord(const int16_t *d) {
  Serial.printf("grid://ssos/x%d/y%d/z%d/d3:%d/d4:%d/d5:%d/d6:%d/d7:%d/d8:%d",
                (int)d[0], (int)d[1], (int)d[2], (int)d[3], (int)d[4],
                (int)d[5], (int)d[6], (int)d[7], (int)d[8]);
}

static void emitPkt(const Packet *p) {
  Serial.printf("PKT id=%s d=%d,%d,%d,%d,%d,%d,%d,%d,%d role=%s hash=%s perm=%s body=%s\n",
                p->id,
                (int)p->d[0], (int)p->d[1], (int)p->d[2], (int)p->d[3], (int)p->d[4],
                (int)p->d[5], (int)p->d[6], (int)p->d[7], (int)p->d[8],
                roleName(p->role), p->hash, p->perm, p->body);
}

static bool parseDims(const char *s, int16_t *d) {
  zeroDims(d);
  if (strncmp(s, "grid://", 7) == 0) {
    const char *px = strstr(s, "/x");
    const char *py = strstr(s, "/y");
    const char *pz = strstr(s, "/z");
    if (px) d[0] = (int16_t)atoi(px + 2);
    if (py) d[1] = (int16_t)atoi(py + 2);
    if (pz) d[2] = (int16_t)atoi(pz + 2);
    const char *p = s;
    uint8_t extra = 3;
    while (extra < DIMS && (p = strstr(p, "/d")) != nullptr) {
      p += 2;
      while (*p && *p != ':') ++p;
      if (*p == ':') d[extra++] = (int16_t)atoi(p + 1);
    }
    return true;
  }
  unsigned n = 0;
  const char *p = s;
  while (*p && n < DIMS) {
    d[n++] = (int16_t)atoi(p);
    const char *c = strchr(p, ',');
    if (!c) break;
    p = c + 1;
  }
  return n > 0;
}

static char *nextTok(char **cursor) {
  char *p = *cursor;
  if (!p) return nullptr;
  while (*p == ' ' || *p == '\t') ++p;
  if (*p == 0) {
    *cursor = p;
    return nullptr;
  }
  char *start = p;
  while (*p && *p != ' ' && *p != '\t') ++p;
  if (*p) {
    *p = 0;
    *cursor = p + 1;
  } else {
    *cursor = p;
  }
  return start;
}

static const char *kv(char **cursor, const char *key) {
  size_t klen = strlen(key);
  char *p = *cursor;
  while (*p == ' ' || *p == '\t') ++p;
  if (strncmp(p, key, klen) != 0 || p[klen] != '=') return nullptr;
  p += klen + 1;
  char *start = p;
  while (*p && *p != ' ') ++p;
  if (*p) {
    *p = 0;
    *cursor = p + 1;
  } else {
    *cursor = p;
  }
  return start;
}

static bool storePacket(const char *id, const int16_t *d, int role,
                        const char *hash, const char *perm, const char *body) {
  if (role <= ROLE_EMPTY || role >= ROLE_COUNT) return false;
  int slot = findById(id);
  if (slot < 0) slot = findByCoord(d);
  if (slot < 0) slot = allocSlot();
  if (slot < 0) return false;
  Packet *p = &bank[slot];
  memset(p, 0, sizeof(*p));
  p->used = 1;
  p->role = (uint8_t)role;
  memcpy(p->d, d, sizeof(int16_t) * DIMS);
  p->gen = nextGen++;
  strncpy(p->id, id, ID_MAX - 1);
  if (hash && hash[0]) strncpy(p->hash, hash, HASH_MAX);
  else hashOf(body ? body : "", p->hash);
  strncpy(p->perm, (perm && perm[0]) ? perm : "open", PERM_MAX - 1);
  strncpy(p->body, body ? body : "", BODY_MAX - 1);
  ++recvCount;
  return true;
}

static bool saveBank() {
  if (!prefs.begin("ssos", false)) return false;
  bool ok = prefs.putUShort("n", packetCount()) &&
            prefs.putUShort("gen", nextGen) &&
            prefs.putUInt("boots", bootCount) &&
            prefs.putBytes("bank", bank, sizeof(bank)) == sizeof(bank);
  prefs.end();
  return ok;
}

static bool loadBank() {
  if (!prefs.begin("ssos", true)) return false;
  uint16_t n = prefs.getUShort("n", 0xFFFF);
  if (n == 0xFFFF || n > PKT_MAX) {
    prefs.end();
    return false;
  }
  size_t got = prefs.getBytes("bank", bank, sizeof(bank));
  nextGen = prefs.getUShort("gen", 1);
  bootCount = prefs.getUInt("boots", 0);
  prefs.end();
  return got == sizeof(bank);
}

static void seedController() {
  memset(bank, 0, sizeof(bank));
  nextGen = 1;
  int16_t d[DIMS];
  zeroDims(d);
  storePacket("ctrl:kernel", d, ROLE_BOOT, nullptr, "open", "ssos.packet.v1");
  d[0] = 1;
  storePacket("ctrl:usb", d, ROLE_RUNTIME, nullptr, "open", "port:usb");
}

static void cmdId() {
  uint64_t mac = ESP.getEfuseMac();
  Serial.printf("OK SSOS_ESP32 proto=ssos.packet.v1 model=any replaceable=1 fuse=9to8 "
                "chip=esp32s3 mac=%04X%08X boots=%lu packets=%u recv=%lu\n",
                (unsigned)(mac >> 32), (unsigned)mac,
                (unsigned long)bootCount, packetCount(), (unsigned long)recvCount);
}

static void cmdHelp() {
  Serial.println("OK ssos.packet.v1 replaceable packet controller");
  Serial.println("  ID DUMP PKT GET DEL STATS SAVE LOAD CLEAR TENSOR TSET TRESET MODEL MLOAD MINFER MCLEAR BENCH HELP");
  Serial.println("  PKT id=... d=x,y,z,d3,d4,d5,d6,d7,d8 role=... hash=... perm=... body=...");
  Serial.println("  GET id=... | GET d=...");
  Serial.println("  DUMP is the install tape for a replacement controller");
  Serial.println("  TENSOR TSET i=0..8 v=... TRESET  — live 9-D tensor");
  Serial.println("  MODEL MLOAD MINFER x=x0,...,x8 MCLEAR — packet-backed 9-D model head");
  Serial.println("  model rows: PKT id=model:w:0..7 ... body=q0,...,q8 (signed Q10)");
  Serial.println("GPIO48 follows dominant tensor axis (green=start, red=fault):");
  Serial.println("  green=start  amber=idle/9beat  yellow=DUMP/scale");
  Serial.println("  orange=PKT/burst  violet=GET/cache  teal=SAVE/flush");
  Serial.println("  cyan=LOAD/recover  blue=DEL/margin  magenta=HELP");
  Serial.println("  white=CLEAR/wave  red=FAULT");
}

static void cmdDump() {
  Serial.printf("OK dump proto=ssos.packet.v1 count=%u\n", packetCount());
  for (uint8_t i = 0; i < PKT_MAX; ++i)
    if (bank[i].used) emitPkt(&bank[i]);
  Serial.println("OK end");
}

static void cmdStats() {
  Serial.printf("OK stats packets=%u free=%u next_gen=%u recv=%lu uptime_ms=%lu\n",
                packetCount(), PKT_MAX - packetCount(), nextGen,
                (unsigned long)recvCount, (unsigned long)millis());
  tensorPrint();
  Serial.printf("OK model ready=%u dims=9 outputs=8 weights=72\n", modelReady() ? 1 : 0);
}

static bool parseFloat9(const char *s, float out[9]) {
  const char *p = s;
  for (int i = 0; i < 9; ++i) {
    char *end = nullptr;
    out[i] = strtof(p, &end);
    if (end == p || !isfinite(out[i])) return false;
    if (i < 8) {
      if (*end != ',') return false;
      p = end + 1;
    } else if (*end != 0 && *end != ' ') {
      return false;
    }
  }
  return true;
}

static void printModel();

static void printModel() {
  uint8_t rows = 0;
  char id[20];
  for (int r = 0; r < 8; ++r) {
    snprintf(id, sizeof(id), "model:w:%d", r);
    if (findById(id) >= 0) ++rows;
  }
  Serial.printf("OK model ready=%u source=packet-bank encoding=q10 rows=%u dims=9 outputs=8 weights=72\n",
                modelReady() ? 1 : 0, rows);
}

static bool isModelPacketId(const char *id) {
  return id && strncmp(id, "model:w:", 8) == 0;
}

static bool parseModelQ10Row(const char *body, float out[9]) {
  const char *p = body;
  for (int i = 0; i < 9; ++i) {
    char *end = nullptr;
    long value = strtol(p, &end, 10);
    if (end == p || value < -8192 || value > 8192) return false;
    out[i] = (float)value / 1024.0f;
    if (i < 8) {
      if (*end != ',') return false;
      p = end + 1;
    } else if (*end != 0) {
      return false;
    }
  }
  return true;
}

static bool loadModelPackets() {
  float weights[72];
  char id[20];
  for (int r = 0; r < 8; ++r) {
    snprintf(id, sizeof(id), "model:w:%d", r);
    int slot = findById(id);
    if (slot < 0 || !parseModelQ10Row(bank[slot].body, weights + r * 9)) {
      modelClear();
      return false;
    }
  }
  modelLoadW72(weights);
  return true;
}

static void clearModelPackets() {
  char id[20];
  for (int r = 0; r < 8; ++r) {
    snprintf(id, sizeof(id), "model:w:%d", r);
    int slot = findById(id);
    if (slot >= 0) bank[slot].used = 0;
  }
  modelClear();
}

static void handlePkt(char *cur) {
  const char *id = nullptr;
  const char *ds = nullptr;
  const char *role = nullptr;
  const char *hash = nullptr;
  const char *perm = nullptr;
  const char *body = nullptr;
  char *scan = cur;
  while (*scan) {
    while (*scan == ' ') ++scan;
    if (!*scan) break;
    if (strncmp(scan, "id=", 3) == 0) { id = kv(&scan, "id"); continue; }
    if (strncmp(scan, "d=", 2) == 0) { ds = kv(&scan, "d"); continue; }
    if (strncmp(scan, "coord=", 6) == 0) { ds = kv(&scan, "coord"); continue; }
    if (strncmp(scan, "role=", 5) == 0) { role = kv(&scan, "role"); continue; }
    if (strncmp(scan, "hash=", 5) == 0) { hash = kv(&scan, "hash"); continue; }
    if (strncmp(scan, "perm=", 5) == 0) { perm = kv(&scan, "perm"); continue; }
    if (strncmp(scan, "body=", 5) == 0) {
      scan += 5;
      body = scan;
      break;
    }
    Serial.println("ERR unknown PKT field");
    tensorOnFault();
    tqaShow(TQA_FAULT);
    return;
  }
  if (!id || !ds || !role) {
    Serial.println("ERR usage: PKT id=... d=... role=... [hash=...] [perm=...] [body=...]");
    tqaShow(TQA_FAULT);
    return;
  }
  int16_t dims[DIMS];
  if (!parseDims(ds, dims)) {
    Serial.println("ERR bad coordinate");
    tqaShow(TQA_FAULT);
    return;
  }
  char roleBuf[ROLE_MAX];
  strncpy(roleBuf, role, ROLE_MAX - 1);
  roleBuf[ROLE_MAX - 1] = 0;
  for (char *p = roleBuf; *p; ++p)
    if (*p >= 'A' && *p <= 'Z') *p = (char)(*p - 'A' + 'a');
  int r = roleFromName(roleBuf);
  if (r < 0) {
    Serial.println("ERR unknown role");
    tqaShow(TQA_FAULT);
    return;
  }
  if (!storePacket(id, dims, r, hash, perm, body ? body : "")) {
    Serial.println("ERR bank full or bad packet");
    tensorOnFault();
    tqaShow(TQA_FAULT);
    return;
  }
  if (isModelPacketId(id)) modelClear();
  tensorOnRecv(packetCount(), PKT_MAX);
  tqaShow((TqaAxis)(TQA_PACKET_SCALE + tensorDominant()));
  int slot = findById(id);
  Serial.print("OK recv ");
  emitPkt(&bank[slot]);
}

static void handleGet(char *cur) {
  while (*cur == ' ') ++cur;
  if (strncmp(cur, "id=", 3) == 0) {
    const char *id = kv(&cur, "id");
    int slot = id ? findById(id) : -1;
    if (slot < 0) { tensorOnGet(false); tensorOnFault(); tqaShow(TQA_FAULT); Serial.println("ERR not found"); return; }
    tensorOnGet(true);
    tqaShow((TqaAxis)(TQA_PACKET_SCALE + tensorDominant()));
    Serial.print("OK ");
    emitPkt(&bank[slot]);
    return;
  }
  const char *ds = nullptr;
  if (strncmp(cur, "d=", 2) == 0) ds = kv(&cur, "d");
  else if (strncmp(cur, "coord=", 6) == 0) ds = kv(&cur, "coord");
  else ds = nextTok(&cur);
  if (!ds) { tqaShow(TQA_FAULT); Serial.println("ERR usage: GET id=... | GET d=..."); return; }
  int16_t dims[DIMS];
  if (!parseDims(ds, dims)) { tqaShow(TQA_FAULT); Serial.println("ERR bad coordinate"); return; }
  int slot = findByCoord(dims);
  if (slot < 0) { tqaShow(TQA_FAULT); Serial.println("ERR not found"); return; }
  Serial.print("OK ");
  emitPkt(&bank[slot]);
}

static void handleDel(char *cur) {
  while (*cur == ' ') ++cur;
  if (strncmp(cur, "id=", 3) != 0) {
    tqaShow(TQA_FAULT);
    Serial.println("ERR usage: DEL id=...");
    return;
  }
  const char *id = kv(&cur, "id");
  int slot = id ? findById(id) : -1;
  if (slot < 0) { tqaShow(TQA_FAULT); Serial.println("ERR not found"); return; }
  bool wasModel = isModelPacketId(id);
  bank[slot].used = 0;
  if (wasModel) modelClear();
  Serial.printf("OK deleted id=%s\n", id);
}

static void handleLine(char *line) {
  while (*line == ' ' || *line == '\t') ++line;
  size_t n = strlen(line);
  while (n && (line[n - 1] == '\r' || line[n - 1] == '\n' || line[n - 1] == ' '))
    line[--n] = 0;
  if (!n) return;
  char *cmdEnd = line;
  while (*cmdEnd && *cmdEnd != ' ') ++cmdEnd;
  char saved = *cmdEnd;
  *cmdEnd = 0;
  for (char *p = line; *p; ++p)
    if (*p >= 'a' && *p <= 'z') *p = (char)(*p - 'a' + 'A');
  char *rest = saved ? cmdEnd + 1 : cmdEnd;
  if (strcmp(line, "HELP") == 0 || strcmp(line, "?") == 0) {
    tqaShow(TQA_RECOVERY_GAP);
    cmdHelp();
    return;
  }
  if (strcmp(line, "ID") == 0) { tqaShow(TQA_NINEBEAT); cmdId(); return; }
  if (strcmp(line, "DUMP") == 0) { tqaShow(TQA_PACKET_SCALE); cmdDump(); return; }
  if (strcmp(line, "STATS") == 0) { tqaShow(TQA_NINEBEAT); cmdStats(); return; }
  if (strcmp(line, "SAVE") == 0) {
    bool ok = saveBank();
    tqaShow(ok ? TQA_FLUSH_BREATH : TQA_FAULT);
    Serial.println(ok ? "OK saved" : "ERR save failed");
    return;
  }
  if (strcmp(line, "LOAD") == 0) {
    bool ok = loadBank();
    if (ok) loadModelPackets();
    tqaShow(ok ? TQA_REST_RECOVERY : TQA_FAULT);
    Serial.println(ok ? "OK loaded" : "ERR load failed");
    return;
  }
  if (strcmp(line, "CLEAR") == 0) {
    seedController();
    modelClear();
    tqaShow(TQA_POWER_WAVE);
    Serial.println("OK cleared");
    return;
  }
  if (strcmp(line, "PKT") == 0) { tqaShow(TQA_BURST_ENERGY); handlePkt(rest); return; }
  if (strcmp(line, "GET") == 0) { tqaShow(TQA_CACHE_RESONANCE); handleGet(rest); return; }
  if (strcmp(line, "DEL") == 0) { tqaShow(TQA_FLUSH_MARGIN); handleDel(rest); return; }
  if (strcmp(line, "BENCH") == 0) { tqaShow(TQA_BURST_ENERGY); tqaBenchRun(); return; }
  if (strcmp(line, "TENSOR") == 0) {
    tqaShow((TqaAxis)(TQA_PACKET_SCALE + tensorDominant()));
    tensorPrint();
    return;
  }
  if (strcmp(line, "TRESET") == 0) {
    tensorResetSeed();
    tqaShow(TQA_POWER_WAVE);
    Serial.println("OK tensor reset to trained seed");
    tensorPrint();
    return;
  }
  if (strcmp(line, "TSET") == 0) {
    int idx = -1;
    float val = 0;
    char *p = rest;
    while (*p) {
      while (*p == ' ') ++p;
      if (strncmp(p, "i=", 2) == 0) { idx = atoi(p + 2); while (*p && *p != ' ') ++p; continue; }
      if (strncmp(p, "v=", 2) == 0) { val = (float)atof(p + 2); while (*p && *p != ' ') ++p; continue; }
      break;
    }
    if (!tensorSetW(idx, val)) {
      tensorOnFault();
      tqaShow(TQA_FAULT);
      Serial.println("ERR usage: TSET i=0..8 v=...");
      return;
    }
    tqaShow((TqaAxis)(TQA_PACKET_SCALE + tensorDominant()));
    Serial.println("OK tensor weight set");
    tensorPrint();
    return;
  }
  if (strcmp(line, "MODEL") == 0) { printModel(); return; }
  if (strcmp(line, "MCLEAR") == 0) {
    clearModelPackets();
    Serial.println("OK model packets cleared; send SAVE to persist");
    return;
  }
  if (strcmp(line, "MLOAD") == 0) {
    bool ok = loadModelPackets();
    Serial.println(ok ? "OK model loaded from packet bank" : "ERR model requires valid model:w:0..7 Q10 packets");
    return;
  }
  if (strcmp(line, "MINFER") == 0) {
    while (*rest == ' ') ++rest;
    if (strncmp(rest, "x=", 2) != 0) { Serial.println("ERR usage: MINFER x=x0,...,x8"); return; }
    float input[9], output[8];
    if (!modelReady()) { Serial.println("ERR model not loaded"); return; }
    if (!parseFloat9(rest + 2, input)) { Serial.println("ERR bad 9-D input"); return; }
    modelInfer(input, output);
    int best = 0;
    for (int i = 1; i < 8; ++i) if (output[i] > output[best]) best = i;
    Serial.printf("OK model y8=%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f argmax=%d\n",
                  output[0], output[1], output[2], output[3], output[4], output[5], output[6], output[7], best);
    return;
  }
  tensorOnFault();
  tqaShow(TQA_FAULT);
  Serial.println("ERR unknown command");
}

void setup() {
  tqaShow(TQA_START);
  Serial.begin(115200);
  delay(400);
  tqaBenchInit();
  tensorInit();
  if (!loadBank()) seedController();
  loadModelPackets();
  ++bootCount;
  Serial.println("SSOS_ESP32 ready proto=ssos.packet.v1 tensor=9to8.fused");
  cmdId();
  tensorPrint();
  tqaShow((TqaAxis)(TQA_PACKET_SCALE + tensorDominant()));
}

void loop() {
  tensorTick();
  if (tensorSinceFlush() >= tensorFlushN()) {
    if (saveBank()) tensorClearFlush();
  }
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      lineBuf[lineLen] = 0;
      handleLine(lineBuf);
      lineLen = 0;
    } else if (lineLen + 1 < CMD_LINE_MAX) {
      lineBuf[lineLen++] = ch;
    }
  }
}
