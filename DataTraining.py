import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score

# Load cleaned dataset
df = pd.read_csv("data_log_cleaned_labeled.csv")

# -----------------------------
# 1. Basic preprocessing
# -----------------------------

# Drop rows with missing values (or you can impute later)
df = df.dropna()

# Convert timestamp if you want (optional)
# df["timestamp"] = pd.to_datetime(df["timestamp"])

# Drop non-numeric or unnecessary columns
df = df.drop(columns=["timestamp", "node_id", "video_time_sec"], errors="ignore")

# -----------------------------
# 2. Separate features & label
# -----------------------------
X = df.drop(columns=["fire"])   # features
y = df["fire"]                  # target (0 to 1)

# -----------------------------
# 3. Train-test split
# -----------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# -----------------------------
# 4. Train Random Forest Regressor
# -----------------------------
model = RandomForestRegressor(
    n_estimators=100,
    max_depth=10,
    random_state=42
)

model.fit(X_train, y_train)

# -----------------------------
# 5. Evaluate model
# -----------------------------
y_pred = model.predict(X_test)

mse = mean_squared_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)

print("MSE:", mse)
print("R2 Score:", r2)

# -----------------------------
# 6. Feature importance (VERY useful)
# -----------------------------
importances = pd.Series(model.feature_importances_, index=X.columns)
print("\nFeature Importance:")
print(importances.sort_values(ascending=False))

# -----------------------------
# 7. Save model (for deployment on STM32 pipeline later)
# -----------------------------
import joblib
joblib.dump(model, "fire_risk_model.pkl")