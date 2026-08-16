/* Pulse USB-JTAG into the ROM bootloader, then exit. */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <libusb-1.0/libusb.h>

static void set_line(libusb_device_handle *h, int dtr, int rts) {
    uint16_t val = (dtr ? 1 : 0) | ((rts ? 1 : 0) << 1);
    libusb_control_transfer(h, 0x21, 0x22, val, 0, NULL, 0, 500);
}

int main(int argc, char **argv) {
    const char *fdstr = getenv("TERMUX_USB_FD");
    int rawfd = fdstr ? atoi(fdstr) : -1;
    for (int i = 1; i < argc && rawfd < 0; ++i) {
        char *end = NULL;
        long v = strtol(argv[i], &end, 10);
        if (end && *end == 0) rawfd = (int)v;
    }
    if (rawfd < 0) return 2;
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
    usleep(100000);
    set_line(h, 1, 0);
    usleep(100000);
    set_line(h, 0, 1);
    usleep(100000);
    set_line(h, 0, 1);
    usleep(100000);
    set_line(h, 0, 0);
    usleep(200000);
    printf("bl-reset ok\n");
    return 0;
}
