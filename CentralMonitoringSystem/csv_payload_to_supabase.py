import os
import random
import requests
from datetime import datetime, timezone, timedelta

#required environment variables:
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

TABLE = "Wildfire_Sensor_Data"

# standardized CSV payload format
# Long,Lat,Temperature,Humidity,Pressure,CO,CO2,Timestamp,Fire

def random_time_str() -> str:
    """generate a random HH:MM:SS string"""
    h = random.randint(0, 23)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    return f"{h:02d}:{m:02d}:{s:02d}"

def make_unique_created_at(i: int) -> str:
    """generate a unique timestamptz for each row...primary key safety"""
    t = datetime.now(timezone.utc) + timedelta(microseconds=i)
    return t.isoformat()

def make_mock_payload_csv() -> str:
    """
    create 1 standardized CSV payload string in the exact agreed order:
    Long,Lat,Temperature,Humidity,Pressure,CO,CO2,Timestamp,Fire
    """
    #UCSB coordinates
    lon = random.uniform(-119.95, -119.70)
    lat = random.uniform(34.35, 34.55)

    temperature = random.uniform(10.0, 45.0)
    humidity = random.uniform(5.0, 90.0)
    pressure = random.uniform(980.0, 1035.0)
    co = random.uniform(0.0, 50.0)
    co2 = random.uniform(350.0, 2000.0)

    #fire heuristic (just mock logic for now)
    fire = "true" if (temperature > 38 and humidity < 20 and co > 20) else "false"
    timestamp = random_time_str()

    # IMPORTANT: exact order, no commas inside values
    return (
        f"{lon:.6f},"
        f"{lat:.6f},"
        f"{temperature:.2f},"
        f"{humidity:.2f},"
        f"{pressure:.2f},"
        f"{co:.2f},"
        f"{co2:.2f},"
        f"{timestamp},"
        f"{fire}"
    )

def row_from_payload_csv(payload: str, created_at: str) -> dict:
    """
    parse the standardized CSV payload and map directly into the Supabase row schema.
    """
    parts = [p.strip() for p in payload.split(",")]
    if len(parts) != 9:
        raise ValueError(f"Expected 9 CSV fields, got {len(parts)}: {payload}")

    lon = float(parts[0])
    lat = float(parts[1])
    temperature = float(parts[2])
    humidity = float(parts[3])
    pressure = float(parts[4])
    co = float(parts[5])
    co2 = float(parts[6])
    timestamp = parts[7]
    fire = parts[8].lower()

    if fire not in ("true", "false"):
        raise ValueError(f"Fire must be 'true' or 'false', got: {parts[8]}")

    return {
        "created_at": created_at,   # PRIMARY KEY in your table
        "Long": lon,
        "Lat": lat,
        "Temperature": temperature,
        "Humidity": humidity,
        "Pressure": pressure,
        "CO": co,
        "CO2": co2,
        "Timestamp": timestamp,
        "Fire": fire,
    }

def insert_rows(rows: list[dict]) -> list[dict]:
    """Insert a list of rows into Supabase using PostgREST (JSON body)."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    response = requests.post(url, headers=headers, json=rows, timeout=15)
    if not response.ok:
        raise RuntimeError(f"Insert failed ({response.status_code}): {response.text}")

    return response.json()

if __name__ == "__main__":
    NUM_ROWS = 25

    #step 1: generate mock CSV payloads in the standardized format
    payloads = [make_mock_payload_csv() for _ in range(NUM_ROWS)]

    #step 2: parse those payloads into row dicts matching Supabase schema
    rows = [row_from_payload_csv(payloads[i], make_unique_created_at(i)) for i in range(NUM_ROWS)]

    #step 3: insert into Supabase
    inserted = insert_rows(rows)

    print(f"Inserted {len(inserted)} rows into {TABLE}")

    print("\nStandardized CSV payload format:")
    print("Long,Lat,Temperature,Humidity,Pressure,CO,CO2,Timestamp,Fire")

    print("\nExample CSV payload that produced row 0:")
    print(payloads[0])

    print("\nExample inserted row 0:")
    print(inserted[0])

