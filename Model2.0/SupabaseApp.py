import os
import joblib
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# -----------------------------
# 1. Load credentials
# -----------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://yzankkkdstzranyazqgt.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl6YW5ra2tkc3R6cmFueWF6cWd0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc5OTAyODcsImV4cCI6MjA4MzU2NjI4N30.V2aPUOi-M3BVslS_nwA85ktDQY4SoDV1tkMXm1QMZV0")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# 2. Load trained model
# -----------------------------
model = joblib.load("fire_risk_model_v2.pkl")

# -----------------------------
# 3. Fetch data from Supabase
# -----------------------------
TABLE_NAME = "Wildfire_Sensor_Data"

response = (
    supabase.table(TABLE_NAME)
    .select("*")
    .execute()
)

df = pd.DataFrame(response.data)

print("Original rows:", len(df))

# -----------------------------
# 4. Clean data
# -----------------------------

# Drop rows where CO2 is 0 or over 1500, and where Temperature, Humidity, or Pressure are 0 or negative
df = df[
    (df["CO2"] > 0) &
    (df["CO2"] <= 1500) &
    (df["Temperature"] > 0) &
    (df["Humidity"] > 0) &
    (df["Pressure"] > 0)
].copy()

print("Rows after CO2 filtering:", len(df))

# Drop rows with missing required sensor values
df = df.dropna(subset=["Temperature", "Humidity", "Pressure", "CO", "CO2"])

# -----------------------------
# 5. Prepare model features
# -----------------------------
X = pd.DataFrame({
    "temperature": df["Temperature"],
    "humidity": df["Humidity"],
    "pressure": df["Pressure"],
    "co_ppm": df["CO"],
    "co2_ppm": df["CO2"],
})

# -----------------------------
# 6. Predict fire risk
# -----------------------------
df["Predicted_Fire"] = model.predict(X)

# Keep prediction between 0 and 1
df["Predicted_Fire"] = df["Predicted_Fire"].clip(0, 1)

# -----------------------------
# 7. Save as new file
# -----------------------------
output_file = "supabase_fire_predictions_filtered.csv"
df.to_csv(output_file, index=False)

print(f"Saved file: {output_file}")

print(df[[
    "Temperature",
    "Humidity",
    "Pressure",
    "CO",
    "CO2",
    "Predicted_Fire"
]].head())