Frank's New model, including labeled dataset and the model code.

data_log.csv: original dataset collected from sensor.
data_log_cleaned_labeled: preprocessed and labeled dataset.
DataProcessing.py: the code used to process data_log.csv to get data_log_cleaned_labeled.csv
DataTraining.py: the code used to train data_log_cleaned_labeled and calculate the Mean Squared Error, R^2 variance, and feature importance.
Supabase_model_testing.py: apply the model to data in supabase and get supabase_fire_predictions.csv
supabase_fire_prediction.csv: the predicted fire risks based on data from supabase.

Next Step: try to improve the data training model and apply the new model to Supabase.
