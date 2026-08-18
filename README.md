# Biological Age Prediction: SQL, Phenotypic Age & Machine Learning on NHANES

A project on benchmarking a published biological aging clock (Levine et al. 2018 Phenotypic Age) against a self-built machine learning model, using real-world US population health data and actual mortality outcomes.

## Overview

This project asks: **can a machine learning model, trained only on raw blood biomarkers, match a peer-reviewed clinical aging formula at predicting mortality risk?**

Rather than benchmarking against a proxy (like chronological age), the model is evaluated on what actually matters. Real 3-4 year mortality outcomes from the NHANES Linked Mortality File. This is closer to how aging biomarkers are validated in the research literature.

## Data Source

- **NHANES 2015-2016** (National Health and Nutrition Examination Survey, CDC/NCHS)
- **NHANES 2019 Public-Use Linked Mortality File** — mortality follow-up through December 31, 2019, linked via the National Death Index
- Final analytic sample: **2,531 adults** with complete biomarker data, including **109 recorded deaths** during follow-up

## Methodology

### 1. Data pipeline (SQL + Python)
- Five NHANES component files (Demographics, Standard Biochemistry Profile, Fasting Glucose, High-Sensitivity CRP, Complete Blood Count) downloaded directly from CDC servers via `pandas.read_sas()`
- Mortality file (fixed-width `.dat` format) parsed and linked via participant ID (`SEQN`)
- All data loaded into a normalized SQLite database with SQL views joining biomarker and outcome data

### 2. Levine Phenotypic Age (baseline)
Implemented the Levine et al. (2018) Phenotypic Age algorithm from its published Gompertz-based mortality-risk formula, using 9 blood biomarkers plus chronological age:

albumin, creatinine, glucose, CRP, lymphocyte %, mean cell volume (MCV), red cell distribution width (RDW), alkaline phosphatase, white blood cell count

**Validation check:** participants who died during follow-up had an average biological age *7.5 years above* their chronological age (age_gap), while surviving participants averaged *1.7 years below* — confirming the formula captures a real, clinically meaningful signal in this dataset.

### 3. Machine learning models
Two ensemble models were trained on the same 9 biomarkers + age + gender to predict mortality directly, using 5-fold stratified cross-validation (to handle the ~4% death rate and avoid overfitting on out-of-fold evaluation):
- **Random Forest** — bootstrap-aggregated decision trees
- **Gradient Boosting** — sequentially-built trees, each correcting the previous tree's errors

## Results

| Method | AUC (C-statistic) |
|---|---|
| Levine Phenotypic Age | 0.859 |
| Random Forest (this project) | 0.842 |
| Gradient Boosting (this project) | 0.801 |

Both ML models substantially outperform chance (AUC 0.5) and fall in a range considered strong for population-level mortality prediction. Random Forest, trained with no prior knowledge of clinical risk thresholds or formula structure, essentially matched a peer-reviewed, expert-calibrated algorithm.

**Random Forest outperformed Gradient Boosting on this dataset** — a notable and instructive finding rather than a limitation. With only 109 deaths across the sample, Gradient Boosting's sequential error-correction is more prone to overfitting to noise in the minority class, while Random Forest's bagging and feature-subsampling make it more robust on small, imbalanced datasets. This is a well-documented pattern in the machine learning literature: gradient boosting tends to excel on larger datasets, while random forests are often more robust when positive cases are scarce.

**Feature importance (Random Forest):** age (40%), creatinine (15%), RDW (12%), lymphocyte % (8%) were the strongest predictors — consistent with independent findings in the aging biomarker literature.

## Honest limitations

- Sample size for the ML model is modest (109 deaths); results should be interpreted as a proof of concept, not a clinically validated tool
- No claim is made that the ML model "beats" Phenotypic Age — it matches it, which is itself a meaningful finding given the formula's decades of clinical validation
- NHANES mortality linkage files are not yet available for the most recent (2017-March 2020) survey cycle, which is why this analysis uses the 2015-2016 cycle instead

## Tech stack

- **SQL** (SQLite): data modeling, joins, aggregate exploration
- **Python**: `pandas` (data wrangling), `scikit-learn` (Random Forest, cross-validation, AUC), `math` (Phenotypic Age formula implementation)
- **Data source**: CDC NHANES public-use files, NCHS Public-Use Linked Mortality File

## Future work

- Extend to the 2017-March 2020 cycle once mortality linkage data becomes available
- Try XGBoost with regularization tuning to see if it can overcome the overfitting seen with scikit-learn's Gradient Boosting on this small, imbalanced sample
- Explore a multi-omics approach incorporating epigenetic clock data, following Moqri et al. (2026)

  ## Sources and data collection:
- https://wwwn.cdc.gov/nchs/nhanes/search/datapage.aspx?Component=Laboratory&CycleBeginYear=2015 
