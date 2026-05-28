import os
import joblib
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# -----------------------------
# 1. Load credentials
# -----------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# 2. Load trained Gradient Boosting model
# -----------------------------
model = joblib.load("fire_risk_model_no_time.pkl")  # no time-based features

# -----------------------------
# 3. Fetch all data from Supabase
# -----------------------------
TABLE_NAME = "Wildfire_Sensor_Data"

response = (
    supabase.table(TABLE_NAME)
    .select("*")
    .execute()
)

df = pd.DataFrame(response.data)
print("Total rows fetched:", len(df))

# -----------------------------
# 4. Rename columns to match model
# -----------------------------
df = df.rename(columns={
    "Temperature": "temperature",
    "Humidity": "humidity",
    "Pressure": "pressure",
    "CO": "co_ppm",
    "CO2": "co2_ppm",
    "Timestamp": "timestamp",
    "timestamp": "timestamp"
})

# -----------------------------
# 5. Clean data
# -----------------------------
df = df[
    (df["temperature"] > 0) &
    (df["humidity"] > 0) &
    (df["pressure"] > 0) &
    (df["co_ppm"] >= 0) &
    (df["co2_ppm"] > 0) &
    (df["co2_ppm"] <= 1000)
].copy()

df = df.dropna(subset=["temperature", "humidity", "pressure", "co_ppm", "co2_ppm"])
print("Rows after cleaning:", len(df))

# -----------------------------
# 6. Select model features
# -----------------------------
FEATURE_COLUMNS = ["temperature", "humidity", "pressure", "co_ppm", "co2_ppm"]
X = df[FEATURE_COLUMNS]

# -----------------------------
# 7. Predict fire risk
# -----------------------------
df["Predicted_Fire_Risk"] = model.predict(X)
df["Predicted_Fire_Risk"] = df["Predicted_Fire_Risk"].clip(0, 1)

# -----------------------------
# 8. Save results locally
# -----------------------------
output_file = "supabase_fire_predictions_all.csv"
df.to_csv(output_file, index=False)
print(f"Saved predictions for all data: {output_file}")

# -----------------------------
# 9. Optional: preview
# -----------------------------
print(df[FEATURE_COLUMNS + ["Predicted_Fire_Risk"]].head())