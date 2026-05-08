import os
import sys
from typing import List

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


# Core features and time-delta features for a time-based regression model.
DELTA_WINDOW = 5
BASE_FEATURES = ['temperature', 'humidity', 'pressure', 'co_ppm', 'co2_ppm']
FEATURES = [
    *BASE_FEATURES,
    'delta_temperature',
    'delta_humidity',
    'delta_pressure',
    'delta_co_ppm',
    'delta_co2_ppm',
    'delta_seconds',
]
TARGET = 'fire'
CSV_FILES = ['cntrl.csv', 'close.csv', '5ft.csv']
MODEL_PATH = 'fire_time_model.joblib'
SCALER_PATH = 'fire_time_scaler.joblib'


def load_csv_with_timestamp(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if 'timestamp' not in df.columns:
        raise ValueError(f'CSV file {path} must contain a timestamp column')

    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.sort_values('timestamp').reset_index(drop=True)
    return df


def add_time_delta_features(df: pd.DataFrame, delta_window: int = DELTA_WINDOW) -> pd.DataFrame:
    """Add delta and rate features derived from the previous sample in the same file."""
    required = ['timestamp', 'temperature', 'humidity', 'pressure', 'co_ppm', 'co2_ppm', TARGET]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f'Missing required columns: {missing}')

    df = df[required].copy()
    df[['temperature', 'humidity', 'pressure', 'co_ppm', 'co2_ppm']] = (
        df[['temperature', 'humidity', 'pressure', 'co_ppm', 'co2_ppm']]
        .astype(float)
    )

    df['delta_seconds'] = df['timestamp'].diff(periods=delta_window).dt.total_seconds().fillna(0.0)
    for field in BASE_FEATURES:
        df[f'delta_{field}'] = df[field].diff(periods=delta_window).fillna(0.0)

    # Keep only the features we want to train on plus the target
    return df[[*FEATURES, TARGET]].dropna()


def load_time_series_data(files: List[str] = CSV_FILES, delta_window: int = DELTA_WINDOW) -> pd.DataFrame:
    dataframes = []
    for path in files:
        if not os.path.exists(path):
            print(f'Warning: {path} not found, skipping.')
            continue

        df = load_csv_with_timestamp(path)
        df = add_time_delta_features(df, delta_window=delta_window)
        dataframes.append(df)
        print(f'Loaded {path}: {len(df)} rows after time-feature creation (delta_window={delta_window})')

    if not dataframes:
        raise FileNotFoundError('No CSV files found to load data from.')

    combined = pd.concat(dataframes, ignore_index=True)
    print(f'Total combined rows: {len(combined)}')

    return combined


def prepare_data(df: pd.DataFrame):
    print(f'Features available: {df.columns.tolist()}')
    df = df.dropna(subset=[*FEATURES, TARGET])
    print(f'Rows after dropping NaNs: {len(df)}')

    X = df[FEATURES]
    y = df[TARGET].astype(float)
    return X, y


def train_time_model(X, y, verbose: bool = True):
    X_temp, X_test, y_temp, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
    X_train, X_val, y_train, y_val = train_test_split(X_temp, y_temp, test_size=0.176, random_state=42)

    if verbose:
        print(f'Train rows: {len(X_train)}, Val rows: {len(X_val)}, Test rows: {len(X_test)}')

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    model = GradientBoostingRegressor(
        n_estimators=150,
        learning_rate=0.1,
        max_depth=5,
        random_state=42,
        validation_fraction=0.1,
        n_iter_no_change=10,
    )
    model.fit(X_train_scaled, y_train)

    def evaluate(X_data, y_true):
        y_pred = np.clip(model.predict(X_data), 0.0, 1.0)
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        r2 = r2_score(y_true, y_pred)
        return y_pred, {'mae': mae, 'rmse': rmse, 'r2': r2}

    y_val_pred, val_metrics = evaluate(X_val_scaled, y_val)
    y_test_pred, test_metrics = evaluate(X_test_scaled, y_test)

    if verbose:
        print(f'\nTrain rows: {len(X_train)}, Val rows: {len(X_val)}, Test rows: {len(X_test)}')
        print('\nValidation metrics:')
        print(f"  MAE: {val_metrics['mae']:.4f}, RMSE: {val_metrics['rmse']:.4f}, R²: {val_metrics['r2']:.4f}")
        print('\nTest metrics:')
        print(f"  MAE: {test_metrics['mae']:.4f}, RMSE: {test_metrics['rmse']:.4f}, R²: {test_metrics['r2']:.4f}")
        print('\nFeature importances:')
        for feat, imp in zip(FEATURES, model.feature_importances_):
            print(f'  {feat}: {imp:.4f}')

    metrics = {
        'val': val_metrics,
        'test': test_metrics,
    }
    return model, scaler, X_test, y_test, y_test_pred, metrics


def save_model(model, scaler):
    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f'Model saved to {MODEL_PATH} and scaler saved to {SCALER_PATH}')


def predict_fire_risk(data: dict, model=None, scaler=None):
    if model is None:
        model = joblib.load(MODEL_PATH)
    if scaler is None:
        scaler = joblib.load(SCALER_PATH)

    missing = [feat for feat in FEATURES if feat not in data]
    if missing:
        raise ValueError(f"Missing required feature(s) for prediction: {missing}")

    X = pd.DataFrame([data], columns=FEATURES)
    X_scaled = scaler.transform(X)
    score = np.clip(model.predict(X_scaled)[0], 0.0, 1.0)
    return score


def sweep_delta_windows(windows=range(1, 11)):
    results = []
    for window in windows:
        print(f'\n=== Evaluating delta_window={window} ===')
        df = load_time_series_data(delta_window=window)
        X, y = prepare_data(df)
        _, _, _, _, _, metrics = train_time_model(X, y, verbose=False)
        test_metrics = metrics['test']
        print(f"delta_window={window} -> Test MAE: {test_metrics['mae']:.4f}, RMSE: {test_metrics['rmse']:.4f}, R²: {test_metrics['r2']:.4f}")
        results.append((window, test_metrics))

    best_window, best_metrics = min(results, key=lambda x: x[1]['rmse'])
    print('\n=== Sweep Summary ===')
    for window, metrics in results:
        print(f"window={window}: MAE={metrics['mae']:.4f}, RMSE={metrics['rmse']:.4f}, R²={metrics['r2']:.4f}")
    print(f"\nBest window by RMSE: {best_window} with RMSE={best_metrics['rmse']:.4f}, MAE={best_metrics['mae']:.4f}, R²={best_metrics['r2']:.4f}")
    return best_window, best_metrics


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('sweep', 'delta_sweep'):
        sweep_delta_windows(windows=range(1, 11))
        return

    df = load_time_series_data()
    X, y = prepare_data(df)
    model, scaler, X_test, y_test, y_test_pred, metrics = train_time_model(X, y)
    save_model(model, scaler)

    print('\nSample test predictions:')
    for actual, pred in list(zip(y_test.tolist(), y_test_pred.tolist()))[:10]:
        print(f'  actual={actual:.3f}, pred={pred:.3f}, error={abs(actual - pred):.3f}')

    print('\nExample time-based prediction:')
    example = {
        'temperature': 29.16,
        'humidity': 40.09,
        'pressure': 1013.06,
        'co_ppm': 7.0,
        'co2_ppm': 701.0,
        'delta_temperature': 0.12,
        'delta_humidity': -0.35,
        'delta_pressure': -0.02,
        'delta_co_ppm': 1.0,
        'delta_co2_ppm': 5.0,
        'delta_seconds': 10.0,
    }
    print(f"  risk={predict_fire_risk(example, model, scaler):.4f}")


if __name__ == '__main__':
    main()
