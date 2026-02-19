import joblib
import numpy as np

# -----------------------------
# Load trained model
# -----------------------------
MODEL_PATH = "fire_random_forest_model.joblib"
model = joblib.load(MODEL_PATH)

print("Fire Detection Model Loaded Successfully.\n")

# -----------------------------
# Interactive prediction loop
# -----------------------------
while True:
    try:
        print("Enter sensor values:")

        temperature = float(input("Temperature: "))
        humidity = float(input("Humidity: "))
        pressure = float(input("Pressure: "))
        co = float(input("CO: "))
        co2 = float(input("CO2: "))

        # Prepare input in correct shape [1, 5]
        features = np.array([[temperature, humidity, pressure, co, co2]])

        prediction = model.predict(features)[0]

        if hasattr(model, "predict_proba"):
            probability = model.predict_proba(features)[0][1]
            print(f"\nPrediction: {'🔥 FIRE DETECTED' if prediction == 1 else '✅ No Fire'}")
            print(f"Fire Probability: {probability:.4f}\n")
        else:
            print(f"\nPrediction: {'🔥 FIRE DETECTED' if prediction == 1 else '✅ No Fire'}\n")

    except ValueError:
        print("Invalid input. Please enter numeric values only.\n")
        continue

    # Optional exit
    again = input("Test another sample? (y/n): ").strip().lower()
    if again != "y":
        print("Exiting...")
        break
