/*
 * co2.h
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#ifndef INC_CO2_H_
#define INC_CO2_H_

#include "stm32l4xx_hal.h"

extern UART_HandleTypeDef huart2;

/* ======== S88 Modbus RTU config ======== */
#define S88_BAUD_RATE        9600
#define S88_MODBUS_ADDR      0xFE
#define S88_READ_INPUT_REG   0x04
#define S88_CO2_REG          0x0003

/* ======== function prototypes ======== */

/**
 * @brief  Initialise the SenseAir S88 CO2 sensor.
 *         Waits 10 seconds for sensor warmup then verifies comms.
 * @return 1 on success, 0 on failure
 */
uint8_t CO2_Init(void);

/**
 * @brief  Read CO2 concentration from the S88 via Modbus RTU.
 * @param  co2_ppm  Output: CO2 concentration in ppm
 * @return 1 on success, 0 on failure
 */
uint8_t CO2_Read(uint16_t *co2_ppm);

/**
 * @brief  Returns the last error code from a failed CO2_Read().
 * @return error code: 1=TX fail, 2=RX fail, 3=bad response, 4=bad CRC
 */
uint8_t CO2_GetLastError(void);

#endif /* INC_CO2_H_ */
