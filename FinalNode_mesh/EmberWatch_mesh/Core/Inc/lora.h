/*
 * lora.h
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#ifndef INC_LORA_H_
#define INC_LORA_H_

#include "stm32l4xx_hal.h"   // HAL functions and types
extern UART_HandleTypeDef huart1;
/* ======== LoRa configuration ======== */
#define LORA_CMD_TIMEOUT_MS  500
#define LORA_ACK_TIMEOUT_MS  5000
#define LORA_MAX_RETRIES     3
#define LORA_BAND_MHZ        915
#define LORA_NETWORK_ID      3
#define LORA_ADDRESS         1  // set node id before flashing
#define LORA_DEST_ADDRESS    0
#define LORA_RF_POWER        14

/* ======== packet protocol ======== */
#define PKT_TYPE_DATA        0x01
#define PKT_TYPE_REPLY       0x02
#define ACK_MSG              1
#define NACK_MSG             0

/* ======== function prototypes ======== */

/**
 * @brief  Initialise and configure the LoRa module over USART1.
 *         Must be called after MX_USART1_UART_Init().
 */
void LoRa_Init(void);

/**
 * @brief  Send a raw AT command and wait up to timeout_ms for a response.
 * @param  cmd        AT command string (without \r\n)
 * @param  timeout_ms Timeout in milliseconds
 */
void LoRa_Cmd(const char *cmd, uint32_t timeout_ms);

/**
 * @brief  Pack and transmit a BASE sensor data packet (22 bytes).
 *         Retries up to LORA_MAX_RETRIES times waiting for ACK.
 * @param  temp_c    Temperature in degrees Celsius
 * @param  hum_rh    Relative humidity in percent
 * @param  press_hpa Pressure in hPa
 * @param  co_ppm    CO concentration in ppm
 * @param  co2_ppm   CO2 concentration in ppm
 * @return 1 if ACK received, 0 if all retries failed
 */
uint8_t LoRa_SendBasePacket(float temp_c, float hum_rh, float press_hpa,
                             float co_ppm, uint16_t co2_ppm);

/**
 * @brief  Pack and transmit a LOCATION packet (13 bytes).
 *         Retries up to LORA_MAX_RETRIES times waiting for ACK.
 * @param  lat  Latitude  in decimal degrees
 * @param  lon  Longitude in decimal degrees
 * @return 1 if ACK received, 0 if all retries failed
 */
uint8_t LoRa_SendLocationPacket(float lat, float lon);


#endif /* INC_LORA_H_ */
