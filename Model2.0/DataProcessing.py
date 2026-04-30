import pandas as pd

# Load your dataset
df = pd.read_csv("data_log.csv")

# Drop unwanted columns
df = df.drop(columns=["seq", "rssi", "snr"], errors="ignore")

# Convert timestamp
df["timestamp"] = pd.to_datetime(df["timestamp"])

# Default label
df["fire"] = 0.0

# Important times
fire_start = pd.to_datetime("2026-04-24 15:30:05")
sensor_close_2ft = pd.to_datetime("2026-04-24 15:32:49")  # video start, sensor about 2 ft
sensor_away_10ft = pd.to_datetime("2026-04-24 15:38:04")
sensor_back_5ft = sensor_away_10ft + pd.Timedelta(minutes=1, seconds=10)
sensor_back_3ft = sensor_back_5ft + pd.Timedelta(minutes=1)

# Optional: seconds since recording start
recording_start = pd.to_datetime("2026-04-24 15:32:49")
df["video_time_sec"] = (df["timestamp"] - recording_start).dt.total_seconds()

# -------------------------------------------------
# Fire-risk labels based on distance and fire status
# -------------------------------------------------

# Before fire starts: no fire risk
df.loc[df["timestamp"] < fire_start, "fire"] = 0.0

# Fire started, but not large yet
df.loc[
    (df["timestamp"] >= fire_start) &
    (df["timestamp"] < sensor_close_2ft),
    "fire"
] = 0.4

# Sensor about 2 ft from fire: highest risk
df.loc[
    (df["timestamp"] >= sensor_close_2ft) &
    (df["timestamp"] < sensor_away_10ft),
    "fire"
] = 1.0

# Sensor moved to about 10 ft
df.loc[
    (df["timestamp"] >= sensor_away_10ft) &
    (df["timestamp"] < sensor_back_5ft),
    "fire"
] = 0.3

# Sensor moved back to about 5 ft
df.loc[
    (df["timestamp"] >= sensor_back_5ft) &
    (df["timestamp"] < sensor_back_3ft),
    "fire"
] = 0.6

# Sensor moved back to about 3 ft
df.loc[
    df["timestamp"] >= sensor_back_3ft,
    "fire"
] = 0.85

# Save labeled dataset
df.to_csv("data_log_cleaned_labeled.csv", index=False)

# Preview
print(df.head())
print(df["fire"].value_counts().sort_index())