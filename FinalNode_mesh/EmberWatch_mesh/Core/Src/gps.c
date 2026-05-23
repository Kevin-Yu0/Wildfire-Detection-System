/*
 * gps.c
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#include "gps.h"
#include <string.h>
#include <stdlib.h>

/* ======== public functions ======== */

void GPS_TryRead(GPS_Data_t *data)
{
//    char    line[128];
//    uint8_t idx = 0;
//    uint8_t b;
//
//    /* sync to start of sentence — wait for '$' */
//        do {
//            if (HAL_UART_Receive(&huart3, &b, 1, 100) != HAL_OK) break;
//        } while (b != '$');
//
//        /* store the '$' and read the rest of the sentence */
//        line[idx++] = '$';
//
//    /* read one NMEA sentence; 5ms per-byte timeout drops out quickly if no data */
//    while (idx < sizeof(line) - 1) {
//        if (HAL_UART_Receive(&huart3, &b, 1, 100) != HAL_OK) break;
//        if (b == '\n') break;
//        if (b == '\r') continue;
//        line[idx++] = (char)b;
//    }
//    line[idx] = '\0';
//
//    /* only process GPGGA sentences — contains fix quality and position */
//    if (idx < 15 || strncmp(line, "$GPGGA", 6) != 0) return;
    uint8_t buf[128];
    memset(buf, 0, sizeof(buf));

    /* read up to 128 bytes in one call — 2 second timeout */
    HAL_UART_Receive(&huart3, buf, sizeof(buf), 2000);

    /* scan buffer for $GPGGA */
    char *start = NULL;
    for (int i = 0; i < 120; i++) {
        if (buf[i] == '$' &&
            buf[i+1] == 'G' &&
            buf[i+2] == 'P' &&
            buf[i+3] == 'G' &&
            buf[i+4] == 'G' &&
            buf[i+5] == 'A') {
            start = (char *)&buf[i];
            break;
        }
    }
    if (!start) return;

    /* copy into line and null terminate at \n */
    char line[128];
    strncpy(line, start, 127);
    line[127] = '\0';
    for (int i = 0; i < 127; i++) {
        if (line[i] == '\n' || line[i] == '\r') {
            line[i] = '\0';
            break;
        }
    }

    /* tokenise on comma */
    char   *fields[12];
    uint8_t nf  = 0;
    char   *tok = strtok(line, ",");
    while (tok && nf < 12) { fields[nf++] = tok; tok = strtok(NULL, ","); }

    /* field[6] = fix quality; 0 or missing = no fix */
    if (nf < 7 || fields[6][0] == '0' || fields[6][0] == '\0') return;

    /* latitude: DDMM.MMMMM -> decimal degrees */
    float lat_raw = strtof(fields[2], NULL);
    int   lat_deg = (int)(lat_raw / 100);
    float lat_dec = lat_deg + (lat_raw - (float)(lat_deg * 100)) / 60.0f;
    if (fields[3][0] == 'S') lat_dec = -lat_dec;

    /* longitude: DDDMM.MMMMM -> decimal degrees */
    float lon_raw = strtof(fields[4], NULL);
    int   lon_deg = (int)(lon_raw / 100);
    float lon_dec = lon_deg + (lon_raw - (float)(lon_deg * 100)) / 60.0f;
    if (fields[5][0] == 'W') lon_dec = -lon_dec;

    data->lat   = lat_dec;
    data->lon   = lon_dec;
    data->valid = 1;
}
