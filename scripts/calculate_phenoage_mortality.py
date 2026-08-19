"""
Calculates Levine Phenotypic Age for the NHANES 2015-2016 cycle
(same validated formula as before, now on mortality-linked data).

Run: python calculate_phenoage_mortality.py
(place this file in the same folder as nhanes_mortality.db)
"""

import sqlite3
import math

DB_PATH = "nhanes_mortality.db"


def phenotypic_age(age, albumin_gdl, creatinine_mgdl, glucose_mgdl, crp_mgl,
                    lymphocyte_pct, mcv, rdw, alk_phosphatase, wbc):
    albumin_gL = albumin_gdl * 10.0
    creatinine_umolL = creatinine_mgdl * 88.4
    glucose_mmolL = glucose_mgdl / 18.0
    crp_mgdL = crp_mgl / 10.0

    if crp_mgdL <= 0:
        crp_mgdL = 0.01

    xb = (
        -19.9067
        + (-0.0336 * albumin_gL)
        + (0.0095 * creatinine_umolL)
        + (0.1953 * glucose_mmolL)
        + (0.0954 * math.log(crp_mgdL))
        + (-0.0120 * lymphocyte_pct)
        + (0.0268 * mcv)
        + (0.3306 * rdw)
        + (0.00188 * alk_phosphatase)
        + (0.0554 * wbc)
        + (0.0804 * age)
    )

    M = 1 - math.exp((-1.51714 * math.exp(xb)) / 0.0076927)
    M = min(max(M, 1e-10), 1 - 1e-10)

    pheno_age = 141.50225 + (math.log(-0.00553 * math.log(1 - M)) / 0.090165)
    return pheno_age


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT SEQN, age, gender, albumin, creatinine, alk_phosphatase,
               glucose, crp, lymphocyte_pct, mcv, rdw, wbc,
               mortstat, permth_exm
        FROM phenoage_mortality_input
        WHERE age >= 18
          AND albumin IS NOT NULL AND creatinine IS NOT NULL
          AND alk_phosphatase IS NOT NULL AND glucose IS NOT NULL
          AND crp IS NOT NULL AND crp > 0
          AND lymphocyte_pct IS NOT NULL AND mcv IS NOT NULL
          AND rdw IS NOT NULL AND wbc IS NOT NULL
    """).fetchall()

    print(f"Calculating Phenotypic Age for {len(rows)} participants...")

    results = []
    errors = 0
    for row in rows:
        (seqn, age, gender, albumin, creatinine, alk_phos, glucose, crp,
         lymph, mcv, rdw, wbc, mortstat_raw, permth_exm) = row

        # mortstat may come as text (e.g. "1" with whitespace) from the mortality file
        try:
            mortstat = int(str(mortstat_raw).strip())
        except (ValueError, TypeError):
            errors += 1
            continue

        try:
            pa = phenotypic_age(age, albumin, creatinine, glucose, crp,
                                 lymph, mcv, rdw, alk_phos, wbc)
            age_gap = pa - age
            results.append((seqn, age, gender, pa, age_gap, mortstat, permth_exm))
        except (ValueError, ZeroDivisionError):
            errors += 1
            continue

    print(f"  Done: {len(results)} calculated, {errors} failed")

    cur.execute("DROP TABLE IF EXISTS phenoage_mortality_results")
    cur.execute("""
        CREATE TABLE phenoage_mortality_results (
            SEQN REAL PRIMARY KEY,
            chronological_age REAL,
            gender REAL,
            phenotypic_age REAL,
            age_gap REAL,
            mortstat REAL,
            permth_exm REAL
        )
    """)
    cur.executemany(
        "INSERT INTO phenoage_mortality_results VALUES (?, ?, ?, ?, ?, ?, ?)",
        results
    )
    conn.commit()

    avg_gap = sum(r[4] for r in results) / len(results)
    deaths = sum(1 for r in results if r[5] == 1)
    avg_gap_dead = sum(r[4] for r in results if r[5] == 1) / max(deaths, 1)
    avg_gap_alive = sum(r[4] for r in results if r[5] == 0) / max(len(results) - deaths, 1)

    print(f"\nAverage age_gap (all): {avg_gap:.2f} years")
    print(f"Average age_gap (deceased, n={deaths}): {avg_gap_dead:.2f} years")
    print(f"Average age_gap (alive, n={len(results)-deaths}): {avg_gap_alive:.2f} years")
    print(f"\nTable 'phenoage_mortality_results' saved in {DB_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
