"""
Sammenligner Levine PhenoAge mot en egen ML-modell (Random Forest)
pa faktisk dodelighetsprediksjon (NHANES 2015-2016 + mortalitetskobling).

Evalueringsmetode: 5-fold kryssvalidering, AUC (C-statistikk) som malestokk.
AUC = 0.5 betyr "ikke bedre enn myntkast", AUC = 1.0 betyr perfekt skille.

Kjor: python compare_mortality_models.py
Krever: pip install scikit-learn
"""

import sqlite3
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score

DB_PATH = "nhanes_mortality.db"


def main():
    conn = sqlite3.connect(DB_PATH)

    # Hent biomarkorer (features) + phenotypic_age (Levine sin skar) + mortstat (malet)
    rows = conn.execute("""
        SELECT
            i.age, i.gender, i.albumin, i.creatinine, i.alk_phosphatase,
            i.glucose, i.crp, i.lymphocyte_pct, i.mcv, i.rdw, i.wbc,
            r.phenotypic_age, r.mortstat
        FROM phenoage_mortality_input i
        JOIN phenoage_mortality_results r ON i.SEQN = r.SEQN
        WHERE i.age >= 18
          AND i.albumin IS NOT NULL AND i.creatinine IS NOT NULL
          AND i.alk_phosphatase IS NOT NULL AND i.glucose IS NOT NULL
          AND i.crp IS NOT NULL AND i.crp > 0
          AND i.lymphocyte_pct IS NOT NULL AND i.mcv IS NOT NULL
          AND i.rdw IS NOT NULL AND i.wbc IS NOT NULL
    """).fetchall()

    conn.close()

    data = np.array(rows, dtype=float)
    # Kolonner: 0=age,1=gender,2=albumin,3=creatinine,4=alk_phos,5=glucose,
    #           6=crp,7=lymph,8=mcv,9=rdw,10=wbc,11=phenotypic_age,12=mortstat

    X = data[:, 0:11]              # de 9 biomarkorene + alder + kjonn
    phenoage_score = data[:, 11]   # Levine sin skar (brukes som prediktor)
    y = data[:, 12].astype(int)    # 0 = levde, 1 = dode

    n = len(y)
    deaths = y.sum()
    print(f"Datasett: {n} deltakere, {deaths} dodsfall ({100*deaths/n:.1f}%)")

    # --- Levine PhenoAge som prediktor ---
    # Hoyere phenotypic_age -> hoyere antatt dodelighetsrisiko, sa vi bruker den direkte
    auc_phenoage = roc_auc_score(y, phenoage_score)

    # --- ML-modell: Random Forest med kryssvalidert prediksjon ---
    # StratifiedKFold sikrer at hver fold far en fornuftig andel dodsfall,
    # viktig siden bare ~4% dode
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=5,           # begrenset dybde for a unnga overtilpasning pa lite datasett
        min_samples_leaf=10,
        class_weight="balanced",  # kompenserer for at dodsfall er sjeldne
        random_state=42
    )

    # cross_val_predict gir "out-of-fold" prediksjoner - modellen ser aldri
    # testdataene under trening, sa dette er en aerlig sammenligning
    proba_rf = cross_val_predict(model, X, y, cv=skf, method="predict_proba")[:, 1]
    auc_rf = roc_auc_score(y, proba_rf)

    # --- ML-modell nr. 2: Gradient Boosting ---
    # Bygger trer sekvensielt, hvert nytt tre retter opp feilene fra de forrige.
    # Ofte litt sterkere enn Random Forest pa denne typen tabelldata (samme
    # familie som XGBoost, men innebygd i scikit-learn - ingen ekstra installasjon)
    gbm = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=3,           # gradient boosting trenger typisk grunnere trer enn RF
        learning_rate=0.05,    # lav lasrate + flere trer = mer robust mot overtilpasning
        min_samples_leaf=10,
        random_state=42
    )
    proba_gbm = cross_val_predict(gbm, X, y, cv=skf, method="predict_proba")[:, 1]
    auc_gbm = roc_auc_score(y, proba_gbm)

    print(f"\n{'Metode':<30}{'AUC (C-statistikk)':>20}")
    print("-" * 50)
    print(f"{'Levine PhenoAge':<30}{auc_phenoage:>20.4f}")
    print(f"{'Random Forest (egen modell)':<30}{auc_rf:>20.4f}")
    print(f"{'Gradient Boosting (egen modell)':<30}{auc_gbm:>20.4f}")

    best_ml_name = "Gradient Boosting" if auc_gbm > auc_rf else "Random Forest"
    best_ml_auc = max(auc_gbm, auc_rf)
    diff = best_ml_auc - auc_phenoage
    print(f"\nBeste egen modell: {best_ml_name} (AUC={best_ml_auc:.4f})")
    print(f"Differanse mot PhenoAge: {diff:+.4f}")
    if abs(diff) < 0.02:
        print("-> Praktisk sett likeverdige (differanse innenfor typisk stoy for dette datasettet)")
    elif diff > 0:
        print("-> Egen modell presterer bedre pa denne mortalitetsprediksjonen")
    else:
        print("-> Levine PhenoAge presterer bedre - ikke uventet, siden formelen er spesifikt kalibrert for dodelighet")

    # Feature importance - hvilke biomarkorer driver GBM-modellens beslutninger
    gbm.fit(X, y)
    feature_names = ["age", "gender", "albumin", "creatinine", "alk_phosphatase",
                      "glucose", "crp", "lymphocyte_pct", "mcv", "rdw", "wbc"]
    importances = gbm.feature_importances_
    print(f"\n{'Biomarkor (Gradient Boosting)':<30}{'Viktighet':>12}")
    print("-" * 42)
    for name, imp in sorted(zip(feature_names, importances), key=lambda x: -x[1]):
        print(f"{name:<30}{imp:>12.4f}")


if __name__ == "__main__":
    main()
