"""
Compares Levine PhenoAge against self-built ML models
(Random Forest and Gradient Boosting) on actual mortality prediction
(NHANES 2015-2016 + mortality linkage).

Evaluation method: 5-fold cross-validation, AUC (C-statistic) as the metric.
AUC = 0.5 means "no better than a coin flip", AUC = 1.0 means perfect discrimination.

Run: python compare_mortality_models.py
Requires: pip install scikit-learn
"""

import sqlite3
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score

DB_PATH = "nhanes_mortality.db"


def main():
    conn = sqlite3.connect(DB_PATH)

    # Fetch biomarkers (features) + phenotypic_age (Levine's score) + mortstat (target)
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
    # Columns: 0=age,1=gender,2=albumin,3=creatinine,4=alk_phos,5=glucose,
    #          6=crp,7=lymph,8=mcv,9=rdw,10=wbc,11=phenotypic_age,12=mortstat

    X = data[:, 0:11]              # the 9 biomarkers + age + gender
    phenoage_score = data[:, 11]   # Levine's score (used directly as predictor)
    y = data[:, 12].astype(int)    # 0 = alive, 1 = deceased

    n = len(y)
    deaths = y.sum()
    print(f"Dataset: {n} participants, {deaths} deaths ({100*deaths/n:.1f}%)")

    # --- Levine PhenoAge as predictor ---
    # Higher phenotypic_age -> assumed higher mortality risk, so we use it directly
    auc_phenoage = roc_auc_score(y, phenoage_score)

    # --- ML model 1: Random Forest with cross-validated prediction ---
    # StratifiedKFold ensures each fold gets a reasonable share of deaths,
    # important since only ~4% of participants died
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=5,           # limited depth to avoid overfitting on a small dataset
        min_samples_leaf=10,
        class_weight="balanced",  # compensates for deaths being rare
        random_state=42
    )

    # cross_val_predict gives "out-of-fold" predictions - the model never
    # sees the test data during training, so this is an honest comparison
    proba_rf = cross_val_predict(model, X, y, cv=skf, method="predict_proba")[:, 1]
    auc_rf = roc_auc_score(y, proba_rf)

    # --- ML model 2: Gradient Boosting ---
    # Builds trees sequentially, each new tree correcting the previous tree's errors.
    # Often slightly stronger than Random Forest on this kind of tabular data (same
    # family as XGBoost, but built into scikit-learn - no extra installation needed)
    gbm = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=3,           # gradient boosting typically needs shallower trees than RF
        learning_rate=0.05,    # low learning rate + more trees = more robust against overfitting
        min_samples_leaf=10,
        random_state=42
    )
    proba_gbm = cross_val_predict(gbm, X, y, cv=skf, method="predict_proba")[:, 1]
    auc_gbm = roc_auc_score(y, proba_gbm)

    print(f"\n{'Method':<30}{'AUC (C-statistic)':>20}")
    print("-" * 50)
    print(f"{'Levine PhenoAge':<30}{auc_phenoage:>20.4f}")
    print(f"{'Random Forest (this project)':<30}{auc_rf:>20.4f}")
    print(f"{'Gradient Boosting (this project)':<30}{auc_gbm:>20.4f}")

    best_ml_name = "Gradient Boosting" if auc_gbm > auc_rf else "Random Forest"
    best_ml_auc = max(auc_gbm, auc_rf)
    diff = best_ml_auc - auc_phenoage
    print(f"\nBest own model: {best_ml_name} (AUC={best_ml_auc:.4f})")
    print(f"Difference vs. PhenoAge: {diff:+.4f}")
    if abs(diff) < 0.02:
        print("-> Practically equivalent (difference within typical noise for this dataset)")
    elif diff > 0:
        print("-> Own model performs better on this mortality prediction task")
    else:
        print("-> Levine PhenoAge performs better - not unexpected, since the formula is specifically calibrated for mortality")

    # Feature importance - which biomarkers drive the GBM model's decisions
    gbm.fit(X, y)
    feature_names = ["age", "gender", "albumin", "creatinine", "alk_phosphatase",
                      "glucose", "crp", "lymphocyte_pct", "mcv", "rdw", "wbc"]
    importances = gbm.feature_importances_
    print(f"\n{'Biomarker (Gradient Boosting)':<30}{'Importance':>12}")
    print("-" * 42)
    for name, imp in sorted(zip(feature_names, importances), key=lambda x: -x[1]):
        print(f"{name:<30}{imp:>12.4f}")


if __name__ == "__main__":
    main()
