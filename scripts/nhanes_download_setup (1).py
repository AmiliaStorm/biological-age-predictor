"""
NHANES 2017-March 2020 Data Downloader + SQLite Loader
For: Biological Age Predictor project (Phenotypic Age benchmark)

This script:
1. Downloads the XPT files directly from CDC's servers
2. Converts them to pandas DataFrames
3. Loads them into a SQLite database (nhanes.db)

Run: python nhanes_download_setup.py
Requires: pip install pandas requests
(XPT reading is supported natively by pandas via pyreadstat: pip install pyreadstat)
"""

import pandas as pd
import sqlite3
import os

# --- Configuration ---

BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/"
DB_PATH = "nhanes.db"

# File name -> (CDC filename, description)
FILES = {
    "DEMO": ("P_DEMO.xpt", "Demographics (age, sex, sample weights)"),
    "BIOPRO": ("P_BIOPRO.xpt", "Standard Biochemistry Profile (albumin, creatinine, alk. phosphatase)"),
    "GLU": ("P_GLU.xpt", "Fasting glucose"),
    "HSCRP": ("P_HSCRP.xpt", "High-sensitivity CRP"),
    "CBC": ("P_CBC.xpt", "Complete Blood Count (lymphocyte %, MCV, RDW, WBC)"),
}

# Key variables needed for Phenotypic Age per file (for reference/README)
KEY_VARS = {
    "DEMO": ["SEQN", "RIDAGEYR", "RIAGENDR", "WTMEC2YR", "SDMVPSU", "SDMVSTRA"],
    "BIOPRO": ["SEQN", "LBXSAL", "LBXSCR", "LBXSAPSI"],
    "GLU": ["SEQN", "LBXGLU"],
    "HSCRP": ["SEQN", "LBXHSCRP"],
    "CBC": ["SEQN", "LBXLYPCT", "LBXMCVSI", "LBXRDW", "LBXWBCSI"],
}


def download_and_load(conn):
    for table_name, (filename, description) in FILES.items():
        url = BASE_URL + filename
        print(f"\n--- {table_name}: {description} ---")
        print(f"Downloading from: {url}")

        try:
            # pandas reads .xpt (SAS transport) directly over HTTP
            df = pd.read_sas(url, format="xport")
        except Exception as e:
            print(f"  ERROR downloading {filename}: {e}")
            print(f"  Check the filename on the CDC page, or download it manually.")
            continue

        print(f"  Retrieved {len(df)} rows, {len(df.columns)} columns")

        # SEQN is always the key linking the tables together
        if "SEQN" not in df.columns:
            print(f"  WARNING: No SEQN column found in {filename}")

        # Keep only key variables + SEQN, to keep the database tidy
        # (remove this filtering if you want ALL columns)
        if table_name in KEY_VARS:
            available = [c for c in KEY_VARS[table_name] if c in df.columns]
            missing = [c for c in KEY_VARS[table_name] if c not in df.columns]
            if missing:
                print(f"  Note: missing expected columns: {missing}")
            df = df[available]

        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"  Loaded into SQLite table '{table_name}'")


def build_merged_view(conn):
    """Creates a merged view that joins all tables on SEQN,
    ready for computing Phenotypic Age and age_gap."""
    query = """
    CREATE VIEW IF NOT EXISTS phenoage_input AS
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
        c.LBXWBCSI AS wbc
    FROM DEMO d
    LEFT JOIN BIOPRO b ON d.SEQN = b.SEQN
    LEFT JOIN GLU g ON d.SEQN = g.SEQN
    LEFT JOIN HSCRP h ON d.SEQN = h.SEQN
    LEFT JOIN CBC c ON d.SEQN = c.SEQN;
    """
    conn.execute(query)
    conn.commit()
    print("\nView 'phenoage_input' created — one row per participant, all 9 biomarkers + age.")


def main():
    if os.path.exists(DB_PATH):
        print(f"Note: {DB_PATH} already exists and will be updated (tables replaced).")

    conn = sqlite3.connect(DB_PATH)

    download_and_load(conn)
    build_merged_view(conn)

    # Quick sanity check
    cur = conn.execute("SELECT COUNT(*) FROM phenoage_input WHERE albumin IS NOT NULL")
    n = cur.fetchone()[0]
    print(f"\nDone! {n} participants have at least albumin data available.")
    print(f"Database saved as: {os.path.abspath(DB_PATH)}")

    conn.close()


if __name__ == "__main__":
    main()
