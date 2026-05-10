"""
lora_to_supabase.py

Base station bridge program:
LoRa RX module (RYLR998) -> UART -> RYLS135 (USB-UART) -> Python -> Supabase REST -> Database

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

Packet types
Location
    Long (4)
    Lat (4)
Base
    Temperature (2)
    Humidity (2)
    Pressure (4)
    CO (4)
    CO2 (4)
    Fire (1)  # based on model prediction
"""

import os
import json
import time
import serial
import requests
import argparse
import re
import struct
from datetime import datetime
from typing import Optional, Dict, Any, Tuple


class CentralMonitoringStation:
    """Encapsulates LoRa serial reading, payload parsing, and Supabase insertion."""

    # class-level defaults from environment
    SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
    SUPABASE_KEY = os.environ["SUPABASE_KEY"]
    TABLE = os.environ.get("TABLE_NAME", "Wildfire_Sensor_Data")
    PORT = os.environ.get("LORA_PORT", "COM5")
    BAUD = int(os.environ.get("LORA_BAUD", "115200"))
    PRINT_RAW = os.environ.get("PRINT_RAW", "0") == "1"
    DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

    OPEN_SERIAL_RETRY_SEC = 2
    NETWORK_RETRY_SEC = 2

    HEADER_LEN_BYTES = 5
    LOCATION_LEN_BYTE = 8 + HEADER_LEN_BYTES
    BASE_LEN_BYTES = 17 + HEADER_LEN_BYTES

    LOCATION_PAYLOAD_FORMAT = "<B B B i i i"
    BASE_PAYLOAD_FORMAT = "<B B B h h i i i B i"

    _HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
    NODE_MAP_FILE = os.path.join(os.path.dirname(__file__), "node_locations.json")

    def __init__(
        self,
        supabase_url: str = SUPABASE_URL,
        supabase_key: str = SUPABASE_KEY,
        table: str = TABLE,
        port: str = PORT,
        baud: int = BAUD,
        print_raw: bool = PRINT_RAW,
        dry_run: bool = DRY_RUN,
        open_retry_sec: int = OPEN_SERIAL_RETRY_SEC,
        network_retry_sec: int = NETWORK_RETRY_SEC,
    ):
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.table = table
        self.port = port
        self.baud = baud
        self.print_raw = print_raw
        self.dry_run = dry_run
        self.open_retry_sec = open_retry_sec
        self.network_retry_sec = network_retry_sec
        self.session = requests.Session()

        # Node mapping: ID to location
        self.node_locations: Dict[int, Tuple[float, float]] = {}
        self.load_node_locations()

        # Communication Protocl
        self.ID = 0

        # expected next packet number
        self.packet_number = 0

    def __enter__(self) -> "CentralMonitoringStation":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.save_node_locations()

    def __del__(self):
        try:
            self.save_node_locations()
        except Exception:
            pass

    def local_time_hhmmss(self) -> str:
        """Local time formatted as HH:MM:SS."""
        return datetime.now().strftime("%H:%M:%S")

    def crc16_ccitt(self, data: bytes, poly=0x1021, init=0xFFFF) -> int:
        crc = init
        for b in data:
            crc ^= (b << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ poly) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return crc

    def predict_fire(self) -> float:
        """Placeholder for fire prediction logic based on sensor data."""
        return 0.0
    
    def reply_to_sender(self, ser: serial.Serial, dest_id: int, pkt_num: int, message: int, pck_type: int = 2) -> None:
        """Send a reply message back to the sender.
        Packet type 2 is for replies
        ACK is 1
        NACK is 0
        """
        type_pkt_num = ((pck_type & 0x0F) << 4) | (pkt_num & 0x0F)
        payload = struct.pack("<B B B i", self.ID, dest_id, type_pkt_num, message)
        crc16 = self.crc16_ccitt(payload)
        full_payload = payload + struct.pack("<H", crc16)
        hex_payload = full_payload.hex()
        cmd = f"AT+SEND={dest_id}, {len(full_payload)}, {hex_payload}\r\n"
        ser.write(cmd.encode("utf-8"))

    def parse_payload_packed_hex(self, payload_hex: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        s = payload_hex.strip()
        if s.startswith(("0x", "0X")):
            s = s[2:]

        byte_payload = bytes.fromhex(s)
        if len(byte_payload) == self.LOCATION_LEN_BYTE:
            send_id, dest_id, type_pkt_num, lon_i, lat_i, crc16 = struct.unpack(
                self.LOCATION_PAYLOAD_FORMAT, byte_payload
            )
            lon = lon_i / 100000.0
            lat = lat_i / 100000.0
            temp = hum = pres = co = co2 = 0.0
            self.node_locations[send_id] = (lon, lat)

        elif len(byte_payload) == self.BASE_LEN_BYTES:
            send_id, dest_id, type_pkt_num, temp_i, hum_i, pres_i, co_i, co2_i, fire_u8, crc16 = struct.unpack(
                self.BASE_PAYLOAD_FORMAT, byte_payload
            )
            lon, lat = self.node_locations.get(send_id, (0.0, 0.0))
            temp = temp_i / 100.0
            hum = hum_i / 100.0
            pres = pres_i / 100.0
            co = co_i / 100.0
            co2 = co2_i / 100.0
            fire = fire_u8 / 100.0
        else:
            raise ValueError(
                f"Unexpected payload length {len(byte_payload)} bytes (hex len {len(payload_hex)} chars)"
            )

        pkt_num = type_pkt_num & 0x0F
        pck_type = (type_pkt_num >> 4) & 0x0F

        crc_val = self.crc16_ccitt(byte_payload[:-2])
        if crc_val != crc16:
            raise ValueError(f"CRC16 mismatch: calculated {crc_val:04X} vs received {crc16:04X}")

        ts = self.local_time_hhmmss()
        fire = self.predict_fire()

        payload = {
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
        pck_info = {
            "send_id": send_id,
            "dest_id": dest_id,
            "packet_type": pck_type,
            "packet_number": pkt_num,
        }
        self.save_node_locations()
        return payload, pck_info

    def load_node_locations(self) -> None:
        if os.path.exists(self.NODE_MAP_FILE):
            try:
                with open(self.NODE_MAP_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self.node_locations = {
                    int(k): tuple(v)
                    for k, v in raw.items()
                    if isinstance(v, (list, tuple)) and len(v) == 2
                }
                print(f"[INFO] Loaded {len(self.node_locations)} node locations from {self.NODE_MAP_FILE}")
            except Exception as e:
                print(f"[WARN] Could not load node locations: {e}")
                self.node_locations = {}
        else:
            self.node_locations = {}

    def save_node_locations(self) -> None:
        try:
            with open(self.NODE_MAP_FILE, "w", encoding="utf-8") as f:
                json.dump({str(k): list(v) for k, v in self.node_locations.items()}, f, indent=2)
        except Exception as e:
            print(f"[WARN] Could not save node locations: {e}")

    def parse_rcv_line(self, line: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
        line = line.strip()
        if not line.startswith("+RCV="):
            if line.startswith("+ERR="):
                raise Exception(f"LoRa error message: {line}. 12 is CRC error")
            return None

        body = line[len("+RCV="):]
        parts = body.split(",", 2)
        if len(parts) < 3:
            raise Exception(f"Malformed +RCV line: {line}")

        src_addr_s = parts[0].strip()
        length_s = parts[1].strip()
        rest = parts[2].strip()

        meta: Dict[str, Any] = {
            "src_addr": None,
            "rssi": None,
            "snr": None,
            "declared_len": None,
        }
        try:
            meta["src_addr"] = int(src_addr_s)
        except Exception:
            meta["src_addr"] = src_addr_s

        try:
            meta["declared_len"] = int(length_s)
        except Exception:
            meta["declared_len"] = None

        parts = rest.rsplit(",", 2)
        if len(parts) == 3:
            payload = parts[0].strip()
            rssi_s = parts[1].strip()
            snr_s = parts[2].strip()
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

        payload, pkt_info = self.parse_payload_packed_hex(payload)
        return payload, pkt_info, meta

    def supabase_insert_row(self, row: Dict[str, Any]) -> None:
        url = f"{self.supabase_url}/rest/v1/{self.table}"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        resp = self.session.post(url, headers=headers, json=row, timeout=15)
        if not resp.ok:
            raise RuntimeError(f"Supabase insert failed ({resp.status_code}): {resp.text}")

    def open_serial_forever(self) -> serial.Serial:
        while True:
            try:
                ser = serial.Serial(self.port, self.baud, timeout=1)
                time.sleep(0.5)
                print(f"[OK] Serial connected: {self.port} @ {self.baud}")
                return ser
            except Exception as e:
                print(f"[WARN] Cannot open serial port {self.port}: {e}")
                time.sleep(self.open_retry_sec)

    def run(self) -> None:
        print("[INFO] Starting Central Monitoring Station")
        print(
            f"[INFO] PORT={self.port} BAUD={self.baud} TABLE={self.table} DRY_RUN={self.dry_run}"
        )

        ser = self.open_serial_forever()
        while True:
            try:
                raw_line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not raw_line:
                    continue

                if self.print_raw:
                    print(f"[RX] {raw_line}")

                parsed = self.parse_rcv_line(raw_line)
                if parsed is None:
                    continue

                data, pck_info, meta = parsed
                data["Fire"] = self.predict_fire()
                if self.dry_run:
                    print(f"[PARSED] {data}")
                    continue

                # only accept packets in order to avoid duplicates and out-of-order issues
                # the sender probably did not receive our ACK if they resent, so we resend the ACK for the previous packet number (which is what they should be resending)
                if self.packet_number != pck_info["packet_number"]:
                    print(f"Packet number mismatch: expected {self.packet_number} but got {pck_info['packet_number']}. Throwing away packet.")
                    previous_ack = 1 if self.packet_number == 1 else 0
                    self.reply_to_sender(ser, dest_id=pck_info["send_id"], pkt_num=pck_info["packet_number"], message=previous_ack)
                    continue

                # if all is well, reply with ACK, insert into DB, and increment expected packet number
                self.supabase_insert_row(data)
                print("[DB] Inserted row")
                self.reply_to_sender(ser, dest_id=pck_info["send_id"], pkt_num=pck_info["packet_number"], message=1)
                self.packet_number = (self.packet_number + 1) % 2

            except (serial.SerialException, OSError) as e:
                print(f"[ERR] Serial error: {e}. Reconnecting...")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = self.open_serial_forever()

            except requests.RequestException as e:
                print(f"[ERR] Supabase/network error: {e}. Retrying...")
                time.sleep(self.network_retry_sec)

            except ValueError as e:
                # Case of bad CRC or LoRa error, reply with NACK
                print(f"[DROP] {e}")
                self.reply_to_sender(ser, dest_id=pck_info["send_id"], pkt_num=pck_info["packet_number"], message=0)
                time.sleep(0.05)

            except Exception as e:
                print(f"[ERR] {e}")
                time.sleep(0.2)

# =======================
#CLI args
# =======================

def parse_args():
    parser = argparse.ArgumentParser(description="LoRa RX (RYLR998) -> Supabase bridge (packed HEX payload)")
    parser.add_argument("--port", default=None, help="Serial port (e.g., COM5 or /dev/tty.usbserial-XXXX)")
    parser.add_argument("--baud", type=int, default=None, help="Serial baud rate (default 115200)")
    parser.add_argument("--table", default=None, help="Supabase table name")
    parser.add_argument("--print-raw", action="store_true", default=None, help="Print raw serial lines")
    parser.add_argument("--dry-run", action="store_true", default=None, help="Parse but do not insert into Supabase")
    return parser.parse_args()


# =======================
#Main loop
# =======================

def main() -> None:
    args = parse_args()

    init_kwargs = {}
    if args.table is not None:
        init_kwargs["table"] = args.table
    if args.port is not None:
        init_kwargs["port"] = args.port
    if args.baud is not None:
        init_kwargs["baud"] = args.baud
    if args.print_raw is not None:
        init_kwargs["print_raw"] = args.print_raw
    if args.dry_run is not None:
        init_kwargs["dry_run"] = args.dry_run

    central_monitoring_station = CentralMonitoringStation(**init_kwargs)
    central_monitoring_station.run()


if __name__ == "__main__":
    main()