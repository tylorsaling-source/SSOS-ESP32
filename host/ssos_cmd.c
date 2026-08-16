/* Send one line to SSOS over USB. DTR=0 RTS=0 — do not assert BOOT. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <libusb-1.0/libusb.h>

static void set_line(libusb_device_handle *h, int dtr, int rts) {
    uint16_t val = (dtr ? 1 : 0) | ((rts ? 1 : 0) << 1);
    libusb_control_transfer(h, 0x21, 0x22, val, 0, NULL, 0, 500);
}

int main(int argc, char **argv) {
    const char *fdstr = getenv("TERMUX_USB_FD");
    int rawfd = fdstr ? atoi(fdstr) : -1;
    const char *cmd = "BENCH\n";
    for (int i = 1; i < argc; ++i) {
        char *end = NULL;
        long v = strtol(argv[i], &end, 10);
        if (end && *end == 0 && rawfd < 0) rawfd = (int)v;
        else if (strcmp(argv[i], "-c") == 0 && i + 1 < argc) cmd = argv[++i];
    }
    if (rawfd < 0) return 2;
    FILE *out = fopen("/tmp/ssos_cmd.out", "w");
    if (!out) out = stdout;
    libusb_context *ctx = NULL;
    struct libusb_init_option opts[1] = {{.option = LIBUSB_OPTION_NO_DEVICE_DISCOVERY}};
    if (libusb_init_context(&ctx, opts, 1)) return 3;
    libusb_device_handle *h = NULL;
    if (libusb_wrap_sys_device(ctx, (intptr_t)rawfd, &h)) return 4;
    libusb_set_auto_detach_kernel_driver(h, 1);
    libusb_claim_interface(h, 0);
    libusb_claim_interface(h, 1);
    unsigned char coding[7] = {0x00, 0xc2, 0x01, 0x00, 0, 0, 8};
    libusb_control_transfer(h, 0x21, 0x20, 0, 0, coding, 7, 500);
    set_line(h, 0, 0);
    char line[128];
    if (!strchr(cmd, '\n')) {
        snprintf(line, sizeof(line), "%s\n", cmd);
        cmd = line;
    }
    usleep(200000);
    unsigned char buf[256];
    for (int i = 0; i < 8; ++i) {
        int xfer = 0;
        libusb_bulk_transfer(h, 0x81, buf, sizeof(buf), &xfer, 40);
        if (xfer > 0) { fwrite(buf, 1, xfer, out); fflush(out); }
    }
    int xfer = 0;
    libusb_bulk_transfer(h, 0x01, (unsigned char *)cmd, (int)strlen(cmd), &xfer, 1500);
    for (int i = 0; i < 200; ++i) {
        int n = 0;
        if (libusb_bulk_transfer(h, 0x81, buf, sizeof(buf), &n, 40) == 0 && n > 0) {
            fwrite(buf, 1, n, out);
            fflush(out);
        }
    }
    set_line(h, 0, 0);
    if (out != stdout) fclose(out);
    return 0;
}
