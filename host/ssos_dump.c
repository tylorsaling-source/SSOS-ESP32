/* Pull ID+DUMP from the live controller over Termux USB. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <libusb-1.0/libusb.h>

static void set_line(libusb_device_handle *h, int dtr, int rts) {
    uint16_t val = (dtr ? 1 : 0) | ((rts ? 1 : 0) << 1);
    libusb_control_transfer(h, 0x21, 0x22, val, 0, NULL, 0, 500);
}

static void listen(libusb_device_handle *h, int ms, FILE *out) {
    unsigned char buf[256];
    int slices = ms / 40;
    if (slices < 1) slices = 1;
    for (int i = 0; i < slices; ++i) {
        int xfer = 0;
        if (libusb_bulk_transfer(h, 0x81, buf, sizeof(buf), &xfer, 40) == 0 && xfer > 0)
            fwrite(buf, 1, xfer, out);
    }
    fflush(out);
}

static int send(libusb_device_handle *h, const char *s) {
    int xfer = 0;
    return libusb_bulk_transfer(h, 0x01, (unsigned char *)s, (int)strlen(s), &xfer, 1500) == 0;
}

int main(int argc, char **argv) {
    const char *fdstr = getenv("TERMUX_USB_FD");
    int rawfd = fdstr ? atoi(fdstr) : -1;
    const char *outpath = "/tmp/ssos.dump";
    for (int i = 1; i < argc; ++i) {
        char *end = NULL;
        long v = strtol(argv[i], &end, 10);
        if (end && *end == 0 && rawfd < 0) rawfd = (int)v;
        else if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) outpath = argv[++i];
    }
    if (rawfd < 0) return 2;
    FILE *out = fopen(outpath, "w");
    if (!out) return 5;
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
    listen(h, 400, out);
    send(h, "ID\n");
    listen(h, 700, out);
    send(h, "DUMP\n");
    listen(h, 2000, out);
    set_line(h, 0, 0);
    fclose(out);
    return 0;
}
