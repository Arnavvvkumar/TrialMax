import os, psycopg2, pandas as pd

user="aact_u12256"
password="qbBMI4AiZbB0tpwOZkFo"


conn = psycopg2.connect(host="aact-db.ctti-clinicaltrials.org", port=5432, dbname="aact",
                        user=os.environ["AACT_USER"], password=os.environ["AACT_PASS"])
df = pd.read_sql("""
  SELECT DISTINCT s.nct_id, s.brief_title, s.phase, s.overall_status, s.why_stopped,
         s.enrollment, e.criteria, e.gender, e.minimum_age, e.maximum_age
  FROM studies s
  JOIN eligibilities e ON e.nct_id = s.nct_id
  JOIN conditions c ON c.nct_id = s.nct_id
  WHERE c.downcase_name LIKE '%non-small cell lung%'
""", conn)
print(len(df), "trials")
df.to_parquet("nsclc_trials.parquet")