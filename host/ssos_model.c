/* Tiny linear model that uses the SSOS packet controller as memory.
 *
 * Host trains a 9-D / 4-class softmax. Weights, examples, and receipts
 * are PKT'd onto the chip. Inference reloads W from GET, never from
 * the host copy. DUMP is the replaceable-controller tape.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <libusb-1.0/libusb.h>

#define DIMS 4
#define FEAT 9
#define SCALE 100.0f
#define EX_MAX 12
#define Q_MAX 8

struct Sample {
    const char *text;
    int label;
};

static const char *class_name[DIMS] = {"boot", "document", "payload", "note"};

/* 9 feature groups — bag-of-stems projected onto the 9 axes. */
static const char *stems[FEAT][8] = {
    {"boot", "efi", "rom", "startup", "loader", 0},
    {"kernel", "firmware", "image", "slot", 0},
    {"readme", "spec", "architecture", "charter", "document", 0},
    {"report", "text", "notes", "contract", 0},
    {"sensor", "payload", "bytes", "blob", "body", 0},
    {"opaque", "swap", "model", 0},
    {"journal", "note", "memo", "reminder", "card", 0},
    {"write", "send", "read", 0},
    {"short", "nine", "all", 0},
};

static const struct Sample train_set[] = {
    {"efi kernel boot loader", 0},
    {"boot image firmware slot", 0},
    {"startup boot rom", 0},
    {"readme architecture spec", 1},
    {"document notes report", 1},
    {"charter contract text", 1},
    {"sensor payload bytes", 2},
    {"swap-test body blob", 2},
    {"opaque model payload", 2},
    {"journal note memo", 3},
    {"all-nine note card", 3},
    {"short note reminder", 3},
};
static const int train_n = (int)(sizeof(train_set) / sizeof(train_set[0]));

static const struct Sample query_set[] = {
    {"boot the kernel image", 0},
    {"read the spec document", 1},
    {"send payload bytes", 2},
    {"write a journal note", 3},
};
static const int query_n = (int)(sizeof(query_set) / sizeof(query_set[0]));

static void lower_copy(const char *s, char *out, int max) {
    int i = 0;
    for (; s[i] && i + 1 < max; ++i) {
        char c = s[i];
        if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a');
        out[i] = c;
    }
    out[i] = 0;
}

static int has_stem(const char *hay, const char *stem) {
    const char *p = hay;
    size_t n = strlen(stem);
    while (*p) {
        if (strncmp(p, stem, n) == 0) {
            char after = p[n];
            char before = (p == hay) ? ' ' : p[-1];
            int b_ok = (before < 'a' || before > 'z');
            int a_ok = (after < 'a' || after > 'z');
            if (b_ok && a_ok) return 1;
        }
        ++p;
    }
    return 0;
}

static void embed(const char *text, float x[FEAT]) {
    char buf[128];
    lower_copy(text, buf, sizeof(buf));
    for (int d = 0; d < FEAT; ++d) {
        x[d] = 0;
        for (int k = 0; stems[d][k]; ++k)
            if (has_stem(buf, stems[d][k])) x[d] += 1.0f;
    }
    /* tiny length axis so empty strings are not the origin */
    float nrm = 0;
    for (int d = 0; d < FEAT; ++d) nrm += x[d] * x[d];
    nrm = sqrtf(nrm);
    if (nrm < 1e-6f) {
        x[0] = 1.0f;
        return;
    }
    for (int d = 0; d < FEAT; ++d) x[d] /= nrm;
}

static void softmax(const float *z, float *p, int n) {
    float m = z[0];
    for (int i = 1; i < n; ++i) if (z[i] > m) m = z[i];
    float s = 0;
    for (int i = 0; i < n; ++i) {
        p[i] = expf(z[i] - m);
        s += p[i];
    }
    for (int i = 0; i < n; ++i) p[i] /= s;
}

static int forward(const float W[DIMS][FEAT], const float *b,
                   const float *x, float *probs) {
    float z[DIMS];
    for (int c = 0; c < DIMS; ++c) {
        z[c] = b[c];
        for (int d = 0; d < FEAT; ++d) z[c] += W[c][d] * x[d];
    }
    softmax(z, probs, DIMS);
    int best = 0;
    for (int c = 1; c < DIMS; ++c) if (probs[c] > probs[best]) best = c;
    return best;
}

static void train(float W[DIMS][FEAT], float b[DIMS]) {
    memset(W, 0, sizeof(float) * DIMS * FEAT);
    memset(b, 0, sizeof(float) * DIMS);
    const float lr = 0.35f;
    for (int epoch = 0; epoch < 250; ++epoch) {
        for (int i = 0; i < train_n; ++i) {
            float x[FEAT], p[DIMS];
            embed(train_set[i].text, x);
            forward(W, b, x, p);
            for (int c = 0; c < DIMS; ++c) {
                float g = p[c] - (c == train_set[i].label ? 1.0f : 0.0f);
                b[c] -= lr * g;
                for (int d = 0; d < FEAT; ++d) W[c][d] -= lr * g * x[d];
            }
        }
    }
}

static void quantize(const float W[DIMS][FEAT], const float b[DIMS],
                     int qW[DIMS][FEAT], int qb[DIMS]) {
    for (int c = 0; c < DIMS; ++c) {
        qb[c] = (int)lroundf(b[c] * SCALE);
        for (int d = 0; d < FEAT; ++d)
            qW[c][d] = (int)lroundf(W[c][d] * SCALE);
    }
}

static int forward_q(const int qW[DIMS][FEAT], const int *qb,
                     const float *x, float *probs) {
    float W[DIMS][FEAT], b[DIMS];
    for (int c = 0; c < DIMS; ++c) {
        b[c] = qb[c] / SCALE;
        for (int d = 0; d < FEAT; ++d) W[c][d] = qW[c][d] / SCALE;
    }
    return forward(W, b, x, probs);
}

static void set_line(libusb_device_handle *h, int dtr, int rts) {
    uint16_t val = (dtr ? 1 : 0) | ((rts ? 1 : 0) << 1);
    libusb_control_transfer(h, 0x21, 0x22, val, 0, NULL, 0, 500);
}

static int listen(libusb_device_handle *h, int ms, char *out, int outmax) {
    unsigned char buf[256];
    int n = 0;
    int slices = ms / 40;
    if (slices < 1) slices = 1;
    if (out && outmax > 0) out[0] = 0;
    for (int i = 0; i < slices; ++i) {
        int xfer = 0;
        int rc = libusb_bulk_transfer(h, 0x81, buf, sizeof(buf), &xfer, 40);
        if (rc == 0 && xfer > 0) {
            fwrite(buf, 1, xfer, stdout);
            if (out && n + xfer < outmax) {
                memcpy(out + n, buf, xfer);
                n += xfer;
                out[n] = 0;
            }
        }
    }
    fflush(stdout);
    return n;
}

static int send(libusb_device_handle *h, const char *s) {
    int xfer = 0;
    int rc = libusb_bulk_transfer(h, 0x01, (unsigned char *)s,
                                  (int)strlen(s), &xfer, 1500);
    printf("\n>>> %s rc=%d xfer=%d\n", s, rc, xfer);
    fflush(stdout);
    return rc == 0 && xfer > 0;
}

static const char *find_field(const char *s, const char *key) {
    const char *p = strstr(s, key);
    return p ? p + strlen(key) : NULL;
}

static int parse_body_ints(const char *got, int *out, int want) {
    const char *b = find_field(got, "body=");
    if (!b) return 0;
    int n = 0;
    const char *p = b;
    while (n < want && *p && *p != '\n' && *p != '\r') {
        while (*p == ' ' || *p == ',') ++p;
        if (!*p || *p == '\n' || *p == '\r') break;
        char *end = NULL;
        long v = strtol(p, &end, 10);
        if (end == p) break;
        out[n++] = (int)v;
        p = end;
    }
    return n == want;
}

static int parse_d(const char *got, int d[FEAT]) {
    /* " d=" — not the "d=" hidden inside "id=" */
    const char *p = strstr(got, " d=");
    if (!p) return 0;
    p += 3;
    int n = 0;
    while (n < FEAT && *p && *p != ' ' && *p != '\n') {
        char *end = NULL;
        long v = strtol(p, &end, 10);
        if (end == p) break;
        d[n++] = (int)v;
        p = (*end == ',') ? end + 1 : end;
    }
    return n == FEAT;
}

static void dash_copy(const char *s, char *out, int max) {
    int i = 0;
    for (; s[i] && i + 1 < max; ++i)
        out[i] = (s[i] == ' ') ? '-' : s[i];
    out[i] = 0;
}

int main(int argc, char **argv) {
    FILE *logf = fopen("/tmp/ssos_model.out", "w");
    if (logf) {
        dup2(fileno(logf), STDOUT_FILENO);
        dup2(fileno(logf), STDERR_FILENO);
    }
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    const char *fdstr = getenv("TERMUX_USB_FD");
    int rawfd = fdstr ? atoi(fdstr) : -1;
    fprintf(stderr, "ssos_model start argc=%d TERMUX_USB_FD=%s\n",
            argc, fdstr ? fdstr : "(null)");
    for (int i = 0; i < argc; ++i)
        fprintf(stderr, " argv[%d]=%s\n", i, argv[i]);
    for (int i = 1; i < argc && rawfd < 0; ++i) {
        char *end = NULL;
        long v = strtol(argv[i], &end, 10);
        if (end && *end == 0) rawfd = (int)v;
    }

    float W[DIMS][FEAT], b[DIMS];
    int qW[DIMS][FEAT], qb[DIMS];
    train(W, b);
    quantize(W, b, qW, qb);

    int train_ok = 0;
    printf("=== host train (9-D linear softmax, %d params) ===\n",
           DIMS * FEAT + DIMS);
    for (int i = 0; i < train_n; ++i) {
        float x[FEAT], p[DIMS];
        embed(train_set[i].text, x);
        int pred = forward_q(qW, qb, x, p);
        int ok = pred == train_set[i].label;
        train_ok += ok;
        printf("train[%d] pred=%s gold=%s p=%.2f %s  x=",
               i, class_name[pred], class_name[train_set[i].label],
               p[pred], ok ? "OK" : "MISS");
        for (int d = 0; d < FEAT; ++d)
            printf("%s%.2f", d ? "," : "", x[d]);
        printf("\n");
    }
    printf("train acc %d/%d\n", train_ok, train_n);
    if (rawfd < 0) {
        fprintf(stderr, "ssos_model: no USB fd\n");
        return 2;
    }

    libusb_context *ctx = NULL;
    struct libusb_init_option opts[1] = {{.option = LIBUSB_OPTION_NO_DEVICE_DISCOVERY}};
    if (libusb_init_context(&ctx, opts, 1)) return 3;
    libusb_device_handle *h = NULL;
    if (libusb_wrap_sys_device(ctx, (intptr_t)rawfd, &h)) return 4;
    libusb_set_auto_detach_kernel_driver(h, 1);
    printf("claim0 %s\n", libusb_strerror(libusb_claim_interface(h, 0)));
    printf("claim1 %s\n", libusb_strerror(libusb_claim_interface(h, 1)));
    unsigned char coding[7] = {0x00, 0xc2, 0x01, 0x00, 0, 0, 8};
    libusb_control_transfer(h, 0x21, 0x20, 0, 0, coding, 7, 500);
    /* Never assert DTR on this S3: DTR is GPIO0/BOOT. Holding it loops. */
    set_line(h, 0, 0);

    char got[8192];
    int fail = 0;
    listen(h, 600, got, sizeof(got));
    send(h, "ID\n");
    listen(h, 700, got, sizeof(got));
    if (!strstr(got, "ssos.packet.v1")) {
        printf("FAIL no controller ID\n");
        return 1;
    }

    /* free previous axis-test slots; keep seed */
    const char *old_ids[] = {
        "axis:0", "axis:1", "axis:2", "axis:3", "axis:4",
        "axis:5", "axis:6", "axis:7", "axis:8", "axis:all",
        "verify:1", 0
    };
    for (int i = 0; old_ids[i]; ++i) {
        char line[64];
        snprintf(line, sizeof(line), "DEL id=%s\n", old_ids[i]);
        send(h, line);
        listen(h, 400, got, sizeof(got));
    }

    printf("\n=== PKT quantized weights onto controller ===\n");
    for (int c = 0; c < DIMS; ++c) {
        char line[240];
        snprintf(line, sizeof(line),
                 "PKT id=model:w:%s d=80,%d,0,0,0,0,0,0,0 role=runtime body=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n",
                 class_name[c], c,
                 qW[c][0], qW[c][1], qW[c][2], qW[c][3], qW[c][4],
                 qW[c][5], qW[c][6], qW[c][7], qW[c][8], qb[c]);
        send(h, line);
        got[0] = 0;
        listen(h, 800, got, sizeof(got));
        if (!strstr(got, "OK recv") || !strstr(got, "model:w:")) {
            printf("FAIL store weight %s\n", class_name[c]);
            fail++;
        } else printf("PASS store weight %s\n", class_name[c]);
    }

    printf("\n=== PKT training examples at their 9-D coords ===\n");
    int placed[EX_MAX][FEAT];
    memset(placed, 0, sizeof(placed));
    for (int i = 0; i < train_n; ++i) {
        float x[FEAT];
        embed(train_set[i].text, x);
        int d[FEAT];
        for (int k = 0; k < FEAT; ++k) d[k] = (int)lroundf(x[k] * 10.0f);
        for (int j = 0; j < i; ++j) {
            int same = 1;
            for (int k = 0; k < FEAT; ++k)
                if (d[k] != placed[j][k]) same = 0;
            if (same) d[8] += 1;
        }
        memcpy(placed[i], d, sizeof(d));
        char dashed[80];
        dash_copy(train_set[i].text, dashed, sizeof(dashed));
        char line[240];
        snprintf(line, sizeof(line),
                 "PKT id=model:ex:%d d=%d,%d,%d,%d,%d,%d,%d,%d,%d role=document body=%s:%s\n",
                 i, d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8],
                 class_name[train_set[i].label], dashed);
        send(h, line);
        got[0] = 0;
        listen(h, 800, got, sizeof(got));
        if (!strstr(got, "OK recv")) {
            printf("FAIL store example %d\n", i);
            fail++;
        } else printf("PASS store example %d at d=%d,%d,%d,%d,%d,%d,%d,%d,%d\n",
                      i, d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8]);
    }

    /* wipe host weights — inference must come from the chip */
    int chipW[DIMS][FEAT], chipb[DIMS];
    memset(chipW, 0, sizeof(chipW));
    memset(chipb, 0, sizeof(chipb));
    memset(qW, 0, sizeof(qW));
    memset(qb, 0, sizeof(qb));

    printf("\n=== GET weights back (host W zeroed) ===\n");
    for (int c = 0; c < DIMS; ++c) {
        char line[64];
        snprintf(line, sizeof(line), "GET id=model:w:%s\n", class_name[c]);
        send(h, line);
        got[0] = 0;
        listen(h, 800, got, sizeof(got));
        int vals[10];
        if (!strstr(got, "OK PKT") || !parse_body_ints(got, vals, 10)) {
            printf("FAIL GET weight %s\n", class_name[c]);
            fail++;
            continue;
        }
        for (int d = 0; d < FEAT; ++d) chipW[c][d] = vals[d];
        chipb[c] = vals[9];
        printf("PASS GET weight %s body loaded\n", class_name[c]);
    }

    printf("\n=== infer held-out queries using ONLY chip weights ===\n");
    int infer_ok = 0;
    for (int i = 0; i < query_n; ++i) {
        float x[FEAT], p[DIMS];
        embed(query_set[i].text, x);
        int pred = forward_q(chipW, chipb, x, p);
        int ok = pred == query_set[i].label;
        infer_ok += ok;
        printf("query \"%s\" -> %s (p=%.2f) gold=%s %s  x=",
               query_set[i].text, class_name[pred], p[pred],
               class_name[query_set[i].label], ok ? "PASS" : "FAIL");
        for (int d = 0; d < FEAT; ++d)
            printf("%s%.2f", d ? "," : "", x[d]);
        printf("\n");
        if (!ok) fail++;

        /* spatial recall: nearest stored example by 9-D L2 on DUMP coords later;
           receipt goes on the controller now */
        int qd[FEAT];
        for (int d = 0; d < FEAT; ++d) qd[d] = (int)lroundf(x[d] * 10.0f);
        char dashed[80];
        dash_copy(query_set[i].text, dashed, sizeof(dashed));
        char line[240];
        snprintf(line, sizeof(line),
                 "PKT id=model:rx:%d d=90,%d,%d,0,0,0,0,0,0 role=note body=%s:%s:p%d\n",
                 i, i, pred, class_name[pred], dashed, (int)lroundf(p[pred] * 100));
        send(h, line);
        got[0] = 0;
        listen(h, 800, got, sizeof(got));
        if (!strstr(got, "OK recv")) {
            printf("FAIL receipt %d\n", i);
            fail++;
        } else printf("PASS receipt %d stored\n", i);
        (void)qd;
    }

    printf("\n=== DUMP tape (replacement controller feed) ===\n");
    send(h, "DUMP\n");
    got[0] = 0;
    listen(h, 2000, got, sizeof(got));

    for (int c = 0; c < DIMS; ++c) {
        char id[32];
        snprintf(id, sizeof(id), "id=model:w:%s ", class_name[c]);
        if (!strstr(got, id)) {
            printf("FAIL DUMP missing %s\n", id);
            fail++;
        } else printf("PASS DUMP has %s\n", id);
    }
    for (int i = 0; i < train_n; ++i) {
        char id[24];
        snprintf(id, sizeof(id), "id=model:ex:%d ", i);
        if (!strstr(got, id)) {
            printf("FAIL DUMP missing %s\n", id);
            fail++;
        } else printf("PASS DUMP has %s\n", id);
    }
    for (int i = 0; i < query_n; ++i) {
        char id[24];
        snprintf(id, sizeof(id), "id=model:rx:%d ", i);
        if (!strstr(got, id)) {
            printf("FAIL DUMP missing %s\n", id);
            fail++;
        } else printf("PASS DUMP has %s\n", id);
    }

    /* nearest example from DUMP coords vs query embedding */
    printf("\n=== nearest example from DUMP 9-D coords ===\n");
    for (int i = 0; i < query_n; ++i) {
        float x[FEAT];
        embed(query_set[i].text, x);
        int qd[FEAT];
        for (int d = 0; d < FEAT; ++d) qd[d] = (int)lroundf(x[d] * 10.0f);
        int best = -1;
        int best_d2 = 1 << 30;
        int best_d[FEAT] = {0};
        for (int e = 0; e < train_n; ++e) {
            char key[24];
            snprintf(key, sizeof(key), "id=model:ex:%d ", e);
            const char *at = strstr(got, key);
            if (!at) continue;
            int ed[FEAT];
            if (!parse_d(at, ed)) continue;
            int d2 = 0;
            for (int d = 0; d < FEAT; ++d) {
                int diff = ed[d] - qd[d];
                d2 += diff * diff;
            }
            if (d2 < best_d2) {
                best_d2 = d2;
                best = e;
                memcpy(best_d, ed, sizeof(best_d));
            }
        }
        if (best < 0) {
            printf("FAIL no neighbor for query %d\n", i);
            fail++;
        } else {
            int same = train_set[best].label == query_set[i].label;
            printf("%s neighbor q%d -> ex:%d label=%s d2=%d coord=%d,%d,%d,%d,%d,%d,%d,%d,%d\n",
                   same ? "PASS" : "FAIL", i, best, class_name[train_set[best].label],
                   best_d2, best_d[0], best_d[1], best_d[2], best_d[3], best_d[4],
                   best_d[5], best_d[6], best_d[7], best_d[8]);
            if (!same) fail++;
        }
    }

    printf("\n=== MODEL RESULT fails=%d train=%d/%d infer=%d/%d ===\n",
           fail, train_ok, train_n, infer_ok, query_n);
    set_line(h, 0, 0);
    return fail ? 1 : 0;
}
