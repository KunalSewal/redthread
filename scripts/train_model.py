"""Train the transaction fraud model on July–October closed cases and score every transaction.

    python scripts/train_model.py

1. Validation: train on Jul–Sep, evaluate on October (a time split, like the real task).
2. Final: train on Jul–Oct, score Nov–Dec. Jul–Oct scores are out-of-fold by month so the
   history the agent sees is never scored by a model that trained on it.

Writes data/processed/txn_scores.csv (tx_id, model_score) and data/processed/model_metrics.json.
"""

import json
import logging
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from redthread import paths
from redthread.model.features import build_features, closed_case_labels, load_raw

log = logging.getLogger("train_model")

PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.04,
    "num_leaves": 255,
    "min_child_samples": 50,
    "feature_fraction": 0.4,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "max_bin": 255,
    "verbose": -1,
    "num_threads": 16,
}
MAX_ROUNDS = 3000


def fit(x: pd.DataFrame, y: pd.Series, x_val=None, y_val=None, rounds: int = MAX_ROUNDS) -> lgb.Booster:
    train = lgb.Dataset(x, y, free_raw_data=True)
    if x_val is None:
        return lgb.train(PARAMS, train, num_boost_round=rounds)
    valid = lgb.Dataset(x_val, y_val, reference=train)
    return lgb.train(
        PARAMS, train, num_boost_round=rounds, valid_sets=[valid],
        callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(200)],
    )


def metrics(y: pd.Series, p: np.ndarray, risk: pd.Series) -> dict:
    return {
        "n": int(len(y)),
        "fraud_rate": round(float(y.mean()), 4),
        "auc_model": round(roc_auc_score(y, p), 4),
        "auc_bank_risk_score": round(roc_auc_score(y, risk), 4),
        "avg_precision_model": round(average_precision_score(y, p), 4),
        "avg_precision_bank_risk_score": round(average_precision_score(y, risk), 4),
        "brier_model": round(brier_score_loss(y, p), 5),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    start = time.time()
    raw = load_raw()
    month = pd.to_datetime(raw["ts"]).dt.month.to_numpy()
    tx_ids, risk = raw["TransactionID"], raw["risk_score"]
    y = closed_case_labels(tx_ids)
    x = build_features(raw)
    del raw
    log.info("features: %d rows x %d cols", *x.shape)

    history = month <= 10
    val_train, val_test = month <= 9, month == 10
    booster = fit(x[val_train], y[val_train], x[val_test], y[val_test])
    best_rounds = booster.best_iteration
    p_val = booster.predict(x[val_test], num_iteration=best_rounds)
    report = {"validation_train_jul_sep_test_oct": metrics(y[val_test], p_val, risk[val_test]),
              "best_rounds": best_rounds}
    log.info("validation: %s", report["validation_train_jul_sep_test_oct"])
    importance = pd.Series(booster.feature_importance("gain"), index=x.columns).nlargest(25)
    report["top_features_by_gain"] = importance.round(0).astype(int).to_dict()

    final_rounds = int(best_rounds * 1.1)
    scores = np.full(len(x), np.nan)
    final = fit(x[history], y[history], rounds=final_rounds)
    scores[~history] = final.predict(x[~history])
    for m in (7, 8, 9, 10):
        fold_train, fold_test = history & (month != m), month == m
        scores[fold_test] = fit(x[fold_train], y[fold_train], rounds=final_rounds).predict(x[fold_test])
        log.info("out-of-fold scores for month %d done", m)
    report["out_of_fold_history"] = metrics(y[history], scores[history], risk[history])

    pd.DataFrame({"tx_id": tx_ids, "model_score": scores.round(4)}).to_csv(
        paths.PROCESSED / "txn_scores.csv", index=False)
    (paths.PROCESSED / "model_metrics.json").write_text(json.dumps(report, indent=2))
    log.info("done in %.0fs: %s", time.time() - start, json.dumps(report["out_of_fold_history"]))


if __name__ == "__main__":
    main()
