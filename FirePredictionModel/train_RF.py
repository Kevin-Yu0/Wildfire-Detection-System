import pandas as pd
import joblib
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.tree import plot_tree

# -----------------------------
# 1. Load dataset
# -----------------------------
df = pd.read_csv("processed_data_labeled.csv")

# -----------------------------
# 2. Clean data
# -----------------------------
df = df[
    (df["co2_ppm"] > 0) &
    (df["co2_ppm"] <= 1000) &
    (df["temperature"] > 0) &
    (df["humidity"] > 0) &
    (df["pressure"] > 0)
].copy()

df = df.dropna(subset=[
    "temperature",
    "humidity",
    "pressure",
    "co_ppm",
    "co2_ppm",
    "fire"
])

# -----------------------------
# 3. Select only 5 raw features
# -----------------------------
FEATURE_COLUMNS = [
    "temperature",
    "humidity",
    "pressure",
    "co_ppm",
    "co2_ppm"
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
# 5. Train Random Forest Regressor
# -----------------------------
model = RandomForestRegressor(
    n_estimators=300,
    max_depth=12,
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

# -----------------------------
# 6. Predict and evaluate
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
importance = pd.Series(
    model.feature_importances_,
    index=FEATURE_COLUMNS
)

print("\nFeature Importance:")
print(importance.sort_values(ascending=False))

# -----------------------------
# 8. Plot feature importance
# -----------------------------
importance_sorted = importance.sort_values(ascending=True)

plt.figure(figsize=(8, 5))
importance_sorted.plot(kind="barh")
plt.title("Random Forest Feature Importance")
plt.xlabel("Importance")
plt.ylabel("Feature")
plt.tight_layout()
plt.savefig("rf_feature_importance_no_time.png", dpi=300)
plt.show()

print("Saved diagram: rf_feature_importance_no_time.png")

# -----------------------------
# 9. Plot first 3 trees from Random Forest
# -----------------------------
NUM_TREES_TO_PLOT = 3

for i in range(NUM_TREES_TO_PLOT):
    tree = model.estimators_[i]

    plt.figure(figsize=(20, 10))
    plot_tree(
        tree,
        feature_names=FEATURE_COLUMNS,
        filled=True,
        rounded=True,
        max_depth=3,
        fontsize=8
    )

    plt.title(f"Random Forest Decision Tree {i + 1}")
    plt.tight_layout()

    filename = f"random_forest_tree_{i + 1}.png"
    plt.savefig(filename, dpi=300)
    plt.show()

    print(f"Saved tree diagram: {filename}")

# -----------------------------
# 10. Save model
# -----------------------------
joblib.dump(model, "fire_risk_model_rf_no_time.pkl")

print("\nSaved model: fire_risk_model_rf_no_time.pkl")