"""
lora_to_supabase.py

Base station bridge program:
LoRa RX module (RYLR998) -> UART -> RYLS135 (USB-UART) -> Python -> Supabase REST -> Database

This version ONLY supports the NEW packet structure:
- fixed-width binary fields packed into 25 bytes
- transported as readable HEX ASCII (50 hex chars) inside the RYLR998 +RCV line

RYLR998 RX line formats supported:
  +RCV=<src_addr>,<len>,<payload>,<rssi>,<snr>
  +RCV=<src_addr>,<len>,<payload>

Required env vars:
  SUPABASE_URL
  SUPABASE_KEY

Optional env vars:
  LORA_PORT   (e.g. "COM5" on Windows, "/dev/tty.usbserial-XXXX" on macOS, "/dev/ttyUSB0" on Linux)
  LORA_BAUD   (default 115200)
  TABLE_NAME  (default "Wildfire_Sensor_Data")
  PRINT_RAW   ("1" to print every raw serial line, default "1")
  DRY_RUN     ("1" to parse but NOT insert into Supabase, default "0")
  STORE_META  ("1" to include src_addr/rssi/snr if your table has those columns, default "0")

Packet (25 bytes total), scaling back to floats:
  int32 lon_scaled  = lon * 100000
  int32 lat_scaled  = lat * 100000
  int16 temp_scaled = temp * 100
  int16 hum_scaled  = hum  * 100
  int32 pres_scaled = pres * 100
  int32 co_scaled   = co   * 100
  int32 co2_scaled  = co2  * 100
  uint8 fire        = 0 or 1
"""

import os
import time
import serial
import requests
import argparse
import re
import struct
from datetime import datetime
from typing import Optional, Dict, Any, Tuple


# =======================
# Configuration (env defaults; CLI overrides)
# =======================

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

TABLE = os.environ.get("TABLE_NAME", "Wildfire_Sensor_Data")
PORT = os.environ.get("LORA_PORT", "COM5")
BAUD = int(os.environ.get("LORA_BAUD", "115200"))
PRINT_RAW = os.environ.get("PRINT_RAW", "1") == "1"
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
STORE_META = os.environ.get("STORE_META", "0") == "1"

OPEN_SERIAL_RETRY_SEC = 2
NETWORK_RETRY_SEC = 2

SESSION = requests.Session()


# =======================
# PACKED payload config (HEX ASCII carrying fixed-width binary fields)
# =======================

PACKED_LEN_BYTES = 25
PACKED_LEN_HEX = PACKED_LEN_BYTES * 2  # 50 hex chars

#STM32 is little-endian. If you pack big-endian, change '<' to '>'.
PACKED_STRUCT_FMT = "<ii h h i i i B"

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


# =======================
# Helper functions
# =======================

def local_time_hhmmss() -> str:
    """Local time formatted as HH:MM:SS."""
    return datetime.now().strftime("%H:%M:%S")


def supabase_insert_row(row: Dict[str, Any]) -> None:
    """Insert a single row into Supabase via REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        # Smaller/faster since we don't need the inserted row back
        "Prefer": "return=minimal",
    }

    resp = SESSION.post(url, headers=headers, json=row, timeout=15)
    if not resp.ok:
        raise RuntimeError(f"Supabase insert failed ({resp.status_code}): {resp.text}")


# =======================
#Packed HEX payload parsing
# =======================

def parse_payload_packed_hex(payload_hex: str) -> Dict[str, Any]:
    """
    Parse fixed-width packed payload carried as HEX ASCII (50 hex chars = 25 bytes).

    Unpacked layout (25 bytes):
      int32 lon_i, int32 lat_i,
      int16 temp_i, int16 hum_i,
      int32 pres_i, int32 co_i, int32 co2_i,
      uint8 fire_u8
    """
    s = payload_hex.strip()
    if s.startswith(("0x", "0X")):
        s = s[2:]

    if len(s) != PACKED_LEN_HEX or not _HEX_RE.match(s):
        raise ValueError(
            f"Packed payload must be exactly {PACKED_LEN_HEX} hex chars (got {len(s)}): {payload_hex!r}"
        )

    b = bytes.fromhex(s)
    if len(b) != PACKED_LEN_BYTES:
        raise ValueError(f"Packed payload must be {PACKED_LEN_BYTES} bytes (got {len(b)})")

    lon_i, lat_i, temp_i, hum_i, pres_i, co_i, co2_i, fire_u8 = struct.unpack(PACKED_STRUCT_FMT, b)

    lon = lon_i / 100000.0
    lat = lat_i / 100000.0
    temp = temp_i / 100.0
    hum = hum_i / 100.0
    pres = pres_i / 100.0
    co = co_i / 100.0
    co2 = co2_i / 100.0
    fire = bool(fire_u8)

    #Your new packet doesn’t include timestamp; populate locally (or rely on Supabase created_at).
    ts = local_time_hhmmss()

    return {
        "Long": lon,
        "Lat": lat,
        "Temperature": temp,
        "Humidity": hum,
        "Pressure": pres,
        "CO": co,
        "CO2": co2,
        "Timestamp": ts,
        "Fire": fire,
    }


# =======================
#+RCV parsing
# =======================

def parse_rcv_line(line: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Extract packed-HEX payload and metadata from a RYLR998 +RCV line.

    Supported:
      +RCV=<src_addr>,<len>,<payload>,<rssi>,<snr>
      +RCV=<src_addr>,<len>,<payload>

    Returns:
      (row_dict, meta_dict) or None if not a +RCV line
    """
    line = line.strip()
    if not line.startswith("+RCV="):
        return None

    body = line[len("+RCV="):]

    # Split into: src_addr, len, rest (payload + optional ,rssi,snr)
    parts = body.split(",", 2)
    if len(parts) < 3:
        raise ValueError(f"Malformed +RCV line: {line}")

    src_addr_s = parts[0].strip()
    length_s = parts[1].strip()
    rest = parts[2].strip()

    meta: Dict[str, Any] = {"src_addr": None, "rssi": None, "snr": None, "declared_len": None}

    try:
        meta["src_addr"] = int(src_addr_s)
    except Exception:
        meta["src_addr"] = src_addr_s

    try:
        meta["declared_len"] = int(length_s)
    except Exception:
        meta["declared_len"] = None

    #If RSSI/SNR present, they are last two comma-separated tokens.
    #Payload itself is HEX (no commas), but we keep rsplit for compatibility.
    maybe = rest.rsplit(",", 2)
    if len(maybe) == 3:
        payload = maybe[0].strip()
        rssi_s = maybe[1].strip()
        snr_s = maybe[2].strip()
        try:
            meta["rssi"] = int(rssi_s)
        except Exception:
            meta["rssi"] = rssi_s
        try:
            meta["snr"] = int(snr_s)
        except Exception:
            meta["snr"] = snr_s
    else:
        payload = rest

    row = parse_payload_packed_hex(payload)

    #Optional sanity check: declared_len should be 25 for this packet type
    if meta["declared_len"] is not None and meta["declared_len"] != PACKED_LEN_BYTES:
        #Not fatal; some modules report length differently depending on encoding.
        #Keep permissive so we don’t drop real data.
        pass

    return row, meta


# =======================
#Serial open/retry
# =======================

def open_serial_forever() -> serial.Serial:
    """Open serial port with retry loop."""
    while True:
        try:
            ser = serial.Serial(PORT, BAUD, timeout=1)
            time.sleep(0.5)
            print(f"[OK] Serial connected: {PORT} @ {BAUD}")
            return ser
        except Exception as e:
            print(f"[WARN] Cannot open serial port {PORT}: {e}")
            time.sleep(OPEN_SERIAL_RETRY_SEC)


# =======================
#CLI args
# =======================

def parse_args():
    parser = argparse.ArgumentParser(description="LoRa RX (RYLR998) -> Supabase bridge (packed HEX payload)")
    parser.add_argument("--port", default=PORT, help="Serial port (e.g., COM5 or /dev/tty.usbserial-XXXX)")
    parser.add_argument("--baud", type=int, default=BAUD, help="Serial baud rate (default 115200)")
    parser.add_argument("--table", default=TABLE, help="Supabase table name")
    parser.add_argument("--print-raw", action="store_true", default=PRINT_RAW, help="Print raw serial lines")
    parser.add_argument("--no-print-raw", action="store_false", dest="print_raw", help="Disable printing raw lines")
    parser.add_argument("--dry-run", action="store_true", default=DRY_RUN, help="Parse but do not insert into Supabase")
    parser.add_argument("--store-meta", action="store_true", default=STORE_META, help="Include src_addr/rssi/snr in row (DB must have columns)")
    return parser.parse_args()


# =======================
#Main loop
# =======================

def main() -> None:
    global PORT, BAUD, TABLE, PRINT_RAW, DRY_RUN, STORE_META

    args = parse_args()
    PORT = args.port
    BAUD = args.baud
    TABLE = args.table
    PRINT_RAW = args.print_raw
    DRY_RUN = args.dry_run
    STORE_META = args.store_meta

    print("[INFO] Starting LoRa → Supabase bridge (packed HEX payload only)")
    print(f"[INFO] PORT={PORT} BAUD={BAUD} TABLE={TABLE} DRY_RUN={DRY_RUN} STORE_META={STORE_META}")

    ser = open_serial_forever()

    while True:
        try:
            raw_line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not raw_line:
                continue

            if PRINT_RAW:
                print(f"[RX] {raw_line}")

            parsed = parse_rcv_line(raw_line)
            if parsed is None:
                continue

            row, meta = parsed

            if STORE_META:
                # Only add these if your Supabase table has matching columns
                if meta.get("src_addr") is not None:
                    row["src_addr"] = meta["src_addr"]
                if meta.get("rssi") is not None:
                    row["rssi"] = meta["rssi"]
                if meta.get("snr") is not None:
                    row["snr"] = meta["snr"]

            if DRY_RUN:
                print(f"[PARSED] {row}")
                continue

            supabase_insert_row(row)
            print("[DB] Inserted row")

        except (serial.SerialException, OSError) as e:
            print(f"[ERR] Serial error: {e}. Reconnecting...")
            try:
                ser.close()
            except Exception:
                pass
            ser = open_serial_forever()

        except requests.RequestException as e:
            print(f"[ERR] Supabase/network error: {e}. Retrying...")
            time.sleep(NETWORK_RETRY_SEC)

        except ValueError as e:
            # Expected drop cases: malformed +RCV line, wrong hex length, non-hex payload, etc.
            print(f"[DROP] {e}")
            time.sleep(0.05)

        except Exception as e:
            print(f"[ERR] {e}")
            time.sleep(0.2)


if __name__ == "__main__":
    main()