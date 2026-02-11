import os
import numpy as np
import pandas as pd
import joblib
from supabase import create_client

from collections import Counter

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)

# -----------------------------
# Config
# -----------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://yzankkkdstzranyazqgt.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl6YW5ra2tkc3R6cmFueWF6cWd0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc5OTAyODcsImV4cCI6MjA4MzU2NjI4N30.V2aPUOi-M3BVslS_nwA85ktDQY4SoDV1tkMXm1QMZV0")
TABLE_NAME = "Wildfire_Sensor_Data"  # <-- change this

FEATURE_COLS = ["Temperature", "Humidity", "Pressure", "CO", "CO2"]
LABEL_COL = "Fire"

TEST_SIZE = 0.2
RANDOM_SEED = 42

# -----------------------------
# Connect to Supabase
# -----------------------------
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_all_rows(table: str, cols: list[str], batch_size: int = 1000) -> list[dict]:
    all_rows: list[dict] = []
    start = 0
    select_str = ",".join(cols)

    while True:
        res = (
            supabase
            .table(table)
            .select(select_str)
            .range(start, start + batch_size - 1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            break
        all_rows.extend(rows)
        start += batch_size

    return all_rows

# -----------------------------
# Import + prepare dataset
# -----------------------------
cols_to_fetch = FEATURE_COLS + [LABEL_COL]
rows = fetch_all_rows(TABLE_NAME, cols_to_fetch, batch_size=1000)
df = pd.DataFrame(rows)

if df.empty:
    raise RuntimeError("No data returned. Check TABLE_NAME, RLS policies, and your API key.")

# numeric coercion
for c in FEATURE_COLS:
    df[c] = pd.to_numeric(df[c], errors="coerce")

# label coercion (handles True/False, 0/1, 'true'/'false')
df[LABEL_COL] = (
    df[LABEL_COL]
    .astype(str)
    .str.strip()
    .str.lower()
    .map({"true": 1, "false": 0, "1": 1, "0": 0})
)

# drop missing
df = df.dropna(subset=FEATURE_COLS + [LABEL_COL]).reset_index(drop=True)
df[LABEL_COL] = df[LABEL_COL].astype(int)

# -----------------------------
# Random split: train / test
# -----------------------------
X = df[FEATURE_COLS].to_numpy()
y = df[LABEL_COL].to_numpy()

class_counts = Counter(y)
min_count = min(class_counts.values())

# Only stratify if all classes have at least 2 samples
stratify_arg = y if (len(class_counts) > 1 and min_count >= 2) else None

X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=TEST_SIZE,
    random_state=RANDOM_SEED,
    shuffle=True,
    stratify=stratify_arg
)

print("Class counts:", dict(class_counts))
print("Using stratify:", stratify_arg is not None)

# -----------------------------
# Train Random Forest
# -----------------------------
rf = RandomForestClassifier(
    n_estimators=300,
    random_state=RANDOM_SEED,
    n_jobs=-1,
    class_weight="balanced"
)

rf.fit(X_train, y_train)

# -----------------------------
# Accuracy on training set
# -----------------------------
y_train_pred = rf.predict(X_train)
train_accuracy = accuracy_score(y_train, y_train_pred)

# -----------------------------
# Accuracy on testing set
# -----------------------------
y_test_pred = rf.predict(X_test)
test_accuracy = accuracy_score(y_test, y_test_pred)

print(f"Training Accuracy: {train_accuracy:.4f}")
print(f"Testing Accuracy : {test_accuracy:.4f}")

# -----------------------------
# Save trained model
# -----------------------------
MODEL_PATH = "fire_random_forest_model.joblib"
joblib.dump(rf, MODEL_PATH)

print(f"Model saved to: {MODEL_PATH}")

# -----------------------------
# Feature importance
# -----------------------------
importances = pd.Series(rf.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
print("\nFeature importances:\n", importances)

rf = joblib.load("fire_random_forest_model.joblib")