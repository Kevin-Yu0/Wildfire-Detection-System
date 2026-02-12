import pandas as pd

# # -----------------------------
# # 1. Load CSV
# # -----------------------------
# input_csv = "fire_dataset.csv"  
# df = pd.read_csv(input_csv, parse_dates=["Date"])

# # -----------------------------
# # 2. Drop unnecessary columns
# # -----------------------------
# columns_to_drop = [
#     "Sensor_ID",
#     "experiment_number",
#     "H2_Room",
#     "PM05_Room",
#     "PM100_Room",
#     "PM10_Room",
#     "PM25_Room",
#     "PM40_Room",
#     "PM_Room_Typical_Size",
#     "PM_Total_Room",
#     "VOC_Room_RAW",
#     "anomaly_label",
#     "anomaly_scenario",
#     "scenario_label",
# ]

# df = df.drop(columns=columns_to_drop)

# # drop rows where progress_label is "Short_Cicuit"
# df = df[df["progress_label"] != "Short_Cicuit"]

# # -----------------------------
# # 3. Sort by date
# # -----------------------------
# df = df.sort_values("Date").reset_index(drop=True)

# # -----------------------------
# # 4. Remove invalid experiments
# # -----------------------------
# # Keep only rows where Valid_Experiment == 1
# df = df[df["Valid_Experiment"] == 1].reset_index(drop=True)

# # drop Valid_Experiment column now that all remaining rows are valid
# df = df.drop(columns=["Valid_Experiment"])

# # -----------------------------
# # 5. Save preprocessed CSV
# # -----------------------------
# output_csv = "preprocessed_data.csv"
# df.to_csv(output_csv, index=False)

# print(f"Preprocessing complete! Saved to {output_csv}")
# print(f"Remaining columns: {df.columns.tolist()}")
# print(f"Number of rows: {len(df)}")

# input_csv = "preprocessed_data.csv"  
# df = pd.read_csv(input_csv, parse_dates=["Date"])

# # Define a function to compute risk based on fire, nuisance, and progress_label
# # Base risk by progress_label
# base_risk_map = {
#     "Ignition": 0.3,
#     "Outgassing": 0.6,
#     "Smoldering": 0.8,
#     "Flaming": 1.0,
#     "None": 0.0
# }

# def compute_risk(row, fire_multiplier=1.2, nuisance_increment=0.3):
#     risk = base_risk_map.get(row["progress_label"], 0.0)

#     # Increase if fire detected
#     if row["fire"] == 1.0:
#         risk *= fire_multiplier

#     # Add nuisance contribution
#     if row["nuisance"] == 1.0:
#         risk = max(nuisance_increment, risk)  # Ensure nuisance adds at least the increment

#     # Cap at 1.0
#     return min(risk, 1.0)


# # Apply the function to create the new 'risk' column
# df["Risk"] = df.apply(compute_risk, axis=1)

# # Optional: check the distribution of risk values
# print(df["Risk"].value_counts())

# # Save to new CSV
# df.to_csv("risk_data.csv", index=False)
# print("Saved CSV with 'risk' column!")

# import matplotlib.pyplot as plt

# # Risk values and counts
# risk_values = [0.00, 0.80, 0.30, 0.96, 1.00, 0.36]
# counts = [162480, 49285, 16170, 11979, 2428, 115]

# # Plot
# plt.figure(figsize=(8,5))
# plt.bar(risk_values, counts, color='skyblue', width=0.05)
# plt.xlabel('Risk')
# plt.ylabel('Count')
# plt.title('Distribution of Risk Values')
# plt.xticks(risk_values)  # show all risk values on x-axis
# plt.show()

# input_csv = "risk_data.csv"  
# df = pd.read_csv(input_csv, parse_dates=["Date"])

# # here, we combine all three of these columns into one risk column, so we can drop them after creating the risk column
# columns_to_drop = [
#     "progress_label",
#     "fire",
#     "nuisance",
# ]

# df = df.drop(columns=columns_to_drop)

# # convert Date column to datetime if not already in datetime format
# df["Date"] = pd.to_datetime(df["Date"])

# # add pressure column, which is unused
# df["Pressure_Room"] = 1000

# # reorder columns to have Date first, then features, then risk
# df = df[["Temperature_Room", "Humidity_Room", "Pressure_Room", "CO_Room", "CO2_Room",  "Risk", "Date"]]


# df.to_csv("final_data_with_time.csv", index=False)

# df = df[["Temperature_Room", "Humidity_Room", "Pressure_Room", "CO_Room", "CO2_Room",  "Risk"]]

# df.to_csv("final_data.csv", index=False)

# print("Saved final data!")
