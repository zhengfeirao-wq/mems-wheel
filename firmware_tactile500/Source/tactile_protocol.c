#include "tactile_protocol.h"

static void WriteU32(uint8_t *output, uint32_t value)
{
    output[0] = (uint8_t)value;
    output[1] = (uint8_t)(value >> 8);
    output[2] = (uint8_t)(value >> 16);
    output[3] = (uint8_t)(value >> 24);
}

uint16_t TactileProtocol_Crc16(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFFU; /* CRC-16/CCITT-FALSE，非反射，xorout=0。 */
    size_t index;
    unsigned int bit;

    for (index = 0U; index < length; ++index)
    {
        crc ^= (uint16_t)((uint16_t)data[index] << 8);
        for (bit = 0U; bit < 8U; ++bit)
        {
            crc = (uint16_t)((crc & 0x8000U) != 0U
                            ? ((uint32_t)crc << 1) ^ 0x1021U
                            : (uint32_t)crc << 1);
        }
    }
    return crc;
}

size_t TactileProtocol_Encode(uint8_t *output, size_t capacity,
                             uint8_t wire_version, uint8_t identity,
                             uint8_t status, uint32_t sequence,
                             uint32_t sample_time_us, uint32_t fresh_mask,
                             const int16_t *temperature,
                             const int32_t *pressure, uint8_t channels)
{
    size_t length;
    size_t offset;
    uint8_t channel;
    uint16_t crc;

    if (output == NULL || temperature == NULL || pressure == NULL ||
        (channels != 12U && channels != 32U) ||
        (((identity & 2U) != 0U) != (channels == 32U)) ||
        (channels == 12U && (identity & 4U) != 0U))
    {
        return 0U;
    }
    length = TACTILE_FRAME_OVERHEAD + (size_t)channels * 5U;
    if (capacity < length)
    {
        return 0U;
    }
    if (channels == 12U)
    {
        fresh_mask &= UINT32_C(0x00000FFF);
    }

    output[0] = 0xA5U;
    output[1] = 0x5AU;
    output[2] = (uint8_t)length;
    output[3] = wire_version;
    output[4] = identity;
    output[5] = status;
    WriteU32(output + 6, sequence);
    WriteU32(output + 10, sample_time_us);
    WriteU32(output + 14, fresh_mask);

    offset = TACTILE_FRAME_HEADER_BYTES;
    for (channel = 0U; channel < channels; ++channel)
    {
        uint16_t value = (uint16_t)temperature[channel];
        output[offset++] = (uint8_t)value;
        output[offset++] = (uint8_t)(value >> 8);
    }
    for (channel = 0U; channel < channels; ++channel)
    {
        uint32_t value = (uint32_t)pressure[channel];
        output[offset++] = (uint8_t)value;
        output[offset++] = (uint8_t)(value >> 8);
        output[offset++] = (uint8_t)(value >> 16);
    }

    crc = TactileProtocol_Crc16(output, offset);
    output[offset++] = (uint8_t)crc;
    output[offset++] = (uint8_t)(crc >> 8);
    return offset;
}
