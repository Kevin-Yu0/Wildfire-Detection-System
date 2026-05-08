import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)
import joblib
import os
import requests

# Features to use for prediction
FEATURES = ['temperature', 'humidity', 'pressure', 'co_ppm', 'co2_ppm']
TARGET = 'fire'


def load_and_combine_data():
    """Load and combine all three CSV files into one dataset."""
    dfs = []
    
    for file in ['cntrl.csv', 'close.csv', '5ft.csv']:
        if os.path.exists(file):
            df = pd.read_csv(file)
            dfs.append(df)
            print(f"Loaded {file}: {len(df)} rows")
    
    combined = pd.concat(dfs, ignore_index=True)
    print(f"\nTotal combined rows: {len(combined)}")
    return combined


def prepare_data(df):
    """Prepare data for training."""
    # Check for missing values
    print(f"\nMissing values:\n{df[FEATURES + [TARGET]].isnull().sum()}")
    
    # Drop rows with missing values in features or target
    df = df[FEATURES + [TARGET]].dropna()
    print(f"Rows after removing NaN: {len(df)}")
    
    X = df[FEATURES]
    y = df[TARGET]
    
    return X, y


def train_model(X, y):
    """Train a Gradient Boosting regression model."""
    # Split data: 70% train, 15% val, 15% test
    X_temp, X_test, y_temp, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
    X_train, X_val, y_train, y_val = train_test_split(X_temp, y_temp, test_size=0.176, random_state=42)
    
    print(f"\nTrain set: {len(X_train)}, Val set: {len(X_val)}, Test set: {len(X_test)}")
    
    # Standardize features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)
    
    # Train Gradient Boosting model
    print("\nTraining Gradient Boosting Regressor...")
    model = GradientBoostingRegressor(
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        random_state=42,
        validation_fraction=0.1,
        n_iter_no_change=10
    )
    model.fit(X_train_scaled, y_train)
    
    # Evaluate on validation set
    y_val_pred = model.predict(X_val_scaled)
    y_val_pred = np.clip(y_val_pred, 0.0, 1.0)  # Constrain to [0, 1]
    
    val_mae = mean_absolute_error(y_val, y_val_pred)
    val_rmse = np.sqrt(mean_squared_error(y_val, y_val_pred))
    val_r2 = r2_score(y_val, y_val_pred)
    
    print(f"\nValidation Results:")
    print(f"  MAE: {val_mae:.4f}")
    print(f"  RMSE: {val_rmse:.4f}")
    print(f"  R² Score: {val_r2:.4f}")
    
    # Evaluate on test set
    y_test_pred = model.predict(X_test_scaled)
    y_test_pred = np.clip(y_test_pred, 0.0, 1.0)  # Constrain to [0, 1]
    
    test_mae = mean_absolute_error(y_test, y_test_pred)
    test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
    test_r2 = r2_score(y_test, y_test_pred)
    
    print(f"\nTest Results:")
    print(f"  MAE: {test_mae:.4f}")
    print(f"  RMSE: {test_rmse:.4f}")
    print(f"  R² Score: {test_r2:.4f}")
    
    print(f"\n\nAll Test Set Predictions ({len(y_test)} samples):")
    print(f"{'Actual':<10} {'Predicted':<12} {'Error':<10}")
    print("-" * 32)
    for actual, pred in zip(y_test, y_test_pred):
        error = abs(actual - pred)
        print(f"{actual:<10.3f} {pred:<12.3f} {error:<10.3f}")

    
    # Feature importance
    print(f"\nFeature Importance:")
    for feat, imp in zip(FEATURES, model.feature_importances_):
        print(f"  {feat}: {imp:.4f}")
    
    return model, scaler


def save_model(model, scaler):
    """Save model and scaler to disk."""
    joblib.dump(model, 'fire_model.joblib')
    joblib.dump(scaler, 'fire_scaler.joblib')
    print("\nModel and scaler saved.")


def predict_fire_risk(data_dict, model=None, scaler=None):
    """
    Predict fire risk for a single data point.
    
    Args:
        data_dict: dict with keys matching FEATURES
        model: trained model (loads if None)
        scaler: fitted scaler (loads if None)
    
    Returns:
        float: fire risk between 0.0 and 1.0
    """
    if model is None:
        model = joblib.load('fire_model.joblib')
    if scaler is None:
        scaler = joblib.load('fire_scaler.joblib')
    
    # Create feature vector with named columns to match fitted scaler
    X = pd.DataFrame([data_dict], columns=FEATURES)
    X_scaled = scaler.transform(X)
    
    risk = model.predict(X_scaled)[0]
    risk = np.clip(risk, 0.0, 1.0)  # Ensure in [0, 1]
    
    return risk


SUPABASE_TABLE = 'Wildfire_Sensor_Data'
SUPABASE_BATCH_SIZE = 1000


def get_supabase_credentials():
    """Load Supabase connection information from environment variables."""
    url = os.environ['SUPABASE_URL'].rstrip('/')
    key = os.environ['SUPABASE_KEY']
    return url, key


def fetch_supabase_rows(table: str = SUPABASE_TABLE, batch_size: int = SUPABASE_BATCH_SIZE) -> list[dict]:
    """Fetch all rows from a Supabase table using pagination."""
    url, key = get_supabase_credentials()
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }
    rows = []
    offset = 0

    while True:
        params = {
            'select': '*',
            'limit': batch_size,
            'offset': offset,
        }
        response = requests.get(f'{url}/rest/v1/{table}', headers=headers, params=params, timeout=30)
        if not response.ok:
            raise RuntimeError(f'Supabase query failed ({response.status_code}): {response.text}')

        batch = response.json()
        if not batch:
            break

        rows.extend(batch)
        offset += len(batch)
        if len(batch) < batch_size:
            break

    return rows


def supabase_row_to_features(row: dict) -> dict:
    """Convert a Supabase row into the feature dict needed by the model."""
    return {
        'temperature': float(row.get('Temperature') if row.get('Temperature') is not None else row.get('temperature', 0.0)),
        'humidity': float(row.get('Humidity') if row.get('Humidity') is not None else row.get('humidity', 0.0)),
        'pressure': float(row.get('Pressure') if row.get('Pressure') is not None else row.get('pressure', 0.0)),
        'co_ppm': float(row.get('CO') if row.get('CO') is not None else row.get('co', 0.0)),
        'co2_ppm': float(row.get('CO2') if row.get('CO2') is not None else row.get('co2', 0.0)),
    }


def parse_fire_label(row: dict) -> int | None:
    """Parse the Supabase fire label into a binary value, if available."""
    value = row.get('Fire') if row.get('Fire') is not None else row.get('fire')
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in ('true', 't', '1', 'yes', 'y'):
        return 1
    if text in ('false', 'f', '0', 'no', 'n'):
        return 0
    raise ValueError(f"Invalid fire label: {value}")


def predict_supabase_report(model=None, scaler=None, table: str = SUPABASE_TABLE, threshold: float = 0.5) -> None:
    """Fetch Supabase rows, score them, and print a performance report."""
    if model is None:
        model = joblib.load('fire_model.joblib')
    if scaler is None:
        scaler = joblib.load('fire_scaler.joblib')

    rows = fetch_supabase_rows(table)
    print(f'Fetched {len(rows)} rows from Supabase table "{table}"')

    actuals = []
    predictions = []
    predicted_labels = []
    report_rows = []

    for index, row in enumerate(rows, start=1):
        try:
            features = supabase_row_to_features(row)
        except (TypeError, ValueError) as exc:
            print(f'Row {index}: skipping invalid features: {exc}')
            continue

        risk = predict_fire_risk(features, model, scaler)
        identifier = row.get('created_at') or row.get('Timestamp') or row.get('id') or str(index)
        label = None
        try:
            label = parse_fire_label(row)
        except ValueError as exc:
            print(f'Row {index}: invalid fire label, skipping label metrics: {exc}')

        status = f'id={identifier} | risk={risk:.4f} | data={features}'
        if label is not None:
            status += f' | actual={label}'
            actuals.append(label)
            predictions.append(risk)
            predicted_labels.append(int(risk >= threshold))
        print(f'{index:04d} | {status}')

    if not actuals:
        print('\nNo valid actual fire labels found in Supabase rows, report cannot be generated.')
        return

    actuals = np.array(actuals)
    predictions = np.array(predictions)
    predicted_labels = np.array(predicted_labels)

    mae = mean_absolute_error(actuals, predictions)
    rmse = np.sqrt(mean_squared_error(actuals, predictions))
    r2 = r2_score(actuals, predictions)
    accuracy = accuracy_score(actuals, predicted_labels)
    precision = precision_score(actuals, predicted_labels, zero_division=0)
    recall = recall_score(actuals, predicted_labels, zero_division=0)
    f1 = f1_score(actuals, predicted_labels, zero_division=0)
    cm = confusion_matrix(actuals, predicted_labels)

    print('\nSupabase Test Report')
    print('-------------------')
    print(f'Total rows scored: {len(rows)}')
    print(f'Rows with valid labels: {len(actuals)}')
    print(f'Positive label count: {int(actuals.sum())}')
    print(f'Negative label count: {len(actuals) - int(actuals.sum())}')
    print('\nRegression metrics:')
    print(f'  MAE: {mae:.4f}')
    print(f'  RMSE: {rmse:.4f}')
    print(f'  R²: {r2:.4f}')
    print(f'\nClassification metrics (threshold = {threshold:.2f}):')
    print(f'  Accuracy: {accuracy:.4f}')
    print(f'  Precision: {precision:.4f}')
    print(f'  Recall: {recall:.4f}')
    print(f'  F1 score: {f1:.4f}')
    print('\nConfusion matrix:')
    print(f'  TN: {cm[0,0]}  FP: {cm[0,1]}')
    print(f'  FN: {cm[1,0]}  TP: {cm[1,1]}')

    print('\nPrediction summary:')
    print(f'  Average predicted risk: {predictions.mean():.4f}')
    print(f'  Median predicted risk: {np.median(predictions):.4f}')
    print(f'  Max predicted risk: {predictions.max():.4f}')
    print(f'  Min predicted risk: {predictions.min():.4f}')


def predict_supabase_rows(model=None, scaler=None, table: str = SUPABASE_TABLE) -> None:
    """Fetch Supabase rows, run the model on each row, and print risk scores."""
    if model is None:
        model = joblib.load('fire_model.joblib')
    if scaler is None:
        scaler = joblib.load('fire_scaler.joblib')

    rows = fetch_supabase_rows(table)
    print(f'Fetched {len(rows)} rows from Supabase table "{table}"')

    for index, row in enumerate(rows, start=1):
        try:
            features = supabase_row_to_features(row)
        except (TypeError, ValueError) as exc:
            print(f'Row {index}: skipping invalid row: {exc}')
            continue

        risk = predict_fire_risk(features, model, scaler)
        identifier = row.get('created_at') or row.get('Timestamp') or row.get('id') or str(index)
        print(f'{index:04d} | id={identifier} | risk={risk:.4f} | data={features}')


if __name__ == '__main__':
    if len(os.sys.argv) > 1 and os.sys.argv[1] in ('supabase', 'predict_supabase'):
        # Use a trained model to score all Supabase rows
        if not os.path.exists('fire_model.joblib') or not os.path.exists('fire_scaler.joblib'):
            raise FileNotFoundError('fire_model.joblib or fire_scaler.joblib not found. Run `python model.py` first to train the model.')

        model = joblib.load('fire_model.joblib')
        scaler = joblib.load('fire_scaler.joblib')
        predict_supabase_rows(model, scaler)
    elif len(os.sys.argv) > 1 and os.sys.argv[1] in ('supabase_report', 'supabase-report', 'predict_supabase_report'):
        if not os.path.exists('fire_model.joblib') or not os.path.exists('fire_scaler.joblib'):
            raise FileNotFoundError('fire_model.joblib or fire_scaler.joblib not found. Run `python model.py` first to train the model.')

        model = joblib.load('fire_model.joblib')
        scaler = joblib.load('fire_scaler.joblib')
        predict_supabase_report(model, scaler)
    else:
        # Load and combine data
        df = load_and_combine_data()

        # Prepare features and target
        X, y = prepare_data(df)

        # Train model
        model, scaler = train_model(X, y)

        # Save model and scaler
        save_model(model, scaler)

        # Test prediction with an example from close.csv (fire scenario)
        print("\n\nExample Predictions:")
        print("-" * 50)

        # Example: high CO scenario (close.csv row)
        example_fire = {
            'temperature': 26.36,
            'humidity': 46.67,
            'pressure': 1013.09,
            'co_ppm': 75.0,
            'co2_ppm': 1167.0,
        }
        risk = predict_fire_risk(example_fire, model, scaler)
        print(f"High CO scenario (close to fire): {risk:.3f}")

        # Example: low CO scenario (cntrl.csv row)
        example_normal = {
            'temperature': 26.67,
            'humidity': 41.39,
            'pressure': 1013.37,
            'co_ppm': 0.0,
            'co2_ppm': 453.0,
        }
        risk = predict_fire_risk(example_normal, model, scaler)
        print(f"Low CO scenario (normal environment): {risk:.3f}")
