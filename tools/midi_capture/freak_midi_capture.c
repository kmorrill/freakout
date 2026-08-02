// Passive CoreMIDI sender capture for the disposable MiniFreak V copy.

#include <CoreMIDI/CoreMIDI.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fishhook.h"

static OSStatus (*real_MIDISend)(MIDIPortRef, MIDIEndpointRef,
                                 const MIDIPacketList *);
static OSStatus (*real_MIDISendEventList)(MIDIPortRef, MIDIEndpointRef,
                                          const MIDIEventList *);
static OSStatus (*captured_MIDISend)(MIDIPortRef, MIDIEndpointRef,
                                     const MIDIPacketList *);
static OSStatus (*captured_MIDISendEventList)(MIDIPortRef, MIDIEndpointRef,
                                              const MIDIEventList *);
static OSStatus (*real_MIDIReceived)(MIDIEndpointRef, const MIDIPacketList *);
static OSStatus (*real_MIDIReceivedEventList)(MIDIEndpointRef,
                                              const MIDIEventList *);
static OSStatus (*captured_MIDIReceived)(MIDIEndpointRef,
                                         const MIDIPacketList *);
static OSStatus (*captured_MIDIReceivedEventList)(MIDIEndpointRef,
                                                  const MIDIEventList *);
static void *(*real_dlsym_function)(void *, const char *);
typedef uintptr_t (*generic_midi_function)(
    uintptr_t, uintptr_t, uintptr_t, uintptr_t,
    uintptr_t, uintptr_t, uintptr_t, uintptr_t
);
static generic_midi_function real_SendMessageNowToPort;
static generic_midi_function real_SendDataNowToPort;
static generic_midi_function captured_SendMessageNowToPort;
static generic_midi_function captured_SendDataNowToPort;
static pthread_mutex_t log_lock = PTHREAD_MUTEX_INITIALIZER;

static FILE *open_log(void) {
    const char *path = getenv("FREAK_MIDI_CAPTURE_FILE");
    return path == NULL ? NULL : fopen(path, "a");
}

static void write_hex(FILE *file, const Byte *data, size_t size) {
    for (size_t i = 0; i < size; ++i) {
        fprintf(file, "%02x", data[i]);
    }
}

static uintptr_t capture_generic_call(
    const char *name, generic_midi_function captured,
    generic_midi_function direct, uintptr_t a0, uintptr_t a1, uintptr_t a2,
    uintptr_t a3, uintptr_t a4, uintptr_t a5, uintptr_t a6, uintptr_t a7
) {
    pthread_mutex_lock(&log_lock);
    FILE *file = open_log();
    if (file != NULL) {
        fprintf(file,
                "%s args=%016llx,%016llx,%016llx,%016llx,%016llx,%016llx,"
                "%016llx,%016llx\n",
                name,
                (unsigned long long)a0, (unsigned long long)a1,
                (unsigned long long)a2, (unsigned long long)a3,
                (unsigned long long)a4, (unsigned long long)a5,
                (unsigned long long)a6, (unsigned long long)a7);
        fclose(file);
    }
    pthread_mutex_unlock(&log_lock);
    generic_midi_function function = captured != NULL ? captured : direct;
    return function(a0, a1, a2, a3, a4, a5, a6, a7);
}

static uintptr_t capture_SendMessageNowToPort(
    uintptr_t a0, uintptr_t a1, uintptr_t a2, uintptr_t a3,
    uintptr_t a4, uintptr_t a5, uintptr_t a6, uintptr_t a7
) {
    return capture_generic_call(
        "single-message", captured_SendMessageNowToPort,
        real_SendMessageNowToPort, a0, a1, a2, a3, a4, a5, a6, a7
    );
}

static uintptr_t capture_SendDataNowToPort(
    uintptr_t a0, uintptr_t a1, uintptr_t a2, uintptr_t a3,
    uintptr_t a4, uintptr_t a5, uintptr_t a6, uintptr_t a7
) {
    return capture_generic_call(
        "single-data", captured_SendDataNowToPort, real_SendDataNowToPort,
        a0, a1, a2, a3, a4, a5, a6, a7
    );
}

static OSStatus capture_MIDISend(MIDIPortRef port, MIDIEndpointRef destination,
                                 const MIDIPacketList *packets) {
    pthread_mutex_lock(&log_lock);
    FILE *file = open_log();
    if (file != NULL) {
        const MIDIPacket *packet = &packets->packet[0];
        for (UInt32 i = 0; i < packets->numPackets; ++i) {
            fprintf(file, "midi1 destination=%u timestamp=%llu data=",
                    destination, packet->timeStamp);
            write_hex(file, packet->data, packet->length);
            fputc('\n', file);
            packet = MIDIPacketNext(packet);
        }
        fclose(file);
    }
    pthread_mutex_unlock(&log_lock);
    OSStatus (*sender)(MIDIPortRef, MIDIEndpointRef, const MIDIPacketList *) =
        captured_MIDISend != NULL ? captured_MIDISend : real_MIDISend;
    return sender(port, destination, packets);
}

static OSStatus capture_MIDISendEventList(MIDIPortRef port,
                                          MIDIEndpointRef destination,
                                          const MIDIEventList *events) {
    pthread_mutex_lock(&log_lock);
    FILE *file = open_log();
    if (file != NULL) {
        const MIDIEventPacket *packet = &events->packet[0];
        for (UInt32 i = 0; i < events->numPackets; ++i) {
            fprintf(file,
                    "ump destination=%u protocol=%u timestamp=%llu words=",
                    destination, events->protocol, packet->timeStamp);
            for (UInt32 word = 0; word < packet->wordCount; ++word) {
                fprintf(file, "%08x", packet->words[word]);
            }
            fputc('\n', file);
            packet = MIDIEventPacketNext(packet);
        }
        fclose(file);
    }
    pthread_mutex_unlock(&log_lock);
    OSStatus (*sender)(MIDIPortRef, MIDIEndpointRef, const MIDIEventList *) =
        captured_MIDISendEventList != NULL ? captured_MIDISendEventList
                                           : real_MIDISendEventList;
    return sender(port, destination, events);
}

static OSStatus capture_MIDIReceived(MIDIEndpointRef source,
                                     const MIDIPacketList *packets) {
    pthread_mutex_lock(&log_lock);
    FILE *file = open_log();
    if (file != NULL) {
        const MIDIPacket *packet = &packets->packet[0];
        for (UInt32 i = 0; i < packets->numPackets; ++i) {
            fprintf(file, "received-midi1 source=%u timestamp=%llu data=",
                    source, packet->timeStamp);
            write_hex(file, packet->data, packet->length);
            fputc('\n', file);
            packet = MIDIPacketNext(packet);
        }
        fclose(file);
    }
    pthread_mutex_unlock(&log_lock);
    OSStatus (*receiver)(MIDIEndpointRef, const MIDIPacketList *) =
        captured_MIDIReceived != NULL ? captured_MIDIReceived
                                      : real_MIDIReceived;
    return receiver(source, packets);
}

static OSStatus capture_MIDIReceivedEventList(MIDIEndpointRef source,
                                              const MIDIEventList *events) {
    pthread_mutex_lock(&log_lock);
    FILE *file = open_log();
    if (file != NULL) {
        const MIDIEventPacket *packet = &events->packet[0];
        for (UInt32 i = 0; i < events->numPackets; ++i) {
            fprintf(file,
                    "received-ump source=%u protocol=%u timestamp=%llu words=",
                    source, events->protocol, packet->timeStamp);
            for (UInt32 word = 0; word < packet->wordCount; ++word) {
                fprintf(file, "%08x", packet->words[word]);
            }
            fputc('\n', file);
            packet = MIDIEventPacketNext(packet);
        }
        fclose(file);
    }
    pthread_mutex_unlock(&log_lock);
    OSStatus (*receiver)(MIDIEndpointRef, const MIDIEventList *) =
        captured_MIDIReceivedEventList != NULL
            ? captured_MIDIReceivedEventList
            : real_MIDIReceivedEventList;
    return receiver(source, events);
}

static void *capture_dlsym(void *handle, const char *symbol) {
    void *resolved = real_dlsym_function(handle, symbol);
    if (resolved == NULL || symbol == NULL) {
        return resolved;
    }
    if (strcmp(symbol, "MIDISend") == 0) {
        captured_MIDISend = resolved;
        return (void *)(uintptr_t)&capture_MIDISend;
    }
    if (strcmp(symbol, "MIDISendEventList") == 0) {
        captured_MIDISendEventList = resolved;
        return (void *)(uintptr_t)&capture_MIDISendEventList;
    }
    if (strcmp(symbol, "MIDIReceived") == 0) {
        captured_MIDIReceived = resolved;
        return (void *)(uintptr_t)&capture_MIDIReceived;
    }
    if (strcmp(symbol, "MIDIReceivedEventList") == 0) {
        captured_MIDIReceivedEventList = resolved;
        return (void *)(uintptr_t)&capture_MIDIReceivedEventList;
    }
    if (strcmp(symbol, "SingleMidiOutput_SendMessageNowToPort") == 0) {
        captured_SendMessageNowToPort = resolved;
        return (void *)(uintptr_t)&capture_SendMessageNowToPort;
    }
    if (strcmp(symbol, "SingleMidiOutput_SendDataNowToPort") == 0) {
        captured_SendDataNowToPort = resolved;
        return (void *)(uintptr_t)&capture_SendDataNowToPort;
    }
    return resolved;
}

__attribute__((constructor)) static void install_midi_capture(void) {
    struct rebinding bindings[] = {
        {"dlsym", capture_dlsym, (void **)&real_dlsym_function},
        {"MIDISend", capture_MIDISend, (void **)&real_MIDISend},
        {"MIDISendEventList", capture_MIDISendEventList,
         (void **)&real_MIDISendEventList},
        {"MIDIReceived", capture_MIDIReceived, (void **)&real_MIDIReceived},
        {"MIDIReceivedEventList", capture_MIDIReceivedEventList,
         (void **)&real_MIDIReceivedEventList},
        {"SingleMidiOutput_SendMessageNowToPort", capture_SendMessageNowToPort,
         (void **)&real_SendMessageNowToPort},
        {"SingleMidiOutput_SendDataNowToPort", capture_SendDataNowToPort,
         (void **)&real_SendDataNowToPort},
    };
    rebind_symbols(bindings, sizeof(bindings) / sizeof(bindings[0]));
}
