"""
NHANES 2015-2016 Downloader + Mortality Linkage
For: Biological Age Predictor - ML vs. Levine PhenoAge on actual mortality

This script:
1. Downloads the biomarker files for the 2015-2016 cycle (same as before, but "_I" suffix)
2. Downloads the public-use mortality linkage file from NCHS (fixed-width .dat)
3. Links them together on SEQN and saves everything in a new SQLite database (nhanes_mortality.db)

Run: python nhanes_mortality_setup.py
Requires: pip install pandas requests pyreadstat
"""

import pandas as pd
import sqlite3
import os
import requests

DB_PATH = "nhanes_mortality.db"
BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2015/DataFiles/"
MORT_URL = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/datalinkage/linked_mortality/NHANES_2015_2016_MORT_2019_PUBLIC.dat"

FILES = {
    "DEMO": ("DEMO_I.xpt", "Demographics"),
    "BIOPRO": ("BIOPRO_I.xpt", "Standard Biochemistry Profile"),
    "GLU": ("GLU_I.xpt", "Fasting glucose"),
    "HSCRP": ("HSCRP_I.xpt", "High-sensitivity CRP"),
    "CBC": ("CBC_I.xpt", "Complete Blood Count"),
}

KEY_VARS = {
    "DEMO": ["SEQN", "RIDAGEYR", "RIAGENDR"],
    "BIOPRO": ["SEQN", "LBXSAL", "LBXSCR", "LBXSAPSI"],
    "GLU": ["SEQN", "LBXGLU"],
    "HSCRP": ["SEQN", "LBXHSCRP"],
    "CBC": ["SEQN", "LBXLYPCT", "LBXMCVSI", "LBXRDW", "LBXWBCSI"],
}

# Fixed-width column spec for the NCHS mortality file (standard across all cycles)
# (start, end) are 1-indexed and inclusive, as documented by NCHS
MORT_COLSPECS = [
    (0, 6),    # SEQN
    (14, 15),  # eligstat
    (15, 16),  # mortstat
    (16, 19),  # ucod_leading
    (19, 20),  # diabetes
    (20, 21),  # hyperten
    (42, 45),  # permth_int
    (45, 48),  # permth_exm
]
MORT_NAMES = ["SEQN", "eligstat", "mortstat", "ucod_leading",
              "diabetes", "hyperten", "permth_int", "permth_exm"]


def download_biomarkers(conn):
    for table_name, (filename, description) in FILES.items():
        url = BASE_URL + filename
        print(f"\n--- {table_name}: {description} ---")
        print(f"Downloading from: {url}")
        try:
            df = pd.read_sas(url, format="xport")
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        print(f"  Retrieved {len(df)} rows")
        if table_name in KEY_VARS:
            available = [c for c in KEY_VARS[table_name] if c in df.columns]
            df = df[available]

        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"  Loaded into SQLite table '{table_name}'")


def download_mortality(conn):
    print(f"\n--- MORTALITY ---")
    print(f"Downloading from: {MORT_URL}")

    local_path = "mortality_raw.dat"
    response = requests.get(MORT_URL, timeout=60)
    response.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(response.content)
    print(f"  Downloaded to {local_path}")

    df = pd.read_fwf(local_path, colspecs=MORT_COLSPECS, names=MORT_NAMES)

    # eligstat==1 means eligible for mortality linkage (adults who can actually be traced)
    df = df[df["eligstat"] == 1]

    df.to_sql("MORTALITY", conn, if_exists="replace", index=False)
    print(f"  {len(df)} participants eligible for mortality follow-up, loaded into 'MORTALITY'")

    os.remove(local_path)


def build_merged_view(conn):
    query = """
    CREATE VIEW IF NOT EXISTS phenoage_mortality_input AS
    SELECT
        d.SEQN,
        d.RIDAGEYR AS age,
        d.RIAGENDR AS gender,
        b.LBXSAL AS albumin,
        b.LBXSCR AS creatinine,
        b.LBXSAPSI AS alk_phosphatase,
        g.LBXGLU AS glucose,
        h.LBXHSCRP AS crp,
        c.LBXLYPCT AS lymphocyte_pct,
        c.LBXMCVSI AS mcv,
        c.LBXRDW AS rdw,
        c.LBXWBCSI AS wbc,
        m.mortstat,
        m.permth_exm
    FROM DEMO d
    LEFT JOIN BIOPRO b ON d.SEQN = b.SEQN
    LEFT JOIN GLU g ON d.SEQN = g.SEQN
    LEFT JOIN HSCRP h ON d.SEQN = h.SEQN
    LEFT JOIN CBC c ON d.SEQN = c.SEQN
    INNER JOIN MORTALITY m ON d.SEQN = m.SEQN;
    """
    conn.execute(query)
    conn.commit()
    print("\nView 'phenoage_mortality_input' created — biomarkers + mortality outcome linked on SEQN.")


def main():
    conn = sqlite3.connect(DB_PATH)

    download_biomarkers(conn)
    download_mortality(conn)
    build_merged_view(conn)

    cur = conn.execute("""
        SELECT COUNT(*), SUM(mortstat)
        FROM phenoage_mortality_input
        WHERE age >= 18 AND albumin IS NOT NULL
    """)
    n, deaths = cur.fetchone()
    print(f"\nDone! {n} adults with biomarker data, {int(deaths or 0)} recorded deaths during follow-up.")
    print(f"Database saved as: {os.path.abspath(DB_PATH)}")

    conn.close()


if __name__ == "__main__":
    main()
