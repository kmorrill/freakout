#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <libusb.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#ifdef FREAK_USB_FISHHOOK
#include "fishhook.h"
#endif

/*
 * Passive MiniFreak V USB capture shim.
 *
 * Arturia's application resolves libusb entry points dynamically.  This
 * library is loaded in place of liblibusb.dylib, re-exports the real libusb,
 * and overrides only the synchronous control/bulk transfer functions so their
 * arguments and completed payloads can be recorded.  It never creates a USB
 * request of its own.
 */

static pthread_mutex_t log_mutex = PTHREAD_MUTEX_INITIALIZER;
static void *real_handle;
#ifdef FREAK_USB_FISHHOOK
static void *captured_bulk_transfer;
static void *captured_control_transfer;
#endif

static void *resolve_real(const char *symbol) {
#ifdef FREAK_USB_FISHHOOK
    if (strcmp(symbol, "libusb_bulk_transfer") == 0 &&
        captured_bulk_transfer != NULL) {
        return captured_bulk_transfer;
    }
    if (strcmp(symbol, "libusb_control_transfer") == 0 &&
        captured_control_transfer != NULL) {
        return captured_control_transfer;
    }
#endif
    void *next = dlsym(RTLD_NEXT, symbol);
    if (next != NULL) {
        return next;
    }
    if (real_handle == NULL) {
        const char *path = getenv("FREAK_USB_REAL_LIBUSB");
        if (path == NULL || path[0] == '\0') {
            path = "/Library/Arturia/Shared/liblibusb.dylib";
        }
        real_handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
        if (real_handle == NULL) {
            return NULL;
        }
    }
    return dlsym(real_handle, symbol);
}

static size_t capture_limit(void) {
    const char *text = getenv("FREAK_USB_CAPTURE_MAX_BYTES");
    if (text == NULL || text[0] == '\0') {
        return 1024U * 1024U;
    }
    char *end = NULL;
    unsigned long long value = strtoull(text, &end, 10);
    if (end == text || *end != '\0') {
        return 1024U * 1024U;
    }
    return (size_t)value;
}

static void log_transfer(
    const char *kind,
    uint8_t endpoint,
    uint8_t request_type,
    uint8_t request,
    uint16_t value,
    uint16_t index,
    unsigned int timeout,
    int result,
    int requested,
    int transferred,
    const unsigned char *data,
    size_t data_length
) {
    const char *path = getenv("FREAK_USB_CAPTURE_FILE");
    if (path == NULL || path[0] == '\0') {
        return;
    }
    const char *keepalives = getenv("FREAK_USB_CAPTURE_KEEPALIVES");
    if (data_length == 5U && data != NULL && data[0] == 0x12 &&
        (keepalives == NULL || strcmp(keepalives, "1") != 0)) {
        return;
    }

    size_t shown = data_length;
    size_t limit = capture_limit();
    if (shown > limit) {
        shown = limit;
    }

    /* Two hex characters plus a separator per byte, with ample header room. */
    size_t capacity = 512U + shown * 3U;
    char *line = malloc(capacity);
    if (line == NULL) {
        return;
    }

    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    int used = snprintf(
        line,
        capacity,
        "%lld.%09ld kind=%s endpoint=0x%02x request_type=0x%02x request=0x%02x "
        "value=0x%04x index=0x%04x timeout_ms=%u result=%d requested=%d "
        "transferred=%d captured=%zu data=",
        (long long)now.tv_sec,
        now.tv_nsec,
        kind,
        endpoint,
        request_type,
        request,
        value,
        index,
        timeout,
        result,
        requested,
        transferred,
        shown
    );
    if (used < 0) {
        free(line);
        return;
    }

    size_t offset = (size_t)used;
    for (size_t i = 0; i < shown && offset + 3U < capacity; ++i) {
        int count = snprintf(line + offset, capacity - offset, "%02x", data[i]);
        if (count != 2) {
            break;
        }
        offset += 2U;
    }
    if (shown < data_length && offset + 12U < capacity) {
        memcpy(line + offset, "...truncated", 12U);
        offset += 12U;
    }
    if (offset + 1U < capacity) {
        line[offset++] = '\n';
    }

    pthread_mutex_lock(&log_mutex);
    int fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (fd >= 0) {
        ssize_t ignored = write(fd, line, offset);
        (void)ignored;
        close(fd);
    }
    pthread_mutex_unlock(&log_mutex);
    free(line);
}

#if defined(FREAK_USB_INTERPOSE) || defined(FREAK_USB_FISHHOOK)
#define BULK_WRAPPER_NAME freak_libusb_bulk_transfer
#define CONTROL_WRAPPER_NAME freak_libusb_control_transfer
#else
#define BULK_WRAPPER_NAME libusb_bulk_transfer
#define CONTROL_WRAPPER_NAME libusb_control_transfer
#endif

int BULK_WRAPPER_NAME(
    libusb_device_handle *dev_handle,
    unsigned char endpoint,
    unsigned char *data,
    int length,
    int *actual_length,
    unsigned int timeout
) {
    typedef int (*function_type)(
        libusb_device_handle *, unsigned char, unsigned char *, int, int *,
        unsigned int
    );
    function_type real_function = (function_type)resolve_real("libusb_bulk_transfer");
    if (real_function == NULL) {
        return LIBUSB_ERROR_OTHER;
    }

    int result = real_function(
        dev_handle, endpoint, data, length, actual_length, timeout
    );
    int transferred = actual_length == NULL ? 0 : *actual_length;
    int available = result == LIBUSB_SUCCESS ? transferred : 0;
    if (available < 0) {
        available = 0;
    }
    log_transfer(
        (endpoint & LIBUSB_ENDPOINT_IN) ? "bulk-in" : "bulk-out",
        endpoint, 0, 0, 0, 0, timeout, result, length, transferred, data,
        (size_t)available
    );
    return result;
}

int CONTROL_WRAPPER_NAME(
    libusb_device_handle *dev_handle,
    uint8_t request_type,
    uint8_t request,
    uint16_t value,
    uint16_t index,
    unsigned char *data,
    uint16_t length,
    unsigned int timeout
) {
    typedef int (*function_type)(
        libusb_device_handle *, uint8_t, uint8_t, uint16_t, uint16_t,
        unsigned char *, uint16_t, unsigned int
    );
    function_type real_function =
        (function_type)resolve_real("libusb_control_transfer");
    if (real_function == NULL) {
        return LIBUSB_ERROR_OTHER;
    }

    int result = real_function(
        dev_handle, request_type, request, value, index, data, length, timeout
    );
    size_t available = result > 0 ? (size_t)result : 0U;
    log_transfer(
        (request_type & LIBUSB_ENDPOINT_IN) ? "control-in" : "control-out",
        0, request_type, request, value, index, timeout, result, (int)length,
        result, data, available
    );
    return result;
}

#ifdef FREAK_USB_FISHHOOK
static void *(*real_dlsym_function)(void *, const char *);

static void *freak_dlsym(void *handle, const char *symbol) {
    void *resolved = real_dlsym_function(handle, symbol);
    if (resolved == NULL || symbol == NULL) {
        return resolved;
    }
    if (strcmp(symbol, "libusb_bulk_transfer") == 0) {
        captured_bulk_transfer = resolved;
        return (void *)(uintptr_t)&freak_libusb_bulk_transfer;
    }
    if (strcmp(symbol, "libusb_control_transfer") == 0) {
        captured_control_transfer = resolved;
        return (void *)(uintptr_t)&freak_libusb_control_transfer;
    }
    return resolved;
}

__attribute__((constructor)) static void install_dlsym_capture(void) {
    struct rebinding binding = {
        "dlsym", (void *)(uintptr_t)&freak_dlsym,
        (void **)&real_dlsym_function
    };
    rebind_symbols(&binding, 1U);
}
#endif

#ifdef FREAK_USB_INTERPOSE
extern int libusb_bulk_transfer(
    libusb_device_handle *, unsigned char, unsigned char *, int, int *,
    unsigned int
);
extern int libusb_control_transfer(
    libusb_device_handle *, uint8_t, uint8_t, uint16_t, uint16_t,
    unsigned char *, uint16_t, unsigned int
);

#define DYLD_INTERPOSE(replacement, replacee)                              \
    __attribute__((used)) static struct {                                  \
        const void *replacement;                                           \
        const void *replacee;                                              \
    } interpose_##replacee __attribute__((section("__DATA,__interpose"))) = { \
        (const void *)(uintptr_t)&replacement,                             \
        (const void *)(uintptr_t)&replacee                                 \
    }

DYLD_INTERPOSE(freak_libusb_bulk_transfer, libusb_bulk_transfer);
DYLD_INTERPOSE(freak_libusb_control_transfer, libusb_control_transfer);
#endif
