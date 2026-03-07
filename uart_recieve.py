"""
hub_receiver.py — LoRa base station receiver (POC / ACK testing)

Packet format received from node:
  D,<node_id>,<seq>,<temp_i>,<hum_i>,<press_i>,<co_i>,<co2_i>
  All sensor values are integers = real_value * 100.

Hub replies:
  A,<node_id>,<seq>   — ACK: good packet, seq matches what we expected
  N,<node_id>,<seq>   — NACK: could not parse (node will retransmit)

Alternating-bit protocol (per node):
  - We track the last accepted seq bit for each node ID.
  - If seq == expected  → new packet, process + ACK + flip expected
  - If seq != expected  → duplicate (retry from node), ACK again but skip print
  - If parse fails      → NACK
"""

import serial
import time

PORT = '/dev/tty.usbserial-2140'
BAUD = 115200

# ------------------------------------------------------------------
# Per-node state for the alternating-bit protocol.
# Keyed by node_id (int).  Value is the next expected seq bit (0 or 1).
# ------------------------------------------------------------------
node_expected_seq: dict[int, int] = {}


def send_ack(ser: serial.Serial, node_id: int, seq: int) -> None:
    payload = f"A,{node_id},{seq}"
    cmd     = f"AT+SEND={node_id},{len(payload)},{payload}\r\n"
    ser.write(cmd.encode())
    time.sleep(0.1)                         # give module time to transmit
    ser.read(ser.in_waiting)                # drain "+OK" / "+ERR"


def send_nack(ser: serial.Serial, node_id: int, seq: int) -> None:
    payload = f"N,{node_id},{seq}"
    cmd     = f"AT+SEND={node_id},{len(payload)},{payload}\r\n"
    ser.write(cmd.encode())
    time.sleep(0.1)
    ser.read(ser.in_waiting)


def parse_data_payload(payload: str) -> dict | None:
    """
    Parse  D,<node_id>,<seq>,<temp_i>,<hum_i>,<press_i>,<co_i>,<co2_i>
    Returns a dict with decoded float values, or None on error.
    """
    parts = payload.split(',')
    if len(parts) != 8:
        return None
    if parts[0] != 'D':
        return None
    try:
        return {
            "node_id":     int(parts[1]),
            "seq":         int(parts[2]),
            "temperature": int(parts[3]) / 100.0,
            "humidity":    int(parts[4]) / 100.0,
            "pressure":    int(parts[5]) / 100.0,
            "co_ppm":      int(parts[6]) / 100.0,
            "co2_ppm":     int(parts[7]),           # already in ppm, no /100
        }
    except (ValueError, IndexError):
        return None


def parse_rcv(line: str) -> tuple[str, int, int] | None:
    """
    Parse a +RCV line from the RYLR135 module.
    Format:  +RCV=<src_addr>,<len>,<payload...>,<RSSI>,<SNR>

    The payload itself contains commas, so we cannot split on a fixed count.
    RSSI and SNR are always the last two comma-separated fields; everything
    from index 2 to -2 (inclusive) is the payload.

    Example:
      +RCV=1,28,D,1,0,2253,5001,101377,0,370,-8,10
      parts = ['1','28','D','1','0','2253','5001','101377','0','370','-8','10']
      payload = 'D,1,0,2253,5001,101377,0,370'
      rssi = -8, snr = 10
    """
    line = line.strip()
    if not line.startswith("+RCV="):
        return None
    try:
        parts = line[5:].split(",")   # split on ALL commas
        # need at least: addr, len, one payload field, RSSI, SNR  → 5 parts
        if len(parts) < 5:
            return None
        # addr=parts[0], len=parts[1], payload=parts[2:-2], rssi=parts[-2], snr=parts[-1]
        payload_str = ",".join(parts[2:-2]).strip()
        rssi        = int(parts[-2].strip())
        snr         = int(parts[-1].strip())
        return payload_str, rssi, snr
    except (ValueError, IndexError) as e:
        print(f"  [parse_rcv] error: {e}")
        return None


def print_telemetry(data: dict, rssi: int, snr: int, duplicate: bool) -> None:
    tag = " [DUPLICATE - ACK only]" if duplicate else ""
    print("─" * 52)
    print(f"  Node     {data['node_id']}   seq={data['seq']}{tag}")
    print(f"  Temp     {data['temperature']:.2f} °C")
    print(f"  Humidity {data['humidity']:.2f} %RH")
    print(f"  Pressure {data['pressure']:.2f} hPa")
    print(f"  CO       {data['co_ppm']:.2f} ppm")
    print(f"  CO2      {data['co2_ppm']} ppm")
    print(f"  RSSI     {rssi} dBm   SNR {snr} dB")
    print("─" * 52)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
print(f"Opening {PORT} at {BAUD} baud...")
ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(1)

# Basic module check
ser.write(b"AT\r\n")
time.sleep(0.5)
resp = ser.read(ser.in_waiting)
print(f"Module response: {resp}")

if b"+OK" not in resp and b"AT" not in resp:
    print("✗ No response from LoRa module — check wiring / port")
    ser.close()
    raise SystemExit(1)

print("✓ Module responding")

# Configure hub (address 0)
commands = [
    "AT+BAND=915000000",
    "AT+ADDRESS=0",
    "AT+NETWORKID=3",
    "AT+PARAMETER=9,7,1,12",
    "AT+MODE=0",            # normal receive mode (always listening)
]
for cmd in commands:
    ser.write((cmd + "\r\n").encode())
    time.sleep(0.3)
    r = ser.read(ser.in_waiting).decode("utf-8", errors="ignore")
    print(f"  {cmd}  ->  {r.strip()}")

print("\nHub ready — listening for node packets...\n")

while True:
    if not ser.in_waiting:
        time.sleep(0.01)
        continue

    raw = ser.readline().decode("utf-8", errors="ignore")
    if not raw.strip():
        continue

    result = parse_rcv(raw)
    if result is None:
        # Not a +RCV line (could be +OK, unsolicited, etc.) — just log it
        print(f"[dbg] {raw.strip()}")
        continue

    payload_str, rssi, snr = result

    # Try to parse as a data packet
    data = parse_data_payload(payload_str)
    if data is None:
        # Can't parse — NACK so the node retransmits
        # We don't know the node_id reliably, so try to extract it
        parts = payload_str.split(",")
        try:
            nack_node = int(parts[1])
            nack_seq  = int(parts[2])
        except (ValueError, IndexError):
            nack_node = 0
            nack_seq  = 0
        print(f"  [NACK] bad payload: {payload_str!r}")
        send_nack(ser, nack_node, nack_seq)
        continue

    node_id = data["node_id"]
    seq     = data["seq"]

    # Alternating-bit check
    expected = node_expected_seq.get(node_id, 0)   # default: expect 0 first

    if seq == expected:
        # New packet — process it, ACK, advance expected seq
        node_expected_seq[node_id] = expected ^ 1
        print_telemetry(data, rssi, snr, duplicate=False)
        send_ack(ser, node_id, seq)
    else:
        # Duplicate (node retransmitted because it missed our previous ACK)
        # ACK again with the same seq so the node can move on, but don't
        # re-process the data.
        print_telemetry(data, rssi, snr, duplicate=True)
        send_ack(ser, node_id, seq)

ser.close()