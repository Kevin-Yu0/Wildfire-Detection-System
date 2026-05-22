"""
CenteralMonitoringSystem.py

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
from pyexpat import features
import time
import serial
import requests
import argparse
import re
import struct
import joblib
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

PORT = 'COM8'
BAUD = 115200


class CentralMonitoringStation:
    """Encapsulates LoRa serial reading, payload parsing, and Supabase insertion."""

    # class-level defaults; environment variables can still override these
    SUPABASE_URL = "https://yzankkkdstzranyazqgt.supabase.co"
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    TABLE = os.environ.get("TABLE_NAME", "Wildfire_Sensor_Data")
    PORT = os.environ.get("LORA_PORT", PORT)
    BAUD = int(os.environ.get("LORA_BAUD", str(BAUD)))

    OPEN_SERIAL_RETRY_SEC = 2
    NETWORK_RETRY_SEC = 2

    HEADER_LEN_BYTES = 5
    LOCATION_LEN_BYTE = 8 + HEADER_LEN_BYTES
    BASE_LEN_BYTES = 17 + HEADER_LEN_BYTES

    LOCATION_PAYLOAD_FORMAT = "<B B B i i H"
    BASE_PAYLOAD_FORMAT = "<B B B h h i i i B H"

    _HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
    NODE_MAP_FILE = os.path.join(os.path.dirname(__file__), "node_locations.json")

    def __init__(
        self,
        supabase_url: str = SUPABASE_URL,
        supabase_key: str = SUPABASE_KEY,
        table: str = TABLE,
        port: str = PORT,
        baud: int = BAUD,
        open_retry_sec: int = OPEN_SERIAL_RETRY_SEC,
        network_retry_sec: int = NETWORK_RETRY_SEC,
    ):
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.table = table
        self.port = port
        self.baud = baud
        self.open_retry_sec = open_retry_sec
        self.network_retry_sec = network_retry_sec
        self.session = requests.Session()

        # Node mapping: ID to location
        self.node_locations: Dict[int, Tuple[float, float]] = {}
        self.load_node_locations()

        # Communication Protocl
        self.ID = 0

        # expected next packet number
        self.packet_number: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        # Load ML model for fire prediction
        try:
            self.model = joblib.load("fire_model.joblib")
            self.scaler = joblib.load("fire_scaler.joblib")
            print("✓ ML model and scaler loaded successfully")
        except Exception as e:
            print(f"✗ Could not load ML model or scaler: {e}")
            self.model = None
            self.scaler = None

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

    def predict_fire(self, temp: float, hum: float, pres: float, co: float, co2: float) -> float:
        features = pd.DataFrame([{
        "temperature": temp,
        "humidity": hum,
        "pressure": pres,
        "co_ppm": co,
        "co2_ppm": co2
        }])

        features_scaled = self.scaler.transform(features)
        risk = self.model.predict(features_scaled)[0] 
        risk = max(0.0, min(1.0, risk))
        return float(risk)

    def print_telemetry_base(self, data: Dict[str, Any], pck_info: Dict[str, Any], meta: Dict[str, Any], duplicate: bool = False) -> None:
        tag = "  [DUPLICATE — ACK only]" if duplicate else ""
        print("─" * 52)
        print(f"  Node     {pck_info['send_id']}   seq={pck_info['packet_number']}{tag}")
        print(f"  Temp     {data['Temperature']:.2f} °C")
        print(f"  Humidity {data['Humidity']:.2f} %RH")
        print(f"  Pressure {data['Pressure']:.2f} hPa")
        print(f"  CO       {data['CO']:.2f} ppm")
        print(f"  CO2      {data['CO2']:.2f} ppm")
        print(f"  Fire     {data['Fire']:.2f}")
        if meta.get("rssi") is not None:
            print(f"  RSSI     {meta['rssi']} dBm   SNR {meta['snr']} dB")
        print("─" * 52)

    def print_telemetry_location(self, data: Dict[str, Any], pck_info: Dict[str, Any], meta: Dict[str, Any]) -> None:
        print("─" * 52)
        print(f"  Node     {pck_info['send_id']}   [LOCATION]")
        print(f"  Lon      {data['Long']:.5f}")
        print(f"  Lat      {data['Lat']:.5f}")
        if meta.get("rssi") is not None:
            print(f"  RSSI     {meta['rssi']} dBm   SNR {meta['snr']} dB")
        print("─" * 52)

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
        cmd = f"AT+SEND={dest_id},{len(hex_payload)},{hex_payload}\r\n"
        ser.write(cmd.encode("utf-8"))

    def parse_payload_packed_hex(self, payload_hex: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        s = payload_hex.strip()
        if s.startswith(("0x", "0X")):
            s = s[2:]

        byte_payload = bytes.fromhex(s)
        if len(byte_payload) == self.LOCATION_LEN_BYTE:
            payload_type = "LOCATION"
            send_id, dest_id, type_pkt_num, lon_i, lat_i, crc16 = struct.unpack(
                self.LOCATION_PAYLOAD_FORMAT, byte_payload
            )
            lon = lon_i / 100000.0
            lat = lat_i / 100000.0
            temp = hum = pres = co = co2 = 0.0
            if send_id not in self.node_locations:
                self.node_locations[send_id] = (lon, lat)

        elif len(byte_payload) == self.BASE_LEN_BYTES:
            payload_type = "BASE"
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
        fire = self.predict_fire(temp, hum, pres, co, co2)

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
            "payload_type": payload_type,
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
                print(f"✓ Loaded {len(self.node_locations)} node locations from {self.NODE_MAP_FILE}")
            except Exception as e:
                print(f"  Could not load node locations: {e}")
                self.node_locations = {}
        else:
            self.node_locations = {}

    def save_node_locations(self) -> None:
        try:
            new_data = {str(k): list(v) for k, v in self.node_locations.items() if v != (0.0, 0.0)}

            # If file exists, merge instead of overwrite
            if os.path.exists(self.NODE_MAP_FILE):
                with open(self.NODE_MAP_FILE, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)

                # only add missing keys
                for k, v in new_data.items():
                    if k not in existing_data:
                        existing_data[k] = v

                data_to_save = existing_data
            else:
                data_to_save = new_data

            # write back once
            with open(self.NODE_MAP_FILE, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=2)

        except Exception as e:
            print(f"  Could not save node locations: {e}")

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

    def supabase_insert_row(self, row: Dict[str, Any], meta: Dict[str, Any]) -> None:
        url = f"{self.supabase_url}/rest/v1/{self.table}"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        # Include metadata if the table has those columns
        if "src_addr" in meta:
            row["SensorID"] = meta["src_addr"]
        if "rssi" in meta:
            row["RSSI"] = meta["rssi"]
        if "snr" in meta:
            row["SNR"] = meta["snr"]
        resp = self.session.post(url, headers=headers, json=row, timeout=15)
        if not resp.ok:
            print(f"Supabase insert failed ({resp.status_code}): {resp.text}")
        else:
            print("  ✓ row inserted")

    def open_serial_forever(self) -> serial.Serial:
        while True:
            try:
                print(f"Opening {self.port} at {self.baud} baud...")
                ser = serial.Serial(self.port, self.baud, timeout=1)
                time.sleep(0.5)

                # Basic module check
                ser.write(b"AT\r\n")
                time.sleep(0.5)
                resp = ser.read(ser.in_waiting)
                print(f"Module response: {resp}")

                if b"+OK" not in resp and b"AT" not in resp:
                    print("✗ No response from LoRa module — check wiring / port")
                    ser.close()
                    time.sleep(self.open_retry_sec)
                    continue

                print("✓ Module responding")

                commands = [
                    "AT+BAND=915000000",
                    f"AT+ADDRESS={self.ID}",
                    "AT+NETWORKID=3",
                    "AT+PARAMETER=9,7,1,12",
                    "AT+CRFOP=14",
                    "AT+MODE=0",
                ]
                for cmd in commands:
                    ser.write((cmd + "\r\n").encode())
                    time.sleep(0.3)
                    r = ser.read(ser.in_waiting).decode("utf-8", errors="ignore")
                    print(f"  {cmd}  ->  {r.strip()}")

                print("\nSystem ready — listening for node packets...\n")
                return ser

            except KeyboardInterrupt:
                raise

            except Exception as e:
                print(f"✗ Cannot open serial port {self.port}: {e}")
                time.sleep(self.open_retry_sec)

    def run(self) -> None:
        print("Starting Central Monitoring Station")
        print(f"PORT={self.port}  BAUD={self.baud}  TABLE={self.table}\n")

        ser = self.open_serial_forever()
        while True:
            try:
                raw_line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not raw_line:
                    continue

                parsed = self.parse_rcv_line(raw_line)
                if parsed is None:
                    continue

                data, pck_info, meta = parsed

                is_duplicate = (self.packet_number[pck_info["send_id"]] != pck_info["packet_number"])

                if pck_info["payload_type"] == "LOCATION":
                    self.print_telemetry_location(data, pck_info, meta)
                else:
                    self.print_telemetry_base(data, pck_info, meta, duplicate=is_duplicate)

                if is_duplicate:
                    self.reply_to_sender(ser, dest_id=pck_info["send_id"], pkt_num=pck_info["packet_number"], message=1)
                    continue
                
                if pck_info["payload_type"] == "BASE":
                    self.supabase_insert_row(data, meta)

                self.reply_to_sender(ser, dest_id=pck_info["send_id"], pkt_num=pck_info["packet_number"], message=1)
                self.packet_number[pck_info["send_id"]] = (self.packet_number[pck_info["send_id"]] + 1) % 2

            except KeyboardInterrupt:
                raise

            except (serial.SerialException, OSError) as e:
                print(f"✗ Serial error: {e} — reconnecting...")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = self.open_serial_forever()

            except requests.RequestException as e:
                print(f"✗ Network error: {e} — retrying...")
                time.sleep(self.network_retry_sec)

            except ValueError as e:
                # Case of bad CRC or LoRa error, reply with NACK
                print(f"  [NACK] {e}")
                self.reply_to_sender(ser, dest_id=pck_info["send_id"], pkt_num=pck_info["packet_number"], message=0)
                time.sleep(0.05)

            except Exception as e:
                print(f"✗ {e}")
                time.sleep(0.2)

# =======================
#CLI args
# =======================

def parse_args():
    parser = argparse.ArgumentParser(description="LoRa RX (RYLR998) -> Supabase bridge (packed HEX payload)")
    parser.add_argument("--port", default=None, help="Serial port (e.g., COM5 or /dev/tty.usbserial-XXXX)")
    parser.add_argument("--baud", type=int, default=None, help="Serial baud rate (default 115200)")
    parser.add_argument("--table", default=None, help="Supabase table name")
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

    central_monitoring_station = CentralMonitoringStation(**init_kwargs)
    try:
        central_monitoring_station.run()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
