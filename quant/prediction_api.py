#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DEFAULT_MODEL_DIR = Path(os.environ.get("PREDICTION_MODEL_DIR", "storage/app/prediction"))
MODEL_PATH = DEFAULT_MODEL_DIR / "prediction_model.joblib"
METADATA_PATH = DEFAULT_MODEL_DIR / "prediction_model_metadata.json"

app = FastAPI(title="Laravel Prediction API", version="1.0.0")


class PredictionRequest(BaseModel):
    features: dict[str, object] = Field(default_factory=dict)


class PredictionModelStore:
    def __init__(self) -> None:
        self.model = None
        self.metadata: dict[str, object] | None = None

    def load(self) -> None:
        if not MODEL_PATH.is_file() or not METADATA_PATH.is_file():
            self.model = None
            self.metadata = None
            return

        self.model = joblib.load(MODEL_PATH)
        with METADATA_PATH.open("r", encoding="utf-8") as handle:
            self.metadata = json.load(handle)

    def ensure_ready(self) -> None:
        if self.model is None or self.metadata is None:
            raise HTTPException(
                status_code=503,
                detail="Prediction model is not ready. Train a model first via quant/train_prediction_models.py.",
            )


store = PredictionModelStore()
store.load()


@app.get("/health")
def health() -> dict[str, object]:
    ready = store.model is not None and store.metadata is not None
    return {
        "status": "ok" if ready else "model_missing",
        "model_ready": ready,
        "model_path": str(MODEL_PATH),
    }


@app.post("/predict")
def predict(payload: PredictionRequest) -> dict[str, object]:
    store.ensure_ready()
    assert store.metadata is not None
    assert store.model is not None

    feature_columns = list(store.metadata["feature_columns"])
    row = {column: payload.features.get(column) for column in feature_columns}
    frame = pd.DataFrame([row], columns=feature_columns)

    predicted_direction = str(store.model.predict(frame)[0])
    probabilities = store.model.predict_proba(frame)[0]
    classes = list(store.model.classes_)
    probability_map = {label: float(probabilities[idx]) for idx, label in enumerate(classes)}
    probability = probability_map.get(predicted_direction, max(probability_map.values()))

    regime = "bullish" if payload.features.get("market_regime_bullish") else "non-bullish"
    weighted_sentiment = float(payload.features.get("weighted_sentiment_5d") or 0.0)
    basis = (
        f"Model {store.metadata['selected_model']['model_name']} memakai return_5d, return_20d, "
        f"ATR14, volume ratio, price-vs-EMA50, regime {regime}, dan weighted sentiment 5D={weighted_sentiment:.4f}."
    )

    return {
        "predicted_direction": predicted_direction,
        "probability": round(probability, 4),
        "confidence": round(probability, 4),
        "basis": basis,
        "scenario_bullish": "Jika regime bullish bertahan dan sentimen tetap mendukung, probabilitas kenaikan membaik.",
        "scenario_neutral": "Jika regime dan sentimen bercampur, prediksi cenderung kembali ke flat.",
        "scenario_bearish": "Jika regime melemah dan sentimen memburuk, probabilitas downside meningkat.",
        "model_name": store.metadata["selected_model"]["model_name"],
        "feature_columns": feature_columns,
    }
