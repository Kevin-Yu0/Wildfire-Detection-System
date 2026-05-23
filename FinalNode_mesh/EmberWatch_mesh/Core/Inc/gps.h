/*
 * gps.h
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#ifndef INC_GPS_H_
#define INC_GPS_H_

#include "stm32l4xx_hal.h"

extern UART_HandleTypeDef huart3;

/* ======== data struct ======== */
typedef struct {
    float   lat;        /* decimal degrees, negative = South */
    float   lon;        /* decimal degrees, negative = West  */
    uint8_t valid;      /* 1 = fix acquired, 0 = no fix      */
} GPS_Data_t;

/* ======== function prototypes ======== */

/**
 * @brief  Attempt to read one NMEA sentence from USART3 and
 *         parse a GPGGA fix. Non-blocking — returns immediately
 *         if no data is available. Call this every loop iteration.
 * @param  data  Pointer to GPS_Data_t struct to update
 */
void GPS_TryRead(GPS_Data_t *data);

#endif /* INC_GPS_H_ */
