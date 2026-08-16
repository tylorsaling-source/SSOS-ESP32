#!/usr/bin/env python3
"""Host-only TFL3 9→1 FullyConnected model (float32 + int8)."""
import os
import struct
import sys

sys.path.insert(0, "/tmp/tflvenv/lib/python3.14/site-packages")
import flatbuffers

W9 = (
    2.963291013, 2.926582026, 2.981645507, 2.975527342, 2.928876338,
    2.933746679, 1.077591796, 2.90745369, 2.919062847,
)

TENSORTYPE_F32 = 0
TENSORTYPE_I32 = 2
TENSORTYPE_I8 = 9
BUILTIN_FC = 9
BUILTINOPTS_FC = 8


def vec_u8(b, data: bytes):
    b.StartVector(1, len(data), 1)
    for x in reversed(data):
        b.PrependByte(x)
    return b.EndVector()


def vec_i32(b, vals):
    b.StartVector(4, len(vals), 4)
    for v in reversed(vals):
        b.PrependInt32(int(v))
    return b.EndVector()


def vec_f32(b, vals):
    b.StartVector(4, len(vals), 4)
    for v in reversed(vals):
        b.PrependFloat32(float(v))
    return b.EndVector()


def vec_i64(b, vals):
    b.StartVector(8, len(vals), 8)
    for v in reversed(vals):
        b.PrependInt64(int(v))
    return b.EndVector()


def vec_off(b, offs):
    b.StartVector(4, len(offs), 4)
    for o in reversed(offs):
        b.PrependUOffsetTRelative(o)
    return b.EndVector()


def make_buffer(b, data: bytes | None):
    data_off = vec_u8(b, data) if data is not None else 0
    b.StartObject(1)
    if data_off:
        b.PrependUOffsetTRelativeSlot(0, data_off, 0)
    return b.EndObject()


def make_qparams(b, scale, zp=0):
    sc = vec_f32(b, [scale])
    z = vec_i64(b, [zp])
    b.StartObject(5)
    b.PrependUOffsetTRelativeSlot(2, sc, 0)  # VT_SCALE
    b.PrependUOffsetTRelativeSlot(3, z, 0)   # VT_ZERO_POINT
    return b.EndObject()


def make_tensor(b, shape, typ, buf_idx, name, qoff=0):
    n = b.CreateString(name)
    sh = vec_i32(b, shape)
    b.StartObject(5)
    b.PrependUOffsetTRelativeSlot(0, sh, 0)
    b.PrependInt8Slot(1, typ, 0)
    b.PrependUint32Slot(2, buf_idx, 0)
    b.PrependUOffsetTRelativeSlot(3, n, 0)
    if qoff:
        b.PrependUOffsetTRelativeSlot(4, qoff, 0)
    return b.EndObject()


def make_opcode(b):
    b.StartObject(4)
    b.PrependInt8Slot(0, BUILTIN_FC, 0)
    b.PrependInt32Slot(2, 1, 1)
    b.PrependInt32Slot(3, BUILTIN_FC, 0)
    return b.EndObject()


def make_fc_opts(b):
    b.StartObject(5)
    return b.EndObject()


def make_operator(b, inputs, outputs, opts):
    inn = vec_i32(b, inputs)
    out = vec_i32(b, outputs)
    b.StartObject(5)
    b.PrependUint32Slot(0, 0, 0)
    b.PrependUOffsetTRelativeSlot(1, inn, 0)
    b.PrependUOffsetTRelativeSlot(2, out, 0)
    b.PrependUint8Slot(3, BUILTINOPTS_FC, 0)
    b.PrependUOffsetTRelativeSlot(4, opts, 0)
    return b.EndObject()


def make_subgraph(b, tensors, inputs, outputs, ops, name):
    nm = b.CreateString(name)
    tv = vec_off(b, tensors)
    inn = vec_i32(b, inputs)
    out = vec_i32(b, outputs)
    ov = vec_off(b, ops)
    b.StartObject(5)
    b.PrependUOffsetTRelativeSlot(0, tv, 0)
    b.PrependUOffsetTRelativeSlot(1, inn, 0)
    b.PrependUOffsetTRelativeSlot(2, out, 0)
    b.PrependUOffsetTRelativeSlot(3, ov, 0)
    b.PrependUOffsetTRelativeSlot(4, nm, 0)
    return b.EndObject()


def make_model(b, version, opcodes, subgraphs, desc, buffers):
    d = b.CreateString(desc)
    oc = vec_off(b, opcodes)
    sg = vec_off(b, subgraphs)
    bf = vec_off(b, buffers)
    b.StartObject(5)
    b.PrependUint32Slot(0, version, 0)
    b.PrependUOffsetTRelativeSlot(1, oc, 0)
    b.PrependUOffsetTRelativeSlot(2, sg, 0)
    b.PrependUOffsetTRelativeSlot(3, d, 0)
    b.PrependUOffsetTRelativeSlot(4, bf, 0)
    return b.EndObject()


def emit_float():
    b = flatbuffers.Builder(1024)
    b0 = make_buffer(b, None)
    b1 = make_buffer(b, struct.pack("<9f", *W9))
    b2 = make_buffer(b, struct.pack("<f", 0.0))
    b3 = make_buffer(b, None)
    t_in = make_tensor(b, [1, 9], TENSORTYPE_F32, 0, "in")
    t_w = make_tensor(b, [1, 9], TENSORTYPE_F32, 1, "w")
    t_bias = make_tensor(b, [1], TENSORTYPE_F32, 2, "b")
    t_out = make_tensor(b, [1, 1], TENSORTYPE_F32, 3, "out")
    opts = make_fc_opts(b)
    op = make_operator(b, [0, 1, 2], [3], opts)
    sg = make_subgraph(b, [t_in, t_w, t_bias, t_out], [0], [3], [op], "m")
    oc = make_opcode(b)
    model = make_model(b, 3, [oc], [sg], "fc9f", [b0, b1, b2, b3])
    b.Finish(model, file_identifier=b"TFL3")
    return bytes(b.Output())


def emit_s8():
    w = []
    for x in W9:
        v = int(round(x * 20.0))
        v = max(-128, min(127, v))
        w.append(v)
    b = flatbuffers.Builder(1024)
    b0 = make_buffer(b, None)
    b1 = make_buffer(b, bytes(v & 0xFF for v in w))
    b2 = make_buffer(b, struct.pack("<i", 0))
    b3 = make_buffer(b, None)
    xs, ws, os_ = 0.05, 0.05, 0.25
    q_in = make_qparams(b, xs, 0)
    q_w = make_qparams(b, ws, 0)
    q_b = make_qparams(b, xs * ws, 0)
    q_o = make_qparams(b, os_, 0)
    t_in = make_tensor(b, [1, 9], TENSORTYPE_I8, 0, "in", q_in)
    t_w = make_tensor(b, [1, 9], TENSORTYPE_I8, 1, "w", q_w)
    t_bias = make_tensor(b, [1], TENSORTYPE_I32, 2, "b", q_b)
    t_out = make_tensor(b, [1, 1], TENSORTYPE_I8, 3, "out", q_o)
    opts = make_fc_opts(b)
    op = make_operator(b, [0, 1, 2], [3], opts)
    sg = make_subgraph(b, [t_in, t_w, t_bias, t_out], [0], [3], [op], "m")
    oc = make_opcode(b)
    model = make_model(b, 3, [oc], [sg], "fc9s8", [b0, b1, b2, b3])
    b.Finish(model, file_identifier=b"TFL3")
    return bytes(b.Output())


def write_c(path, sym, data: bytes):
    cpp = os.path.join(path, f"{sym}.cpp")
    hdr = os.path.join(path, f"{sym}.h")
    with open(cpp, "w") as f:
        f.write(f'#include "{sym}.h"\n')
        f.write(f"alignas(16) const unsigned char {sym}[] = {{\n")
        for i, byte in enumerate(data):
            if i % 12 == 0:
                f.write("  ")
            f.write(f"0x{byte:02x},")
            f.write("\n" if (i % 12 == 11 or i + 1 == len(data)) else " ")
        f.write(f"}};\nconst int {sym}_len = {len(data)};\n")
    with open(hdr, "w") as f:
        f.write("#pragma once\n")
        f.write(f"extern const unsigned char {sym}[];\n")
        f.write(f"extern const int {sym}_len;\n")
    print(f"{sym}: {len(data)} bytes  ident={data[4:8]!r}")


def main():
    out = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "firmware", "ssos_kernel")
    )
    write_c(out, "g_fc9f", emit_float())
    write_c(out, "g_fc9s8", emit_s8())


if __name__ == "__main__":
    main()
