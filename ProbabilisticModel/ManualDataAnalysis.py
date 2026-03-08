"""ManualDataAnalysis.py

Simple script for pulling data from Supabase so you can play with it interactively.

This file lives alongside your probabilistic model code; it is intentionally minimal and
re‑uses the same REST pattern from `CentralMonitoringSystem/lora_to_supabase.py`.

Usage:
    set SUPABASE_URL=<your url>
    set SUPABASE_KEY=<your anon/service key>
    python ManualDataAnalysis.py

Optional environment variable:
    TABLE_NAME (defaults to "Wildfire_Sensor_Data")

The script will fetch *all* rows from the table and dump a small sample to stdout.
"""

import os
import requests
from typing import Any, Dict, List

# configuration --------------------------------------------------------------
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
TABLE = os.environ.get("TABLE_NAME", "Wildfire_Sensor_Data")

SESSION = requests.Session()
SESSION.headers.update({
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
})


def supabase_fetch_all() -> List[Dict[str, Any]]:
    """Fetch every row from the Supabase table using the REST API.

    Returns a list of dictionaries representing rows.
    """

    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    # ``select=*`` asks for all columns
    resp = SESSION.get(url, params={"select": "*"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    try:
        data = supabase_fetch_all()
    except Exception as e:
        print(f"[ERROR] could not fetch data: {e}")
        raise

    print(f"Retrieved {len(data)} rows from table '{TABLE}'")
    # dump the first handful of records so you can see the shape
    for i, row in enumerate(data[:10], start=1):
        print(f"[{i}] {row}")

    # copy data into a list for downstream analysis
    all_rows = data  # alias, used by interactive sessions

    # ------------------------------------------------------------------
    # additional steps: load trained MLP model, preprocess fetched data,
    # remove unrelated columns and predict risk values for each row.
    # ------------------------------------------------------------------
    try:
        import pandas as pd
        from sklearn.pipeline import Pipeline
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        import joblib
    except ImportError as e:
        print(f"[WARN] missing package for ML evaluation: {e}")
    else:
        # convert fetched rows into DataFrame for easier manipulation
        df = pd.DataFrame(all_rows)
        print(f"DataFrame shape before cleanup: {df.shape}")

        # drop columns that are not sensor features used by the model
        drop_cols = [c for c in ['Long','Lat','Timestamp','Fire','created_at','SensorID'] if c in df.columns]
        df = df.drop(columns=drop_cols)

        print(f"DataFrame shape after dropping unrelated columns: {df.shape}")

        # rename columns to match training feature names if necessary
        rename_map = {
            'Temperature': 'Temperature_Room',
            'Humidity': 'Humidity_Room',
            'Pressure': 'Pressure_Room',
            'CO': 'CO_Room',
            'CO2': 'CO2_Room'
        }
        df = df.rename(columns=rename_map)

        # select only the features expected by the model
        features = ['Temperature_Room','Humidity_Room','Pressure_Room','CO_Room','CO2_Room']
        for f in features:
            if f not in df.columns:
                raise ValueError(f"Required feature column '{f}' missing from fetched data")

        X = df[features].copy()

        # build same preprocessing pipeline used during training
        preprocessor = Pipeline([
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler())
        ])
        # fit on the current dataset (replace with saved preprocessor if available)
        X_proc = preprocessor.fit_transform(X)

        # load the MLP model file (assumes it lives in the same folder)
        model_path = os.path.join(os.path.dirname(__file__), 'model__MLP.joblib')
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"MLP model not found at {model_path}")
        mlp = joblib.load(model_path)

        # predict risk values
        risk_values = mlp.predict(X_proc)
        print(f"Predicted {len(risk_values)} risk values")
        # show first few
        print(risk_values[:10])

        # keep risk_values available in namespace for interactive use
        risks = risk_values

        with open("predicted_risks.txt", "w") as f:
            for r in risk_values:
                f.write(f"{r}\n")

