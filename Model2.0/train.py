import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score

# -----------------------------
# 1. Load labeled dataset
# -----------------------------
df = pd.read_csv("processed_data_labeled.csv")

# -----------------------------
# 2. Basic cleaning
# -----------------------------
df = df.dropna()

# Drop non-feature columns
df = df.drop(columns=["timestamp", "node_id"], errors="ignore")

# -----------------------------
# 3. Select features and label
# -----------------------------
FEATURE_COLUMNS = [
    "temperature",
    "humidity",
    "pressure",
    "co_ppm",
    "co2_ppm",
]

X = df[FEATURE_COLUMNS]
y = df["fire"]

# -----------------------------
# 4. Train-test split
# -----------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    shuffle=True
)

# -----------------------------
# 5. Train Random Forest model
# -----------------------------
model = RandomForestRegressor(
    n_estimators=200,
    max_depth=10,
    random_state=42
)

model.fit(X_train, y_train)

# -----------------------------
# 6. Evaluate model
# -----------------------------
y_pred = model.predict(X_test)
y_pred = y_pred.clip(0, 1)

mse = mean_squared_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)

print("MSE:", mse)
print("R2 Score:", r2)

# -----------------------------
# 7. Feature importance
# -----------------------------
importance = pd.Series(model.feature_importances_, index=FEATURE_COLUMNS)

print("\nFeature Importance:")
print(importance.sort_values(ascending=False))

# -----------------------------
# 8. Save model
# -----------------------------
joblib.dump(model, "fire_risk_model_v2.pkl")

print("\nSaved model: fire_risk_model_v2.pkl")