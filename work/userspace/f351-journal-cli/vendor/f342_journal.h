/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F342_CONFIG_JOURNAL_H
#define F342_CONFIG_JOURNAL_H

#include <stddef.h>
#include <stdint.h>
#include "f318_store_transaction.h"

/* Same two reserved blocks as F318. This API never takes a physical address. */
#define F342_PAYLOAD_MAX 4096u
#define F342_PAGE_BYTES 256u
#define F342_HEADER_BYTES 32u
#define F342_SLOT_NONE 2u

enum f342_status {
 F342_OK = 0, F342_EMPTY = 1,
 F342_EINVAL = -1, F342_ECLAIM = -2, F342_EIO = -3,
 F342_ECORRUPT = -4, F342_ECAPACITY = -5, F342_ESEQUENCE = -6,
 F342_EPROTECT = -7, F342_EVERIFY = -8, F342_EWITNESS = -9
};
enum f342_slot_state { F342_SLOT_UNREAD, F342_SLOT_EMPTY, F342_SLOT_INVALID, F342_SLOT_VALID };
enum f342_phase {
 F342_PHASE_NONE, F342_PHASE_CLAIM, F342_PHASE_SCAN,
 F342_PHASE_SNAPSHOT, F342_PHASE_UNPROTECT, F342_PHASE_ERASE,
 F342_PHASE_BODY, F342_PHASE_VERIFY, F342_PHASE_COMMIT,
 F342_PHASE_RESTORE, F342_PHASE_WITNESSES, F342_PHASE_DONE
};
struct f342_record {
 uint64_t sequence;
 uint32_t length;
 unsigned slot;
};
struct f342_workspace {
 uint8_t page[F342_PAGE_BYTES];
 uint8_t verify[F342_PAGE_BYTES];
 uint8_t header[F342_HEADER_BYTES];
 uint8_t witnesses[8];
};
struct f342_result {
 enum f342_phase phase;
 enum f342_phase failure_phase;
 enum f342_slot_state slots[2];
 struct f342_record record;
 unsigned target_slot, claimed, released, commit_program_attempted;
 unsigned commit_visible, protection_restore_attempted, protection_restored;
 unsigned witnesses_unchanged;
 uint8_t protection_before, protection_after;
 int primary_status, restore_status, witness_status, commit_readback_status;
 size_t programmed_bytes; /* Only bytes whose write/readback was confirmed. */
 unsigned program_calls;
};

/* Provider must serialize ALL flash readers/command-mode users under claim.
 * Program must implement NOR page writes and read must provide uncached truth.
 * The pure core cannot establish electrical ownership or bus completion.
 * Caller keeps save payload immutable until return. No payload is logged.
 * Workspace, result and payload must not overlap. Load's payload is a staging
 * buffer: ignore it unless return==F342_OK (I/O errors may leave a prefix).
 * Sequence is 1..UINT64_MAX with no wrap. Two valid equal sequences are errors.
 * If no record is valid, save uses only a wholly erased block. It never formats
 * two occupied unknown/torn blocks. An existing valid record establishes the
 * two-slot journal, permitting reuse of its inactive reserved block.
 */
int f342_save(const struct f318_store_ops *, struct f342_workspace *,
              const uint8_t *payload, size_t length, struct f342_result *);
int f342_load(const struct f318_store_ops *, struct f342_workspace *,
              uint8_t *payload, size_t capacity, struct f342_result *);
int f342_inspect(const struct f318_store_ops *, struct f342_workspace *,
                 struct f342_result *);

#endif
