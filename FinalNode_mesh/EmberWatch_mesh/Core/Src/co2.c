/*
 * co2.c
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#include "co2.h"

/* ======== private state ======== */
static uint8_t g_co2_err = 0;

/* ======== private helpers ======== */

static uint16_t s88_crc16(const uint8_t *data, uint8_t len)
{
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint8_t b = 0; b < 8; b++) {
            if (crc & 0x0001) crc = (crc >> 1) ^ 0xA001;
            else               crc >>= 1;
        }
    }
    return crc;
}

static void s88_clear_uart_errors(void)
{
    __HAL_UART_CLEAR_OREFLAG(&huart2);
    __HAL_UART_CLEAR_FEFLAG(&huart2);
    __HAL_UART_CLEAR_NEFLAG(&huart2);
    __HAL_UART_CLEAR_PEFLAG(&huart2);
}

/* ======== public functions ======== */

uint8_t CO2_Init(void)
{
    uint16_t tmp = 0;
    HAL_Delay(10000);  /* S88 needs 10 seconds warmup */
    return CO2_Read(&tmp);
}

uint8_t CO2_Read(uint16_t *co2_ppm)
{
    uint8_t cmd[8], rx[7];

    /* build Modbus RTU read request */
    cmd[0] = S88_MODBUS_ADDR;
    cmd[1] = S88_READ_INPUT_REG;
    cmd[2] = (uint8_t)(S88_CO2_REG >> 8);
    cmd[3] = (uint8_t)(S88_CO2_REG & 0xFF);
    cmd[4] = 0x00;
    cmd[5] = 0x01;
    uint16_t crc = s88_crc16(cmd, 6);
    cmd[6] = (uint8_t)(crc & 0xFF);
    cmd[7] = (uint8_t)((crc >> 8) & 0xFF);

    /* transmit */
    if (HAL_UART_Transmit(&huart2, cmd, 8, 200) != HAL_OK) {
        g_co2_err = 1;
        return 0;
    }

    /* receive */
    s88_clear_uart_errors();
    if (HAL_UART_Receive(&huart2, rx, 7, 2000) != HAL_OK) {
        g_co2_err = 2;
        return 0;
    }

    /* validate response */
    if (rx[1] != S88_READ_INPUT_REG || rx[2] != 0x02) {
        g_co2_err = 3;
        return 0;
    }

    /* verify CRC */
    uint16_t crc_calc = s88_crc16(rx, 5);
    uint16_t crc_recv = (uint16_t)rx[5] | ((uint16_t)rx[6] << 8);
    if (crc_calc != crc_recv) {
        g_co2_err = 4;
        return 0;
    }

    g_co2_err = 0;
    *co2_ppm = (uint16_t)((rx[3] << 8) | rx[4]);
    return 1;
}

uint8_t CO2_GetLastError(void)
{
    return g_co2_err;
}
