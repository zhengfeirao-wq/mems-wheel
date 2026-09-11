#include "tactile_stream.h"
#include <string.h>

void TactileStream_Init(TactileStream *stream)
{
    memset(stream, 0, sizeof(*stream));
    stream->active = -1;
    stream->requested_sequence = 1U;
}

int TactileStream_Claim(TactileStream *stream, uint32_t *sequence)
{
    int slot;
    if (stream->recover_requested != 0U || stream->recovering != 0U)
    {
        return -1;
    }
    for (slot = 0; slot < 2; ++slot)
    {
        if ((stream->state[slot] == TACTILE_BUFFER_BUILDING ||
             stream->state[slot] == TACTILE_BUFFER_READY) &&
            stream->sequence[slot] == stream->requested_sequence)
        {
            return -1; /* 当前周期已经有一份数据，不能重复构建。 */
        }
    }
    for (slot = 0; slot < 2; ++slot)
    {
        if (stream->state[slot] == TACTILE_BUFFER_FREE)
        {
            stream->sequence[slot] = stream->requested_sequence;
            stream->state[slot] = TACTILE_BUFFER_BUILDING;
            *sequence = stream->sequence[slot];
            return slot;
        }
    }
    return -1;
}

int TactileStream_Publish(TactileStream *stream, int slot, size_t length)
{
    if (slot < 0 || slot > 1 ||
        stream->state[slot] != TACTILE_BUFFER_BUILDING)
    {
        return 0;
    }
    if (stream->sequence[slot] != stream->requested_sequence ||
        length == 0U || length > TACTILE_FRAME_MAX_BYTES)
    {
        stream->state[slot] = TACTILE_BUFFER_FREE;
        ++stream->sweep_overruns;
        stream->latched_status |= TACTILE_STATUS_SWEEP_LATE;
        return 0;
    }
    stream->length[slot] = length;
    stream->state[slot] = TACTILE_BUFFER_READY;
    return 1;
}

int TactileStream_OnTick(TactileStream *stream, uint32_t periods,
                        uint8_t allow_transmit)
{
    int slot;
    int ready = -1;
    if (periods == 0U)
    {
        return -1;
    }
    stream->current_sequence += periods;
    stream->requested_sequence = stream->current_sequence + 1U;
    if (periods > 1U || allow_transmit == 0U)
    {
        stream->latched_status |= TACTILE_STATUS_TICK_LATE;
    }
    for (slot = 0; slot < 2; ++slot)
    {
        if (stream->state[slot] == TACTILE_BUFFER_READY)
        {
            if (stream->sequence[slot] == stream->current_sequence)
            {
                ready = slot;
            }
            else
            {
                stream->state[slot] = TACTILE_BUFFER_FREE;
            }
        }
    }
    if (stream->active >= 0)
    {
        stream->latched_status |= TACTILE_STATUS_TX_BUSY;
        if ((uint32_t)(stream->current_sequence -
                       stream->sequence[stream->active]) >= 2U)
        {
            stream->recover_requested = 1U;
        }
    }
    if (stream->active >= 0 || stream->recover_requested != 0U ||
        stream->recovering != 0U || allow_transmit == 0U || ready < 0)
    {
        if (ready >= 0)
        {
            stream->state[ready] = TACTILE_BUFFER_FREE;
        }
        if (ready < 0 && stream->active < 0 &&
            stream->recover_requested == 0U && allow_transmit != 0U)
        {
            stream->latched_status |= TACTILE_STATUS_SWEEP_LATE;
        }
        stream->missed_slots += periods;
        return -1; /* 跳过过期槽位，不补发突发包、不覆盖正在发送的数据。 */
    }
    stream->missed_slots += periods - 1U;
    stream->state[ready] = TACTILE_BUFFER_SENDING;
    stream->active = (int8_t)ready;
    stream->tx_started = 0U;
    return ready;
}

void TactileStream_TxStarted(TactileStream *stream)
{
    if (stream->active >= 0)
    {
        stream->tx_started = 1U;
    }
}

void TactileStream_TxStartFailed(TactileStream *stream)
{
    ++stream->tx_errors;
    ++stream->missed_slots;
    stream->latched_status |= TACTILE_STATUS_TX_ERROR;
    stream->recover_requested = 1U;
    /* 未确认底层停止前，仍保留 SENDING 所有权。 */
}

void TactileStream_TxComplete(TactileStream *stream)
{
    if (stream->active >= 0)
    {
        stream->state[stream->active] = TACTILE_BUFFER_FREE;
        stream->active = -1;
        if (stream->tx_started != 0U)
        {
            ++stream->sent_frames;
        }
        stream->tx_started = 0U;
    }
}

void TactileStream_TxError(TactileStream *stream)
{
    ++stream->tx_errors;
    stream->latched_status |= TACTILE_STATUS_TX_ERROR;
    stream->recover_requested = 1U;
}

void TactileStream_RecoveryComplete(TactileStream *stream)
{
    if (stream->active >= 0)
    {
        stream->state[stream->active] = TACTILE_BUFFER_FREE;
        stream->active = -1;
    }
    stream->recover_requested = 0U;
    stream->recovering = 0U;
    stream->tx_started = 0U;
}
