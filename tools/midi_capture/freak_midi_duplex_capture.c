// Passive CoreMIDI duplex capture for a disposable Arturia application copy.

#include <CoreFoundation/CoreFoundation.h>
#include <CoreMIDI/CoreMIDI.h>
#include <execinfo.h>
#include <mach-o/dyld.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fishhook.h"

typedef struct {
    MIDIReadProc original;
    void *original_refcon;
} InputContext;

static pthread_mutex_t log_lock = PTHREAD_MUTEX_INITIALIZER;

static FILE *capture_file(void) {
    static FILE *file;
    static int initialized;
    if (!initialized) {
        initialized = 1;
        const char *path = getenv("FREAK_MIDI_CAPTURE_FILE");
        if (path != NULL) file = fopen(path, "a");
    }
    return file;
}

static int operation_is_traced(uint8_t operation) {
    const char *filter = getenv("FREAK_MIDI_CAPTURE_BACKTRACE_OPS");
    if (filter == NULL || *filter == '\0') return 0;
    while (*filter != '\0') {
        char *end = NULL;
        unsigned long value = strtoul(filter, &end, 0);
        if (end == filter) {
            ++filter;
            continue;
        }
        if (value <= 0x7f && (uint8_t)value == operation) return 1;
        filter = end;
        while (*filter == ',' || *filter == ' ' || *filter == '\t') ++filter;
    }
    return 0;
}

static int microfreak_operation(const MIDIPacket *packet, uint8_t *operation) {
    if (packet->length < 10) return 0;
    const Byte *data = packet->data;
    if (data[0] != 0xf0 || data[1] != 0x00 || data[2] != 0x20 ||
        data[3] != 0x6b || data[4] != 0x07 || data[5] != 0x01) return 0;
    *operation = data[8];
    return 1;
}

static void log_backtrace(FILE *file, const MIDIPacket *packet) {
    uint8_t operation = 0;
    if (!microfreak_operation(packet, &operation) ||
        !operation_is_traced(operation)) return;
    void *frames[32];
    int count = backtrace(frames, (int)(sizeof(frames) / sizeof(frames[0])));
    fprintf(file, "trace timestamp=%llu op=0x%02x frames=",
            (unsigned long long)packet->timeStamp, operation);
    for (int index = 0; index < count; ++index) {
        if (index != 0) fputc(',', file);
        fprintf(file, "%p", frames[index]);
    }
    fputc('\n', file);
}

static void log_packets(const char *direction, const MIDIPacketList *list) {
    FILE *file = capture_file();
    if (file == NULL || list == NULL) return;
    pthread_mutex_lock(&log_lock);
    const MIDIPacket *packet = &list->packet[0];
    for (UInt32 index = 0; index < list->numPackets; ++index) {
        fprintf(file, "%s timestamp=%llu data=", direction,
                (unsigned long long)packet->timeStamp);
        for (UInt16 byte = 0; byte < packet->length; ++byte)
            fprintf(file, "%02x", packet->data[byte]);
        fputc('\n', file);
        if (strcmp(direction, "out") == 0) log_backtrace(file, packet);
        packet = MIDIPacketNext(packet);
    }
    fflush(file);
    pthread_mutex_unlock(&log_lock);
}

static void wrapped_read_proc(const MIDIPacketList *list,
                              void *read_proc_refcon,
                              void *src_conn_refcon) {
    InputContext *context = (InputContext *)read_proc_refcon;
    log_packets("in", list);
    context->original(list, context->original_refcon, src_conn_refcon);
}

static OSStatus (*original_MIDIInputPortCreate)(MIDIClientRef, CFStringRef,
                                                MIDIReadProc, void *,
                                                MIDIPortRef *);
static OSStatus (*original_MIDISend)(MIDIPortRef, MIDIEndpointRef,
                                     const MIDIPacketList *);

static OSStatus capture_MIDIInputPortCreate(MIDIClientRef client,
                                            CFStringRef port_name,
                                            MIDIReadProc read_proc,
                                            void *refcon,
                                            MIDIPortRef *out_port) {
    InputContext *context = calloc(1, sizeof(*context));
    if (context == NULL) return kMIDIUnknownEndpoint;
    context->original = read_proc;
    context->original_refcon = refcon;
    OSStatus status = original_MIDIInputPortCreate(
        client, port_name, wrapped_read_proc, context, out_port
    );
    if (status != noErr) free(context);
    return status;
}

static OSStatus capture_MIDISend(MIDIPortRef port,
                                 MIDIEndpointRef destination,
                                 const MIDIPacketList *list) {
    log_packets("out", list);
    return original_MIDISend(port, destination, list);
}

__attribute__((constructor)) static void capture_loaded(void) {
    struct rebinding bindings[] = {
        {"MIDIInputPortCreate", capture_MIDIInputPortCreate,
         (void **)&original_MIDIInputPortCreate},
        {"MIDISend", capture_MIDISend, (void **)&original_MIDISend},
    };
    rebind_symbols(bindings, 2);
    FILE *file = capture_file();
    if (file != NULL) {
        fprintf(file, "capture-loaded duplex-v2 image-base=%p\n",
                (const void *)_dyld_get_image_header(0));
        fflush(file);
    }
}
