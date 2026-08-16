#define _GNU_SOURCE
#include <errno.h>
#include <libusb-1.0/libusb.h>
#include <pthread.h>
#include <pty.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define IN_EP 0x81
#define OUT_EP 0x01
#define TMO 1000

struct state {
    libusb_device_handle *usb;
    int ptym;
    volatile int stop;
};

static void set_line(libusb_device_handle *h, int dtr, int rts) {
    uint16_t val = (dtr ? 1 : 0) | ((rts ? 1 : 0) << 1);
    libusb_control_transfer(h, 0x21, 0x22, val, 0, NULL, 0, TMO);
}

static void usb_jtag_bootloader_reset(libusb_device_handle *h) {
    unsigned char coding[7] = {0x00, 0xc2, 0x01, 0x00, 0, 0, 8};
    libusb_control_transfer(h, 0x21, 0x20, 0, 0, coding, 7, TMO);
    set_line(h, 0, 0);
    usleep(100000);
    set_line(h, 1, 0);
    usleep(100000);
    set_line(h, 0, 1);
    usleep(100000);
    set_line(h, 0, 1);
    usleep(100000);
    set_line(h, 0, 0);
    usleep(150000);
}

static void *usb_to_pty(void *arg) {
    struct state *s = arg;
    unsigned char b[512];
    while (!s->stop) {
        int n = 0;
        int r = libusb_bulk_transfer(s->usb, IN_EP, b, sizeof(b), &n, TMO);
        if (r == 0 && n > 0) {
            int off = 0;
            while (off < n && !s->stop) {
                int w = write(s->ptym, b + off, n - off);
                if (w > 0) off += w;
                else if (errno != EINTR) {
                    s->stop = 1;
                    break;
                }
            }
        } else if (r != LIBUSB_ERROR_TIMEOUT && r != LIBUSB_ERROR_INTERRUPTED) {
            s->stop = 1;
        }
    }
    return NULL;
}

int main(int argc, char **argv) {
    const char *fdstr = getenv("TERMUX_USB_FD");
    int rawfd = fdstr ? atoi(fdstr) : -1;
    if (rawfd < 0) {
        for (int i = 1; i < argc; ++i) {
            char *end = NULL;
            long v = strtol(argv[i], &end, 10);
            if (end && *end == 0) rawfd = (int)v;
        }
    }
    if (rawfd < 0) {
        fprintf(stderr, "TERMUX_USB_FD is not set\n");
        return 2;
    }

    libusb_context *ctx = NULL;
    struct libusb_init_option opts[1] = {{.option = LIBUSB_OPTION_NO_DEVICE_DISCOVERY}};
    int rc = libusb_init_context(&ctx, opts, 1);
    if (rc) {
        fprintf(stderr, "libusb_init: %s\n", libusb_strerror(rc));
        return 3;
    }

    struct state s = {0};
    rc = libusb_wrap_sys_device(ctx, (intptr_t)rawfd, &s.usb);
    if (rc) {
        fprintf(stderr, "wrap: %s\n", libusb_strerror(rc));
        return 4;
    }
    libusb_set_auto_detach_kernel_driver(s.usb, 1);
    if (libusb_claim_interface(s.usb, 0) != 0 || libusb_claim_interface(s.usb, 1) != 0) {
        fprintf(stderr, "claim failed\n");
        return 5;
    }

    int pts = -1;
    if (openpty(&s.ptym, &pts, NULL, NULL, NULL) < 0) {
        perror("openpty");
        return 7;
    }
    char *name = ttyname(pts);
    if (!name) {
        perror("ttyname");
        return 8;
    }
    printf("%s\n", name);
    fflush(stdout);

    const char *ptyfile = getenv("SSOS_PTY_FILE");
    if (!ptyfile || !*ptyfile)
        ptyfile = "/data/data/com.termux/files/home/.ssos-pty.path";
    FILE *pf = fopen(ptyfile, "w");
    if (pf) {
        fprintf(pf, "%s\n", name);
        fclose(pf);
    }

    usleep(400000);
    if (!getenv("SSOS_NO_BL_RESET"))
        usb_jtag_bootloader_reset(s.usb);

    pthread_t t;
    pthread_create(&t, NULL, usb_to_pty, &s);
    unsigned char b[512];
    while (!s.stop) {
        int n = read(s.ptym, b, sizeof(b));
        if (n > 0) {
            int sent = 0;
            while (sent < n && !s.stop) {
                int w = 0;
                rc = libusb_bulk_transfer(s.usb, OUT_EP, b + sent, n - sent, &w, TMO);
                if (rc != 0) {
                    fprintf(stderr, "USB write: %s\n", libusb_strerror(rc));
                    s.stop = 1;
                    break;
                }
                sent += w;
            }
        } else if (n < 0 && errno != EINTR) {
            s.stop = 1;
        }
    }
    s.stop = 1;
    pthread_join(t, NULL);
    close(pts);
    close(s.ptym);
    libusb_release_interface(s.usb, 1);
    libusb_release_interface(s.usb, 0);
    libusb_close(s.usb);
    libusb_exit(ctx);
    return 0;
}
