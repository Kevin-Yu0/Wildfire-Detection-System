/*
 * bme.h
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#ifndef INC_BME_H_
#define INC_BME_H_

#include "stm32l4xx_hal.h"

extern I2C_HandleTypeDef hi2c1;

/* ======== I2C address ======== */
#define BME280_I2C_ADDR      (0x76 << 1)

/* ======== registers ======== */
#define BME280_REG_ID         0xD0
#define BME280_REG_RESET      0xE0
#define BME280_REG_CTRL_HUM   0xF2
#define BME280_REG_CTRL_MEAS  0xF4
#define BME280_REG_CONFIG     0xF5
#define BME280_REG_PRESS_MSB  0xF7

/* ======== function prototypes ======== */

/**
 * @brief  Initialise the BME280 sensor — checks chip ID, resets,
 *         reads calibration, and configures oversampling.
 * @return 1 on success, 0 on failure
 */
uint8_t BME280_Init(void);

/**
 * @brief  Read temperature, humidity, and pressure from the BME280.
 * @param  t_c   Output: temperature in degrees Celsius
 * @param  h_rh  Output: relative humidity in percent
 * @param  p_pa  Output: pressure in Pascals
 * @return 1 on success, 0 on failure
 */
uint8_t BME280_Read(float *t_c, float *h_rh, float *p_pa);


#endif /* INC_BME_H_ */
