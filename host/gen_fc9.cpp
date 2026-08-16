// Host-only: emit a TFLM 9→1 FullyConnected model (float32 and int8).
// Built against the same schema_generated.h the chip uses.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "flatbuffers/flatbuffers.h"
#include "tensorflow/lite/schema/schema_generated.h"

static const float kW9[9] = {
    2.963291013f, 2.926582026f, 2.981645507f, 2.975527342f, 2.928876338f,
    2.933746679f, 1.077591796f, 2.90745369f, 2.919062847f};

static void write_c_array(const char *path, const char *sym,
                          const uint8_t *data, size_t n) {
  FILE *f = fopen(path, "w");
  if (!f) {
    perror(path);
    return;
  }
  fprintf(f, "#include \"%s.h\"\n", sym);
  fprintf(f, "alignas(16) const unsigned char %s[] = {\n", sym);
  for (size_t i = 0; i < n; ++i) {
    if ((i % 12) == 0) fputs("  ", f);
    fprintf(f, "0x%02x,", data[i]);
    fputc(((i % 12) == 11 || i + 1 == n) ? '\n' : ' ', f);
  }
  fprintf(f, "};\nconst int %s_len = %zu;\n", sym, n);
  fclose(f);

  std::string hpath = std::string(path);
  auto dot = hpath.rfind('.');
  if (dot != std::string::npos) hpath.replace(dot, std::string::npos, ".h");
  FILE *h = fopen(hpath.c_str(), "w");
  if (!h) {
    perror(hpath.c_str());
    return;
  }
  fprintf(h,
          "#pragma once\n"
          "extern const unsigned char %s[];\n"
          "extern const int %s_len;\n",
          sym, sym);
  fclose(h);
}

static void emit_float(const char *c_path) {
  fprintf(stderr, "emit_float start\n");
  flatbuffers::FlatBufferBuilder fbb(2048, nullptr, false, 16);
  std::vector<uint8_t> empty;
  auto b0 = tflite::CreateBuffer(fbb);
  fprintf(stderr, "b0\n");
  std::vector<uint8_t> wbytes(sizeof(kW9));
  memcpy(wbytes.data(), kW9, sizeof(kW9));
  auto wvec = fbb.CreateVector(wbytes);
  auto b1 = tflite::CreateBuffer(fbb, wvec);
  fprintf(stderr, "b1\n");
  float bias = 0.f;
  std::vector<uint8_t> bbytes(sizeof(bias));
  memcpy(bbytes.data(), &bias, sizeof(bias));
  auto bvec = fbb.CreateVector(bbytes);
  auto b2 = tflite::CreateBuffer(fbb, bvec);
  auto b3 = tflite::CreateBuffer(fbb);
  fprintf(stderr, "buffers ok\n");

  std::vector<int32_t> in_shape{1, 9};
  std::vector<int32_t> w_shape{1, 9};
  std::vector<int32_t> bias_shape{1};
  std::vector<int32_t> out_shape{1, 1};

  auto t_in = tflite::CreateTensorDirect(fbb, &in_shape, tflite::TensorType_FLOAT32,
                                         0, "in");
  auto t_w = tflite::CreateTensorDirect(fbb, &w_shape, tflite::TensorType_FLOAT32,
                                        1, "w");
  auto t_b = tflite::CreateTensorDirect(fbb, &bias_shape, tflite::TensorType_FLOAT32,
                                        2, "b");
  auto t_out = tflite::CreateTensorDirect(fbb, &out_shape, tflite::TensorType_FLOAT32,
                                          3, "out");
  fprintf(stderr, "tensors ok\n");

  auto fc_opts = tflite::CreateFullyConnectedOptions(fbb);
  std::vector<int32_t> op_in{0, 1, 2};
  std::vector<int32_t> op_out{3};
  auto op = tflite::CreateOperatorDirect(
      fbb, 0, &op_in, &op_out, tflite::BuiltinOptions_FullyConnectedOptions,
      fc_opts.Union());
  fprintf(stderr, "op ok\n");

  std::vector<flatbuffers::Offset<tflite::Tensor>> tensors{t_in, t_w, t_b, t_out};
  std::vector<flatbuffers::Offset<tflite::Operator>> ops{op};
  std::vector<int32_t> sg_in{0};
  std::vector<int32_t> sg_out{3};
  auto sg = tflite::CreateSubGraphDirect(fbb, &tensors, &sg_in, &sg_out, &ops, "m");
  fprintf(stderr, "subgraph ok\n");

  auto opcode = tflite::CreateOperatorCode(fbb, /*deprecated*/ 9, 0, 1,
                                           tflite::BuiltinOperator_FULLY_CONNECTED);
  std::vector<flatbuffers::Offset<tflite::OperatorCode>> opcodes{opcode};
  std::vector<flatbuffers::Offset<tflite::SubGraph>> sgs{sg};
  std::vector<flatbuffers::Offset<tflite::Buffer>> bufs{b0, b1, b2, b3};
  auto model = tflite::CreateModelDirect(fbb, 3, &opcodes, &sgs, "fc9f", &bufs);
  fprintf(stderr, "model ok\n");
  tflite::FinishModelBuffer(fbb, model);
  fprintf(stderr, "finish size=%u\n", (unsigned)fbb.GetSize());
  write_c_array(c_path, "g_fc9f", fbb.GetBufferPointer(), fbb.GetSize());
  fprintf(stderr, "float model %u bytes\n", (unsigned)fbb.GetSize());
}

static void emit_s8(const char *c_path) {
  flatbuffers::FlatBufferBuilder fbb(1024);
  int8_t w[9];
  for (int i = 0; i < 9; ++i) {
    int v = (int)lroundf(kW9[i] * 20.0f);
    if (v > 127) v = 127;
    if (v < -128) v = -128;
    w[i] = (int8_t)v;
  }
  auto b0 = tflite::CreateBuffer(fbb);
  std::vector<uint8_t> wbytes(w, w + 9);
  auto b1 = tflite::CreateBufferDirect(fbb, &wbytes);
  int32_t bias = 0;
  std::vector<uint8_t> bbytes(sizeof(bias));
  memcpy(bbytes.data(), &bias, sizeof(bias));
  auto b2 = tflite::CreateBufferDirect(fbb, &bbytes);
  auto b3 = tflite::CreateBuffer(fbb);

  auto qparams = [](flatbuffers::FlatBufferBuilder &fb, float scale, int64_t zp) {
    std::vector<float> sc{scale};
    std::vector<int64_t> z{zp};
    return tflite::CreateQuantizationParameters(
        fb, 0, 0, fb.CreateVector(sc), fb.CreateVector(z));
  };

  std::vector<int32_t> in_shape{1, 9};
  std::vector<int32_t> w_shape{1, 9};
  std::vector<int32_t> bias_shape{1};
  std::vector<int32_t> out_shape{1, 1};
  const float xs = 0.05f, ws = 0.05f, os = 0.25f;

  auto t_in = tflite::CreateTensorDirect(fbb, &in_shape, tflite::TensorType_INT8, 0,
                                         "in", qparams(fbb, xs, 0));
  auto t_w = tflite::CreateTensorDirect(fbb, &w_shape, tflite::TensorType_INT8, 1,
                                        "w", qparams(fbb, ws, 0));
  auto t_b = tflite::CreateTensorDirect(fbb, &bias_shape, tflite::TensorType_INT32, 2,
                                        "b", qparams(fbb, xs * ws, 0));
  auto t_out = tflite::CreateTensorDirect(fbb, &out_shape, tflite::TensorType_INT8, 3,
                                          "out", qparams(fbb, os, 0));

  auto fc_opts = tflite::CreateFullyConnectedOptions(fbb);
  std::vector<int32_t> op_in{0, 1, 2};
  std::vector<int32_t> op_out{3};
  auto op = tflite::CreateOperatorDirect(
      fbb, 0, &op_in, &op_out, tflite::BuiltinOptions_FullyConnectedOptions,
      fc_opts.Union());

  std::vector<flatbuffers::Offset<tflite::Tensor>> tensors{t_in, t_w, t_b, t_out};
  std::vector<flatbuffers::Offset<tflite::Operator>> ops{op};
  std::vector<int32_t> sg_in{0};
  std::vector<int32_t> sg_out{3};
  auto sg = tflite::CreateSubGraphDirect(fbb, &tensors, &sg_in, &sg_out, &ops, "m");

  auto opcode = tflite::CreateOperatorCode(fbb, 9, 0, 1,
                                           tflite::BuiltinOperator_FULLY_CONNECTED);
  std::vector<flatbuffers::Offset<tflite::OperatorCode>> opcodes{opcode};
  std::vector<flatbuffers::Offset<tflite::SubGraph>> sgs{sg};
  std::vector<flatbuffers::Offset<tflite::Buffer>> bufs{b0, b1, b2, b3};
  auto model = tflite::CreateModelDirect(fbb, 3, &opcodes, &sgs, "fc9s8", &bufs);
  tflite::FinishModelBuffer(fbb, model);
  write_c_array(c_path, "g_fc9s8", fbb.GetBufferPointer(), fbb.GetSize());
  fprintf(stderr, "int8 model %u bytes\n", (unsigned)fbb.GetSize());
}

int main(int argc, char **argv) {
  fprintf(stderr, "main\n");
  std::string dir = argc > 1 ? argv[1] : "firmware/ssos_kernel";
  if (!dir.empty() && dir.back() != '/') dir.push_back('/');
  emit_float((dir + "model_fc9f.cpp").c_str());
  emit_s8((dir + "model_fc9s8.cpp").c_str());
  return 0;
}
