import pandas as pd

# -----------------------------
# 1. Load dataset
# -----------------------------
df = pd.read_csv("processed_data.csv")

# Convert timestamp column
df["timestamp"] = pd.to_datetime(df["timestamp"])

# -----------------------------
# 2. Initialize fire column
# -----------------------------
df["fire"] = 0.0

# -----------------------------
# 3. Define important times
# -----------------------------
t_no_fire_end = pd.to_datetime("2026-04-24 15:29:55")

t_fire_close_start = pd.to_datetime("2026-04-24 15:30:05")
t_fire_close_end = pd.to_datetime("2026-04-24 15:37:24")

t_far_start = pd.to_datetime("2026-04-24 15:37:34")
t_far_end = pd.to_datetime("2026-04-24 15:43:23")

t_return_close = pd.to_datetime("2026-04-24 15:43:24")

# -----------------------------
# 4. Apply labels to fire column
# -----------------------------

# No fire
df.loc[
    df["timestamp"] <= t_no_fire_end,
    "fire"
] = 0.0

# Fire close to sensor
df.loc[
    (df["timestamp"] >= t_fire_close_start) &
    (df["timestamp"] <= t_fire_close_end),
    "fire"
] = 1.0

# About 5 ft away
df.loc[
    (df["timestamp"] >= t_far_start) &
    (df["timestamp"] <= t_far_end),
    "fire"
] = 0.5

# Return close to fire
df.loc[
    df["timestamp"] >= t_return_close,
    "fire"
] = 1.0

# -----------------------------
# 5. Save processed dataset
# -----------------------------
df.to_csv("processed_data_labeled.csv", index=False)

# -----------------------------
# 6. Preview
# -----------------------------
print(df.head())

print("\nFire value counts:")
print(df["fire"].value_counts())