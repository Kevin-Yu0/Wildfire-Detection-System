/*
 * lora.c
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#include "lora.h"
#include "stm32l4xx_hal.h"   // HAL functions and types
#include <string.h>
#include <stdio.h>

/* ======== private state ======== */
static uint8_t g_seq_bit = 0;

/* ======== private helpers ======== */

static uint16_t crc16_ccitt(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < len; i++) {
        crc ^= ((uint16_t)data[i] << 8);
        for (uint8_t b = 0; b < 8; b++) {
            if (crc & 0x8000) crc = (uint16_t)((crc << 1) ^ 0x1021);
            else               crc = (uint16_t)(crc  << 1);
        }
    }
    return crc;
}

static void bytes_to_hex_str(const uint8_t *data, uint16_t len, char *out)
{
    static const char hx[] = "0123456789abcdef";
    for (uint16_t i = 0; i < len; i++) {
        out[i * 2]     = hx[data[i] >> 4];
        out[i * 2 + 1] = hx[data[i] & 0x0F];
    }
    out[len * 2] = '\0';
}

static uint8_t hex_char_to_nibble(char c)
{
    if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
    if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
    return 0;
}

static uint8_t hex_str_to_bytes(const char *hex, uint8_t *out, uint8_t max_bytes)
{
    uint8_t len = (uint8_t)(strlen(hex) / 2);
    if (len > max_bytes) len = max_bytes;
    for (uint8_t i = 0; i < len; i++)
        out[i] = (uint8_t)((hex_char_to_nibble(hex[i * 2]) << 4)
                          |  hex_char_to_nibble(hex[i * 2 + 1]));
    return len;
}

static uint16_t lora_readline(char *buf, uint16_t buf_size, uint32_t timeout_ms)
{
    uint16_t idx = 0;
    uint32_t t0  = HAL_GetTick();
    while ((HAL_GetTick() - t0) < timeout_ms && idx < buf_size - 1) {
        uint8_t b;
        if (HAL_UART_Receive(&huart1, &b, 1, 5) != HAL_OK) continue;
        if (b == '\n') {
            if (idx > 0 && buf[idx - 1] == '\r') idx--;
            break;
        }
        buf[idx++] = (char)b;
    }
    buf[idx] = '\0';
    return idx;
}

/* Send hex payload, wait for binary ACK/NACK from hub */
static uint8_t lora_send_with_ack(const char *hex_payload, uint16_t payload_byte_len)
{
    (void)payload_byte_len;
    char    cmd[256];
    char    rx_line[128];
    uint8_t reply[16];

    for (uint8_t attempt = 0; attempt < LORA_MAX_RETRIES; attempt++) {

        snprintf(cmd, sizeof(cmd), "AT+SEND=%d,%d,%s\r\n",
                 LORA_DEST_ADDRESS, (int)strlen(hex_payload), hex_payload);
        HAL_UART_Transmit(&huart1, (uint8_t *)cmd, (uint16_t)strlen(cmd), LORA_CMD_TIMEOUT_MS);

        uint32_t t0 = HAL_GetTick();

        while ((HAL_GetTick() - t0) < (uint32_t)LORA_ACK_TIMEOUT_MS) {

            uint32_t remaining = LORA_ACK_TIMEOUT_MS - (HAL_GetTick() - t0);
            if (remaining == 0) break;

            memset(rx_line, 0, sizeof(rx_line));
            lora_readline(rx_line, sizeof(rx_line), remaining);

            if (strncmp(rx_line, "+RCV=", 5) != 0) continue;

            char tmp[128];
            strncpy(tmp, rx_line + 5, sizeof(tmp) - 1);
            tmp[sizeof(tmp) - 1] = '\0';

            char *tok = strtok(tmp, ",");   /* src_addr */
            if (!tok) continue;
            tok = strtok(NULL, ",");         /* declared len */
            if (!tok) continue;
            tok = strtok(NULL, ",");         /* hex payload */
            if (!tok) continue;

            uint8_t nbytes = hex_str_to_bytes(tok, reply, sizeof(reply));
            if (nbytes < 9) continue;

            uint16_t crc_calc = crc16_ccitt(reply, (uint16_t)(nbytes - 2));
            uint16_t crc_recv = (uint16_t)(reply[nbytes - 2] | ((uint16_t)reply[nbytes - 1] << 8));
            if (crc_calc != crc_recv) continue;

            /* reply: [0]=hub_id [1]=dest_id [2]=type_pkt_num [3..6]=message [7..8]=crc */
            uint8_t  rcv_seq = reply[2] & 0x0F;
            int32_t  message;
            memcpy(&message, &reply[3], 4);

            if (rcv_seq != g_seq_bit) continue;

            if (message == ACK_MSG) {
                g_seq_bit ^= 1u;
                return 1;
            }
            if (message == NACK_MSG) break;
        }

        HAL_Delay(200);
    }

    return 0;
}

/* ======== public functions ======== */

void LoRa_Init(void)
{
    char tmp[64];
    LoRa_Cmd("AT",          LORA_CMD_TIMEOUT_MS);
    LoRa_Cmd("AT+MODE=0",   LORA_CMD_TIMEOUT_MS);
    snprintf(tmp, sizeof(tmp), "AT+BAND=%d000000", LORA_BAND_MHZ);   LoRa_Cmd(tmp, LORA_CMD_TIMEOUT_MS);
    snprintf(tmp, sizeof(tmp), "AT+NETWORKID=%d",  LORA_NETWORK_ID); LoRa_Cmd(tmp, LORA_CMD_TIMEOUT_MS);
    snprintf(tmp, sizeof(tmp), "AT+ADDRESS=%d",    LORA_ADDRESS);    LoRa_Cmd(tmp, LORA_CMD_TIMEOUT_MS);
    LoRa_Cmd("AT+PARAMETER=9,7,1,12", LORA_CMD_TIMEOUT_MS);
    snprintf(tmp, sizeof(tmp), "AT+CRFOP=%d",      LORA_RF_POWER);   LoRa_Cmd(tmp, LORA_CMD_TIMEOUT_MS);
}

void LoRa_Cmd(const char *cmd, uint32_t timeout_ms)
{
    char line[128];
    snprintf(line, sizeof(line), "%s\r\n", cmd);
    HAL_UART_Transmit(&huart1, (uint8_t *)line, (uint16_t)strlen(line), timeout_ms);
    uint8_t rx[128]; size_t i = 0;
    uint32_t t0 = HAL_GetTick();
    while ((HAL_GetTick() - t0) < timeout_ms && i < sizeof(rx) - 1) {
        uint8_t c;
        if (HAL_UART_Receive(&huart1, &c, 1, 10) == HAL_OK) rx[i++] = c;
    }
}

uint8_t LoRa_SendBasePacket(float temp_c, float hum_rh, float press_hpa,
                             float co_ppm, uint16_t co2_ppm)
{
    uint8_t  pkt[22];
    char     hex[45];
    int16_t  temp_i  = (int16_t)(temp_c    * 100.0f);
    int16_t  hum_i   = (int16_t)(hum_rh    * 100.0f);
    int32_t  pres_i  = (int32_t)(press_hpa * 100.0f);
    int32_t  co_i    = (int32_t)(co_ppm    * 100.0f);
    int32_t  co2_i   = (int32_t)co2_ppm * 100;
    uint16_t crc;

    pkt[0]  = (uint8_t)LORA_ADDRESS;
    pkt[1]  = (uint8_t)LORA_DEST_ADDRESS;
    pkt[2]  = (uint8_t)((PKT_TYPE_DATA << 4) | (g_seq_bit & 0x0F));
    memcpy(&pkt[3],  &temp_i, 2);
    memcpy(&pkt[5],  &hum_i,  2);
    memcpy(&pkt[7],  &pres_i, 4);
    memcpy(&pkt[11], &co_i,   4);
    memcpy(&pkt[15], &co2_i,  4);
    pkt[19] = 0x00;                 /* fire_u8 = 0 (predicted by hub) */
    crc     = crc16_ccitt(pkt, 20);
    pkt[20] = (uint8_t)(crc & 0xFF);
    pkt[21] = (uint8_t)(crc >> 8);

    bytes_to_hex_str(pkt, 22, hex);
    return lora_send_with_ack(hex, 22);
}

uint8_t LoRa_SendLocationPacket(float lat, float lon)
{
    uint8_t  pkt[13];
    char     hex[27];
    int32_t  lon_i = (int32_t)(lon * 100000.0f);
    int32_t  lat_i = (int32_t)(lat * 100000.0f);
    uint16_t crc;

    pkt[0] = (uint8_t)LORA_ADDRESS;
    pkt[1] = (uint8_t)LORA_DEST_ADDRESS;
    pkt[2] = (uint8_t)((PKT_TYPE_DATA << 4) | (g_seq_bit & 0x0F));
    memcpy(&pkt[3], &lon_i, 4);
    memcpy(&pkt[7], &lat_i, 4);
    crc    = crc16_ccitt(pkt, 11);
    pkt[11] = (uint8_t)(crc & 0xFF);
    pkt[12] = (uint8_t)(crc >> 8);

    bytes_to_hex_str(pkt, 13, hex);
    return lora_send_with_ack(hex, 13);
}
