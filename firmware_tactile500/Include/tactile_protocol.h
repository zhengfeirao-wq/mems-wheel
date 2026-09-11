#ifndef TACTILE_PROTOCOL_H
#define TACTILE_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

#define TACTILE_FRAME_HEADER_BYTES 18U
#define TACTILE_FRAME_OVERHEAD     20U
#define TACTILE_FRAME_MAX_BYTES    180U
#define TACTILE_INVALID_TEMP       INT16_MIN
#define TACTILE_INVALID_PRESSURE   (-8388607 - 1)

/* 低4位描述本次采集；高4位为从启动起锁存的运行异常。 */
#define TACTILE_STATUS_NOT_ALL_FRESH 0x01U
#define TACTILE_STATUS_SPI_ERROR     0x02U
#define TACTILE_STATUS_SENSOR_ERROR  0x04U
#define TACTILE_STATUS_INIT_ERROR    0x08U
#define TACTILE_STATUS_SWEEP_LATE    0x10U
#define TACTILE_STATUS_TX_BUSY       0x20U
#define TACTILE_STATUS_TX_ERROR      0x40U
#define TACTILE_STATUS_TICK_LATE     0x80U

uint16_t TactileProtocol_Crc16(const uint8_t *data, size_t length);
size_t TactileProtocol_Encode(uint8_t *output, size_t capacity,
                             uint8_t wire_version, uint8_t identity,
                             uint8_t status, uint32_t sequence,
                             uint32_t sample_time_us, uint32_t fresh_mask,
                             const int16_t *temperature,
                             const int32_t *pressure, uint8_t channels);

#endif
