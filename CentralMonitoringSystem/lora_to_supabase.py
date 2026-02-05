"""
lora_to_supabase.py

base station bridge program:
LoRa RX module (RYLR998) -> UART -> RYLS135 (USB-UART) -> Python -> Supabase REST -> Database

What this program dos:
*opens the serial port connected to your RYLR998 receiver (via RYLS135)
*watches for incoming lines that look like: +RCV=... (our standardized CSV format)
*extracts the payload from te CSV sensor packet
* maps payload fields to your supabase table columns
* inserts each packet as a new row into supabase
*keeps running forever (reconnects on serial disconnect & retries on network errors)

required env vars: (you set these before yhou run this program)
  SUPABASE_URL
  SUPABASE_KEY

optional env vars:
  LORA_PORT   (e.g. "COM5" on windows, "/dev/tty.usbserial-XXXX" on macos, "/dev/ttyUSB0" on linux)
  LORA_BAUD   (default 115200)
  TABLE_NAME  (default "Wildfire_Sensor_Data")
  PRINT_RAW   ("1" to print every raw serial line, default "1")
  DRY_RUN     ("1" to parse but NOT insert into Supabase, default "0")
  STORE_META  ("1" to include rssi/snr/src_addr if your table has those columns, default "0")

look at "DB Pipeline & Standardized Payload Format (CSV)" on shared drive for CSV format
standardized payload format expected (CSV):
  Long,Lat,Temperature,Humidity,Pressure,CO,CO2,Timestamp,Fire

example payload:
  -119.8431,34.4140,30.6,30.2,1030.3,3.1,512.0,12:34:56,false

common RYLR998 RX line formats supported:
  +RCV=<src_addr>,<len>,<payload>,<rssi>,<snr>
  +RCV=<src_addr>,<len>,<payload>
if the module prints slightly different then adjust `parse_rcv_line()`.
"""

import os
import time
import serial
import requests
import argparse  # !!! CHANGED: use argparse so user can set options via command line
import csv       # !!! CHANGED: robust CSV parsing (handles edge cases)
from io import StringIO  # !!! CHANGED: csv.reader expects a file-like object
import hashlib   # !!! CHANGED: checksum verification
from datetime import datetime, timezone
from typing import Optional, Dict, Any


#configuration env vars. add these before you run this program or you wont have permission from supabase
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# !!! CHANGED: user can set TABLE/PORT/BAUD/PRINT_RAW/DRY_RUN via argparse; env vars remain as defaults
TABLE = os.environ.get("TABLE_NAME", "Wildfire_Sensor_Data")
PORT = os.environ.get("LORA_PORT", "COM5")
BAUD = int(os.environ.get("LORA_BAUD", "115200"))
PRINT_RAW = os.environ.get("PRINT_RAW", "1") == "1"
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"  #MAKE COMMAND LINE VARIABLE

OPEN_SERIAL_RETRY_SEC = 2
NETWORK_RETRY_SEC = 2

SESSION = requests.Session()


# =======================
# Helper functions
# =======================

# !!! CHANGED: if created_at is omitted, Supabase can auto-fill it (so we no longer need this)
def iso_utc_now() -> str:
    """UTC timestamp for created_at (ISO-8601)."""
    return datetime.now(timezone.utc).isoformat()

# !!! CHANGED: timestamp fallback removed; checksum will be used for validation instead
def local_time_hhmmss() -> str:
    """local time formatted as HH:MM:SS."""
    return datetime.now().strftime("%H:%M:%S")


def supabase_insert_row(row: Dict[str, Any]) -> Any:
    """insert a single row into supabase via REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    resp = SESSION.post(url, headers=headers, json=row, timeout=15)
    if not resp.ok:
        raise RuntimeError(
            f"Supabase insert failed ({resp.status_code}): {resp.text}"
        )
    return resp.json()


# !!! CHANGED: payload now includes checksum; invalid payload is ignored (no insert)
# Expected formats:
#   <CSV_FIELDS>|<checksum>
# Where checksum = first 8 hex chars of SHA256(CSV_FIELDS) (you can change this convention later).
def verify_checksum(payload_with_checksum: str) -> str:
    """
    Returns the CSV portion if checksum is valid; raises ValueError if invalid.

    payload_with_checksum:
      "Long,Lat,Temperature,Humidity,Pressure,CO,CO2,Timestamp,Fire|abcd1234"
    """
    if "|" not in payload_with_checksum:
        raise ValueError("Missing checksum delimiter '|' in payload")

    csv_part, checksum = payload_with_checksum.rsplit("|", 1)
    csv_part = csv_part.strip()
    checksum = checksum.strip().lower()

    computed = hashlib.sha256(csv_part.encode("utf-8")).hexdigest()[:8]
    if computed != checksum:
        raise ValueError(f"Checksum mismatch (expected={checksum}, computed={computed})")

    return csv_part


def parse_payload_csv(payload: str) -> Dict[str, Any]:
    """
    parse CSV payload into a supabase row
    eexpected CSV:
      Long,Lat,Temperature,Humidity,Pressure,CO,CO2,Timestamp,Fire
    """
    """
    import csv
    from io import StringIO

    def to_float(x):
        x = x.strip()
        if x == "" or x.lower() == "null":
            return None
        return float(x)

    reader = csv.reader(StringIO(payload))
    fields = next(reader)

    if len(fields) != 9:
        raise ValueError(f"Expected 9 fields, got {len(fields)}")

    (
        lon,
        lat,
        temp,
        hum,
        pres,
        co,
        co2,
        ts,
        device_id
    ) = fields

    lon, lat, temp, hum, pres, co, co2 = map(to_float, [
        lon, lat, temp, hum, pres, co, co2
    ])
    """

    # !!! CHANGED: verify checksum and then parse CSV robustly (csv.reader handles quoting/whitespace)
    payload_csv = verify_checksum(payload)

    reader = csv.reader(StringIO(payload_csv))
    fields = next(reader, None)
    if fields is None:
        raise ValueError("Empty CSV payload after checksum verification")

    fields = [x.strip() for x in fields]
    if len(fields) != 9:
        raise ValueError(f"Expected 9 CSV fields, got {len(fields)}: {payload_csv}")

    lon = float(fields[0])
    lat = float(fields[1])
    temp = float(fields[2])
    hum = float(fields[3])
    pres = float(fields[4])
    co = float(fields[5])
    co2 = float(fields[6])

    ts = fields[7]

    # !!! CHANGED: removed local timestamp fallback; payload must be valid (checksum already enforced)
    if not ts or len(ts) < 5:
        raise ValueError(f"Invalid Timestamp field: {ts!r}")

    # !!! leave this comment, we will change this portion later based off of our model
    fire = fields[8].lower()
    if fire not in ("true", "false"):
        fire = "false"

    return {
        # !!! CHANGED: omit created_at so Supabase can auto-fill it
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

# !!! CHANGED: cleaner parsing by explicitly extracting payload slice and handling rssi/snr stripping
def parse_rcv_line(line: str) -> Optional[Dict[str, Any]]:
    """
    extract payload from a RYLR998 +RCV line and convert to supabase row
    supported formats:
      +RCV=<src_addr>,<len>,<payload>,<rssi>,<snr>
      +RCV=<src_addr>,<len>,<payload>
    """
    line = line.strip()
    if not line.startswith("+RCV="):
        return None

    body = line[len("+RCV="):]

    parts = body.split(",", 2)
    if len(parts) < 3:
        raise ValueError(f"Malformed +RCV line: {line}")

    rest = parts[2].strip()

    # remove RSSI/SNR if present (payload itself may contain commas)
    # payload is everything except the last two comma-separated tokens (rssi,snr)
    maybe = rest.rsplit(",", 2)
    payload = maybe[0].strip() if len(maybe) == 3 else rest

    return parse_payload_csv(payload)


def open_serial_forever() -> serial.Serial:
    """open serial port with retry loop."""
    while True:
        try:
            ser = serial.Serial(PORT, BAUD, timeout=1)
            time.sleep(0.5)
            print(f"[OK] Serial connected: {PORT} @ {BAUD}")
            return ser
        except Exception as e:
            print(f"[WARN] Cannot open serial port {PORT}: {e}")
            time.sleep(OPEN_SERIAL_RETRY_SEC)


# !!! CHANGED: argparse wiring for TABLE/PORT/BAUD/PRINT_RAW/DRY_RUN
def parse_args():
    parser = argparse.ArgumentParser(description="LoRa RX (RYLR998) -> Supabase bridge")
    parser.add_argument("--port", default=PORT, help="Serial port (e.g., COM5 or /dev/tty.usbserial-XXXX)")
    parser.add_argument("--baud", type=int, default=BAUD, help="Serial baud rate (default 115200)")
    parser.add_argument("--table", default=TABLE, help="Supabase table name")
    parser.add_argument("--print-raw", action="store_true", default=PRINT_RAW, help="Print raw serial lines")
    parser.add_argument("--no-print-raw", action="store_false", dest="print_raw", help="Disable printing raw lines")
    parser.add_argument("--dry-run", action="store_true", default=DRY_RUN, help="Parse but do not insert into Supabase")
    return parser.parse_args()


def main() -> None:
    global PORT, BAUD, TABLE, PRINT_RAW, DRY_RUN  # !!! CHANGED: update runtime config from argparse

    args = parse_args()
    PORT = args.port
    BAUD = args.baud
    TABLE = args.table
    PRINT_RAW = args.print_raw
    DRY_RUN = args.dry_run

    print("[INFO] Starting LoRa → Supabase bridge")
    print(f"[INFO] PORT={PORT} BAUD={BAUD} TABLE={TABLE} DRY_RUN={DRY_RUN}")

    ser = open_serial_forever()

    while True:
        try:
            raw = ser.readline().decode("utf-8", errors="ignore").strip()
            if not raw:
                continue

            if PRINT_RAW:
                print(f"[RX] {raw}")

            row = parse_rcv_line(raw)
            if row is None:
                continue

            if DRY_RUN:
                print(f"[PARSED] {row}")
                continue

            inserted = supabase_insert_row(row)
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

        except Exception as e:
            print(f"[ERR] {e}")
            time.sleep(0.2)


if __name__ == "__main__":
    main()