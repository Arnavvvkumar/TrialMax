import chalkcompute
client = chalkcompute.DatasetClient()
revision = client.upload("nsclc-trials", ["nsclc_trials.parquet"])
print(revision)