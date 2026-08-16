/* LEGACY RESEARCH PROTOTYPE — NOT A CURRENT ssos.packet.v1 CLIENT.
 * PUT/MOVE/QUERY/NEIGHBORS/ROUTE/SEND are not implemented by current firmware.
 * Excluded from the default Termux build; see host/README.md.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <ctype.h>
#include <libusb-1.0/libusb.h>

#define EP_IN  0x81
#define EP_OUT 0x01

static void set_line(libusb_device_handle *h, int dtr, int rts) {
    uint16_t val = (dtr ? 1 : 0) | (rts ? 2 : 0);
    libusb_control_transfer(h, 0x21, 0x22, val, 0, NULL, 0, 500);
}

static void set_coding(libusb_device_handle *h) {
    unsigned char buf[7] = {0x00, 0xc2, 0x01, 0x00, 0, 0, 8};
    libusb_control_transfer(h, 0x21, 0x20, 0, 0, buf, 7, 500);
}

static int drain(libusb_device_handle *h, int ms) {
    unsigned char buf[256];
    int xfer, got = 0;
    int slices = ms / 50;
    if (slices < 1) slices = 1;
    for (int i = 0; i < slices; ++i) {
        int r = libusb_bulk_transfer(h, EP_IN, buf, sizeof(buf), &xfer, 50);
        if (r == 0 && xfer > 0) {
            fwrite(buf, 1, xfer, stdout);
            fflush(stdout);
            got += xfer;
        }
    }
    return got;
}

static int send_line(libusb_device_handle *h, const char *line) {
    char buf[200];
    int n = snprintf(buf, sizeof(buf), "%s\n", line);
    if (n <= 0 || n >= (int)sizeof(buf)) return -1;
    int xfer = 0;
    int r = libusb_bulk_transfer(h, EP_OUT, (unsigned char *)buf, n, &xfer, 500);
    return r;
}

static void usage(void) {
    fprintf(stderr,
            "ssos — USB console for the SSOS-S3 kernel\n"
            "  ssos                 interactive\n"
            "  ssos ID|DUMP|STATS|HELP\n"
            "  ssos GET x y z\n"
            "  ssos PUT x y z ROLE payload...\n"
            "  ssos DEL x y z\n"
            "  ssos MOVE x1 y1 z1 x2 y2 z2\n"
            "  ssos QUERY ROLE\n"
            "  ssos NEIGHBORS x y z\n"
            "  ssos ROUTE x1 y1 z1 x2 y2 z2\n"
            "  ssos SEND x y z usb|wifi|ble\n"
            "  ssos SAVE|LOAD|CLEAR\n");
}

int main(int argc, char **argv) {
    int rawfd = -1;
    int cmdc = 0;
    char *cmdv[32];

    for (int i = 1; i < argc; ++i) {
        char *end = NULL;
        long v = strtol(argv[i], &end, 10);
        if (end && *end == 0 && rawfd < 0 && v >= 0 && v < 1024 && strlen(argv[i]) <= 3) {
            rawfd = (int)v;
            continue;
        }
        if (cmdc < 31) cmdv[cmdc++] = argv[i];
    }

    if (rawfd < 0) {
        fprintf(stderr, "ssos: no USB fd (run via termux-usb -e)\n");
        return 2;
    }

    libusb_context *ctx = NULL;
    struct libusb_init_option opts[1] = {{.option = LIBUSB_OPTION_NO_DEVICE_DISCOVERY}};
    if (libusb_init_context(&ctx, opts, 1)) {
        fprintf(stderr, "libusb init failed\n");
        return 3;
    }
    libusb_device_handle *h = NULL;
    if (libusb_wrap_sys_device(ctx, (intptr_t)rawfd, &h)) {
        fprintf(stderr, "wrap failed\n");
        return 4;
    }
    for (int i = 0; i < 2; ++i) {
        if (libusb_kernel_driver_active(h, i) == 1) libusb_detach_kernel_driver(h, i);
        int c = libusb_claim_interface(h, i);
        if (c) fprintf(stderr, "claim %d: %s\n", i, libusb_strerror(c));
    }
    set_coding(h);
    set_line(h, 0, 0);
    drain(h, 200);

    if (cmdc == 0) {
        fprintf(stderr, "SSOS-S3 console. Type HELP. Ctrl-D to quit.\n");
        send_line(h, "ID");
        drain(h, 400);
        char line[180];
        while (fgets(line, sizeof(line), stdin)) {
            size_t n = strlen(line);
            while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
            if (n == 0) continue;
            if (strcmp(line, "quit") == 0 || strcmp(line, "exit") == 0) break;
            send_line(h, line);
            drain(h, 600);
        }
    } else {
        char joined[180];
        joined[0] = 0;
        for (int i = 0; i < cmdc; ++i) {
            if (i) strncat(joined, " ", sizeof(joined) - strlen(joined) - 1);
            strncat(joined, cmdv[i], sizeof(joined) - strlen(joined) - 1);
        }
        send_line(h, joined);
        drain(h, 800);
    }
    return 0;
}
