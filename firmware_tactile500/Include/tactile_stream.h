#ifndef TACTILE_STREAM_H
#define TACTILE_STREAM_H

#include "tactile_protocol.h"

#define TACTILE_BUFFER_FREE     0U
#define TACTILE_BUFFER_BUILDING 1U
#define TACTILE_BUFFER_READY    2U
#define TACTILE_BUFFER_SENDING  3U

/* 状态函数必须在调用方的短临界区或互不抢占的中断中运行。
 * 采集、CRC、DMA传输均在临界区之外进行。 */
typedef struct
{
    uint8_t frame[2][TACTILE_FRAME_MAX_BYTES];
    size_t length[2];
    volatile uint8_t state[2];
    uint32_t sequence[2];
    volatile uint32_t current_sequence;
    volatile uint32_t requested_sequence;
    volatile int8_t active;
    volatile uint8_t tx_started;
    volatile uint8_t recover_requested;
    volatile uint8_t recovering;
    volatile uint8_t latched_status;
    volatile uint32_t sent_frames;
    volatile uint32_t missed_slots;
    volatile uint32_t sweep_overruns;
    volatile uint32_t tx_errors;
} TactileStream;

void TactileStream_Init(TactileStream *stream);
int TactileStream_Claim(TactileStream *stream, uint32_t *sequence);
int TactileStream_Publish(TactileStream *stream, int slot, size_t length);
int TactileStream_OnTick(TactileStream *stream, uint32_t periods,
                        uint8_t allow_transmit);
void TactileStream_TxStartFailed(TactileStream *stream);
void TactileStream_TxStarted(TactileStream *stream);
void TactileStream_TxComplete(TactileStream *stream);
void TactileStream_TxError(TactileStream *stream);
void TactileStream_RecoveryComplete(TactileStream *stream);

#endif
