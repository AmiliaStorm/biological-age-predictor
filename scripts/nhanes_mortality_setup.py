"""
NHANES 2015-2016 Downloader + Mortalitetskobling
For: Biological Age Predictor - ML vs. Levine PhenoAge pa faktisk dodelighet

Dette skriptet:
1. Laster ned biomarkor-filene for 2015-2016-syklusen (samme som for, men "_I"-suffiks)
2. Laster ned den offentlige mortalitets-koblingsfilen fra NCHS (fixed-width .dat)
3. Kobler dem sammen pa SEQN og lagrer alt i en ny SQLite-database (nhanes_mortality.db)

Kjor: python nhanes_mortality_setup.py
Krever: pip install pandas requests pyreadstat
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
    "GLU": ("GLU_I.xpt", "Fastende glukose"),
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

# Fast-bredde kolonnedefinisjon for NCHS mortalitetsfil (standard for alle sykluser)
# (start, slutt) er 1-indeksert og inklusiv, slik NCHS dokumenterer det
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
        print(f"Laster ned fra: {url}")
        try:
            df = pd.read_sas(url, format="xport")
        except Exception as e:
            print(f"  FEIL: {e}")
            continue

        print(f"  Hentet {len(df)} rader")
        if table_name in KEY_VARS:
            available = [c for c in KEY_VARS[table_name] if c in df.columns]
            df = df[available]

        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"  Lastet inn i SQLite-tabell '{table_name}'")


def download_mortality(conn):
    print(f"\n--- MORTALITET ---")
    print(f"Laster ned fra: {MORT_URL}")

    local_path = "mortality_raw.dat"
    response = requests.get(MORT_URL, timeout=60)
    response.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(response.content)
    print(f"  Lastet ned til {local_path}")

    df = pd.read_fwf(local_path, colspecs=MORT_COLSPECS, names=MORT_NAMES)

    # eligstat==1 betyr kvalifisert for mortalitetskobling (voksne som faktisk kan spores)
    df = df[df["eligstat"] == 1]

    df.to_sql("MORTALITY", conn, if_exists="replace", index=False)
    print(f"  {len(df)} deltakere kvalifisert for mortalitetsoppfolging, lastet inn i 'MORTALITY'")

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
    print("\nView 'phenoage_mortality_input' opprettet - biomarkorer + mortalitetsutfall koblet pa SEQN.")


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
    print(f"\nFerdig! {n} voksne med biomarkordata, {int(deaths or 0)} registrerte dodsfall i oppfolgingsperioden.")
    print(f"Database lagret som: {os.path.abspath(DB_PATH)}")

    conn.close()


if __name__ == "__main__":
    main()
