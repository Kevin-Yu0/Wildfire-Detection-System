import os
import joblib
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# -----------------------------
# 1. Load Supabase credentials
# -----------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# 2. Load trained model
# -----------------------------
model = joblib.load("fire_risk_model.pkl")

# -----------------------------
# 3. Fetch data from Supabase
# -----------------------------
TABLE_NAME = "Wildfire_Sensor_Data"

response = (
    supabase.table(TABLE_NAME)
    .select("*")
    .execute()
)

data = response.data

df = pd.DataFrame(data)

print("Fetched rows:", len(df))
print(df.head())

# -----------------------------
# 4. Prepare features for model
# -----------------------------
# Supabase column names:
# Temperature, Humidity, Pressure, CO, CO2

X = pd.DataFrame({
    "temperature": df["Temperature"],
    "humidity": df["Humidity"],
    "pressure": df["Pressure"],
    "co_ppm": df["CO"],
    "co2_ppm": df["CO2"],
})

# Remove rows with missing sensor values
valid_rows = X.dropna().index
X_valid = X.loc[valid_rows]

# -----------------------------
# 5. Predict fire risk
# -----------------------------
predictions = model.predict(X_valid)

# Limit prediction between 0 and 1
predictions = predictions.clip(0, 1)

# -----------------------------
# 6. Save predictions into separate file
# -----------------------------
df["Predicted_Fire"] = None
df.loc[valid_rows, "Predicted_Fire"] = predictions

df.to_csv("supabase_fire_predictions.csv", index=False)

print("Saved prediction file: supabase_fire_predictions.csv")
print(df[["Temperature", "Humidity", "Pressure", "CO", "CO2", "Predicted_Fire"]].head())