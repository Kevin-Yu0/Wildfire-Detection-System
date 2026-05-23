/*
 * bme.c
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#include "bme.h"

/* ======== private calibration struct ======== */
typedef struct {
    uint16_t dig_T1; int16_t  dig_T2; int16_t  dig_T3;
    uint16_t dig_P1; int16_t  dig_P2; int16_t  dig_P3;
    int16_t  dig_P4; int16_t  dig_P5; int16_t  dig_P6;
    int16_t  dig_P7; int16_t  dig_P8; int16_t  dig_P9;
    uint8_t  dig_H1; int16_t  dig_H2; uint8_t  dig_H3;
    int16_t  dig_H4; int16_t  dig_H5; int8_t   dig_H6;
} BME280_Calib;

/* ======== private state ======== */
static BME280_Calib g_calib;
static int32_t      g_t_fine = 0;

/* ======== private helpers ======== */

static int bme280_read_regs(uint8_t reg, uint8_t *data, uint16_t len)
{
    if (HAL_I2C_Master_Transmit(&hi2c1, BME280_I2C_ADDR, &reg, 1, 100) != HAL_OK) return -1;
    if (HAL_I2C_Master_Receive (&hi2c1, BME280_I2C_ADDR, data, len, 100) != HAL_OK) return -1;
    return 0;
}

static int bme280_write_reg(uint8_t reg, uint8_t value)
{
    uint8_t buf[2] = {reg, value};
    return (HAL_I2C_Master_Transmit(&hi2c1, BME280_I2C_ADDR, buf, 2, 100) == HAL_OK) ? 0 : -1;
}

static uint8_t bme280_read_calibration(void)
{
    uint8_t buf1[26], buf2[7];
    if (bme280_read_regs(0x88, buf1, 26) != 0) return 0;
    if (bme280_read_regs(0xE1, buf2,  7) != 0) return 0;

    g_calib.dig_T1 = (uint16_t)((buf1[1] << 8) | buf1[0]);
    g_calib.dig_T2 = (int16_t)(((uint16_t)buf1[3] << 8) | buf1[2]);
    g_calib.dig_T3 = (int16_t)(((uint16_t)buf1[5] << 8) | buf1[4]);
    g_calib.dig_P1 = (uint16_t)((buf1[7] << 8) | buf1[6]);
    g_calib.dig_P2 = (int16_t)(((uint16_t)buf1[9] << 8) | buf1[8]);
    g_calib.dig_P3 = (int16_t)(((uint16_t)buf1[11] << 8) | buf1[10]);
    g_calib.dig_P4 = (int16_t)(((uint16_t)buf1[13] << 8) | buf1[12]);
    g_calib.dig_P5 = (int16_t)(((uint16_t)buf1[15] << 8) | buf1[14]);
    g_calib.dig_P6 = (int16_t)(((uint16_t)buf1[17] << 8) | buf1[16]);
    g_calib.dig_P7 = (int16_t)(((uint16_t)buf1[19] << 8) | buf1[18]);
    g_calib.dig_P8 = (int16_t)(((uint16_t)buf1[21] << 8) | buf1[20]);
    g_calib.dig_P9 = (int16_t)(((uint16_t)buf1[23] << 8) | buf1[22]);

    uint8_t h1 = 0;
    if (bme280_read_regs(0xA1, &h1, 1) != 0) return 0;
    g_calib.dig_H1 = h1;
    g_calib.dig_H2 = (int16_t)((buf2[1] << 8) | buf2[0]);
    g_calib.dig_H3 = buf2[2];
    g_calib.dig_H4 = (int16_t)(((int16_t)buf2[3] << 4) | (buf2[4] & 0x0F));
    g_calib.dig_H5 = (int16_t)(((int16_t)buf2[5] << 4) | (buf2[4] >> 4));
    g_calib.dig_H6 = (int8_t)   buf2[6];
    return 1;
}

/* ======== public functions ======== */

uint8_t BME280_Init(void)
{
    uint8_t id = 0;
    if (bme280_read_regs(BME280_REG_ID, &id, 1) != 0) return 0;
    if (id != 0x60) return 0;
    if (bme280_write_reg(BME280_REG_RESET, 0xB6) != 0) return 0;
    HAL_Delay(5);
    if (!bme280_read_calibration()) return 0;
    if (bme280_write_reg(BME280_REG_CTRL_HUM,  0x01) != 0) return 0;
    if (bme280_write_reg(BME280_REG_CONFIG,    0xA0) != 0) return 0;
    if (bme280_write_reg(BME280_REG_CTRL_MEAS, 0x27) != 0) return 0;
    return 1;
}

uint8_t BME280_Read(float *t_c, float *h_rh, float *p_pa)
{
    uint8_t  data[8];
    int32_t  adc_T, adc_P, adc_H;
    int32_t  var1, var2, T;
    int64_t  var1_p, var2_p, p;
    int32_t  v_x1_u32r;

    if (bme280_read_regs(BME280_REG_PRESS_MSB, data, 8) != 0) return 0;

    adc_P = (int32_t)(((uint32_t)data[0] << 12) | ((uint32_t)data[1] << 4) | (data[2] >> 4));
    adc_T = (int32_t)(((uint32_t)data[3] << 12) | ((uint32_t)data[4] << 4) | (data[5] >> 4));
    adc_H = (int32_t)(((uint32_t)data[6] <<  8) |  (uint32_t)data[7]);

    if (adc_T == 0x800000 || adc_P == 0x800000 || adc_H == 0x8000) return 0;

    /* temperature compensation */
    var1 = ((((adc_T >> 3) - ((int32_t)g_calib.dig_T1 << 1)))
             * ((int32_t)g_calib.dig_T2)) >> 11;
    var2 = (((((adc_T >> 4) - (int32_t)g_calib.dig_T1)
              * ((adc_T >> 4) - (int32_t)g_calib.dig_T1)) >> 12)
             * (int32_t)g_calib.dig_T3) >> 14;
    g_t_fine = var1 + var2;
    T = (g_t_fine * 5 + 128) >> 8;

    /* pressure compensation */
    var1_p = ((int64_t)g_t_fine) - 128000;
    var2_p = var1_p * var1_p * (int64_t)g_calib.dig_P6;
    var2_p = var2_p + ((var1_p * (int64_t)g_calib.dig_P5) << 17);
    var2_p = var2_p + (((int64_t)g_calib.dig_P4) << 35);
    var1_p = ((var1_p * var1_p * (int64_t)g_calib.dig_P3) >> 8)
           + ((var1_p * (int64_t)g_calib.dig_P2) << 12);
    var1_p = (((((int64_t)1) << 47) + var1_p) * (int64_t)g_calib.dig_P1) >> 33;
    if (var1_p == 0) return 0;
    p = 1048576 - adc_P;
    p = (((p << 31) - var2_p) * 3125) / var1_p;
    var1_p = ((int64_t)g_calib.dig_P9 * (p >> 13) * (p >> 13)) >> 25;
    var2_p = ((int64_t)g_calib.dig_P8 * p) >> 19;
    p = ((p + var1_p + var2_p) >> 8) + (((int64_t)g_calib.dig_P7) << 4);

    /* humidity compensation */
    v_x1_u32r = g_t_fine - (int32_t)76800;
    v_x1_u32r = (((((adc_H << 14)
                    - (((int32_t)g_calib.dig_H4) << 20)
                    - (((int32_t)g_calib.dig_H5) * v_x1_u32r))
                   + (int32_t)16384) >> 15)
                 * (((((((v_x1_u32r * (int32_t)g_calib.dig_H6) >> 10)
                        * (((v_x1_u32r * (int32_t)g_calib.dig_H3) >> 11)
                           + (int32_t)32768)) >> 10)
                      + (int32_t)2097152)
                     * (int32_t)g_calib.dig_H2 + 8192) >> 14));
    v_x1_u32r = v_x1_u32r
              - (((((v_x1_u32r >> 15) * (v_x1_u32r >> 15)) >> 7)
                  * (int32_t)g_calib.dig_H1) >> 4);
    if (v_x1_u32r < 0)         v_x1_u32r = 0;
    if (v_x1_u32r > 419430400) v_x1_u32r = 419430400;

    if (t_c)  *t_c  = (float)T / 100.0f;
    if (p_pa) *p_pa = (float)p / 25600.0f;
    if (h_rh) *h_rh = ((float)(v_x1_u32r >> 12)) / 1024.0f;
    return 1;
}


