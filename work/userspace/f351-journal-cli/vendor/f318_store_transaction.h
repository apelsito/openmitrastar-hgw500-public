#ifndef F318_STORE_TRANSACTION_H
#define F318_STORE_TRANSACTION_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define F318_FLASH_BYTES 0x01000000u
#define F318_ERASE_BYTES 0x00010000u
#define F318_STORE_OFFSET 0x00dc0000u
#define F318_STORE_SLOT_COUNT 2u
#define F318_STORE_SLOT_BYTES F318_ERASE_BYTES
#define F318_STORE_PAYLOAD_MAX 256u

enum f318_store_status {
    F318_STORE_OK = 0,
    F318_STORE_EMPTY = 1,
    F318_STORE_EINVAL = -1,
    F318_STORE_ECLAIM = -2,
    F318_STORE_EPROTECT = -3,
    F318_STORE_EIO = -4,
    F318_STORE_EVERIFY = -5,
    F318_STORE_EWITNESS = -6
};

enum f318_store_phase {
    F318_PHASE_NONE = 0,
    F318_PHASE_CLAIM,
    F318_PHASE_SNAPSHOT,
    F318_PHASE_UNPROTECT,
    F318_PHASE_ERASE,
    F318_PHASE_PROGRAM_BODY,
    F318_PHASE_VERIFY_BODY,
    F318_PHASE_COMMIT,
    F318_PHASE_RESTORE_PROTECTION,
    F318_PHASE_VERIFY_PROTECTION,
    F318_PHASE_RELEASE,
    F318_PHASE_DONE
};

struct f318_store_ops {
    int (*claim)(void *context);
    void (*release)(void *context);
    int (*read_protection)(void *context, uint32_t block_offset,
                           uint8_t *value);
    int (*set_protection)(void *context, uint32_t block_offset,
                          uint8_t value);
    int (*erase_block)(void *context, uint32_t block_offset);
    int (*program)(void *context, uint32_t flash_offset,
                   const uint8_t *data, size_t length);
    int (*read)(void *context, uint32_t flash_offset, uint8_t *data,
                size_t length);
    int (*sync)(void *context);
    void *context;
    uint8_t unprotected_value;
};

struct f318_store_result {
    enum f318_store_phase phase;
    uint32_t slot_offset;
    size_t payload_length;
    size_t programmed_bytes;
    uint8_t protection_before;
    uint8_t protection_after;
    uint8_t protection_changed;
    uint8_t protection_restore_attempted;
    uint8_t protection_restored;
    uint8_t witnesses_unchanged;
    uint8_t commit_visible;
};

uint32_t f318_store_crc32(const uint8_t *data, size_t length);
uint32_t f318_store_slot_offset(unsigned slot);
int f318_store_write_slot(const struct f318_store_ops *ops, unsigned slot,
                          const uint8_t *payload, size_t length,
                          struct f318_store_result *result);
int f318_store_read_slot(const struct f318_store_ops *ops, unsigned slot,
                         uint8_t *payload, size_t capacity, size_t *length);

#ifdef __cplusplus
}
#endif

#endif
