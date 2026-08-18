"""
NHANES 2017-March 2020 Data Downloader + SQLite Loader
For: Biological Age Predictor project (Phenotypic Age benchmark)

Dette skriptet:
1. Laster ned XPT-filene direkte fra CDC sine servere
2. Konverterer dem til pandas DataFrames
3. Laster dem inn i en SQLite-database (nhanes.db)

Kjør: python nhanes_download_setup.py
Krever: pip install pandas requests
(xport-lesing støttes native i pandas via pyreadstat, evt: pip install pyreadstat)
"""

import pandas as pd
import sqlite3
import os

# --- Konfigurasjon ---

BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/"
DB_PATH = "nhanes.db"

# Filnavn -> (CDC-filnavn, beskrivelse)
FILES = {
    "DEMO": ("P_DEMO.xpt", "Demographics (alder, kjønn, sample weights)"),
    "BIOPRO": ("P_BIOPRO.xpt", "Standard Biochemistry Profile (albumin, kreatinin, alk. fosfatase)"),
    "GLU": ("P_GLU.xpt", "Fastende glukose"),
    "HSCRP": ("P_HSCRP.xpt", "High-sensitivity CRP"),
    "CBC": ("P_CBC.xpt", "Complete Blood Count (lymfocytt%, MCV, RDW, WBC)"),
}

# Nøkkelvariabler du trenger til Phenotypic Age per fil (for referanse/README)
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
        print(f"Laster ned fra: {url}")

        try:
            # pandas leser .xpt (SAS transport) direkte over HTTP
            df = pd.read_sas(url, format="xport")
        except Exception as e:
            print(f"  FEIL ved nedlasting av {filename}: {e}")
            print(f"  Sjekk om filnavnet stemmer på CDC-siden, evt last ned manuelt.")
            continue

        print(f"  Hentet {len(df)} rader, {len(df.columns)} kolonner")

        # SEQN er alltid nøkkelen som kobler tabellene sammen på tvers
        if "SEQN" not in df.columns:
            print(f"  ADVARSEL: Ingen SEQN-kolonne funnet i {filename}")

        # Behold kun nøkkelvariabler + SEQN, for å holde databasen ryddig
        # (fjern denne filtreringen hvis du vil ha ALLE kolonnene)
        if table_name in KEY_VARS:
            available = [c for c in KEY_VARS[table_name] if c in df.columns]
            missing = [c for c in KEY_VARS[table_name] if c not in df.columns]
            if missing:
                print(f"  Merk: mangler forventede kolonner: {missing}")
            df = df[available]

        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"  Lastet inn i SQLite-tabell '{table_name}'")


def build_merged_view(conn):
    """Lager en samlet view som joiner alle tabellene på SEQN,
    klar for å regne ut Phenotypic Age og age_gap."""
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
    print("\nView 'phenoage_input' opprettet — én rad per deltaker, alle 9 biomarkører + alder.")


def main():
    if os.path.exists(DB_PATH):
        print(f"Merk: {DB_PATH} finnes allerede og vil bli oppdatert (tabeller erstattes).")

    conn = sqlite3.connect(DB_PATH)

    download_and_load(conn)
    build_merged_view(conn)

    # Rask sjekk
    cur = conn.execute("SELECT COUNT(*) FROM phenoage_input WHERE albumin IS NOT NULL")
    n = cur.fetchone()[0]
    print(f"\nFerdig! {n} deltakere har minst albumin-data tilgjengelig.")
    print(f"Database lagret som: {os.path.abspath(DB_PATH)}")

    conn.close()


if __name__ == "__main__":
    main()
