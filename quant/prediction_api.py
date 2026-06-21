#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DEFAULT_MODEL_DIRS = [
    Path(os.environ.get("PREDICTION_MODEL_DIR", "storage/app/prediction")),
    Path("storage/app/prediction_v3"),
    Path("storage/app/prediction_v4a"),
    Path("storage/app/prediction_v2"),
]
DEFAULT_RANKING_MODEL_DIR = Path(os.environ.get("PREDICTION_RANKING_MODEL_DIR", "storage/app/prediction_v4b"))
RANKING_MODEL_VERSION = os.environ.get("PREDICTION_RANKING_MODEL_VERSION", "v5_ranking")
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")

app = FastAPI(title="Laravel Prediction API", version="1.0.0")


class PredictionRequest(BaseModel):
    features: dict[str, object] = Field(default_factory=dict)
    model_variant: str = Field(default="technical")


class RankingStockRequest(BaseModel):
    ticker: str
    features: dict[str, object] = Field(default_factory=dict)


class RankingRequest(BaseModel):
    stocks: list[RankingStockRequest] = Field(default_factory=list, min_length=2)


class PredictionModelStore:
    def __init__(self, model_dirs: list[Path]) -> None:
        self.model_dirs = model_dirs
        self.model_path: Path | None = None
        self.metadata_path: Path | None = None
        self.model = None
        self.metadata: dict[str, object] | None = None

    def load(self) -> None:
        self.model = None
        self.metadata = None
        self.model_path = None
        self.metadata_path = None

        for model_dir in self.model_dirs:
            model_path = model_dir / "prediction_model.joblib"
            metadata_path = model_dir / "prediction_model_metadata.json"
            if not model_path.is_file() or not metadata_path.is_file():
                continue

            try:
                model = joblib.load(model_path)
                with metadata_path.open("r", encoding="utf-8") as handle:
                    metadata = json.load(handle)
            except Exception:
                continue

            self.model = model
            self.metadata = metadata
            self.model_path = model_path
            self.metadata_path = metadata_path
            return

    def ensure_ready(self) -> None:
        if self.model is None or self.metadata is None:
            raise HTTPException(
                status_code=503,
                detail="Prediction model is not ready. Train a model first via quant/train_prediction_models.py.",
            )


def resolve_positive_class(classes: list[object]) -> object:
    for candidate in (1, "1", "up"):
        if candidate in classes:
            return candidate

    if len(classes) < 2:
        raise HTTPException(status_code=500, detail="Ranking model does not expose enough classes for probability scoring.")

    return classes[-1]


def normalize_direction(label: object) -> str:
    if label in (1, "1", "up"):
        return "up"
    if label in (0, "0", "non_up", "non-up"):
        return "flat"
    return str(label).lower()


def score_to_signal(score: float) -> str:
    if score >= 0.60:
        return "strong_candidate"
    if score >= 0.50:
        return "candidate"
    if score >= 0.40:
        return "neutral"
    return "avoid"


store = PredictionModelStore(DEFAULT_MODEL_DIRS)
store.load()
production_model_dir = Path(os.environ.get("PREDICTION_PRODUCTION_MODEL_DIR", "storage/app/prediction"))
production_stores = {
    "technical": PredictionModelStore([production_model_dir]),
    "technical_sentiment": PredictionModelStore([production_model_dir]),
    "bumi_technical": PredictionModelStore([production_model_dir]),
    "dewa_regime": PredictionModelStore([production_model_dir]),
    "dewa_technical": PredictionModelStore([production_model_dir]),
}
production_stores["technical"].model_path = production_model_dir / "model_technical_v6a.joblib"
production_stores["technical"].metadata_path = production_model_dir / "model_technical_v6a_metadata.json"
production_stores["technical_sentiment"].model_path = production_model_dir / "model_technical_sentiment_v6b.joblib"
production_stores["technical_sentiment"].metadata_path = production_model_dir / "model_technical_sentiment_v6b_metadata.json"
production_stores["bumi_technical"].model_path = production_model_dir / "model_bumi_technical.joblib"
production_stores["bumi_technical"].metadata_path = production_model_dir / "model_bumi_technical_metadata.json"
production_stores["dewa_regime"].model_path = production_model_dir / "model_dewa_regime.joblib"
production_stores["dewa_regime"].metadata_path = production_model_dir / "model_dewa_regime_metadata.json"
production_stores["dewa_technical"].model_path = production_model_dir / "model_dewa_technical.joblib"
production_stores["dewa_technical"].metadata_path = production_model_dir / "model_dewa_technical_metadata.json"

TICKER_SPECIFIC_VARIANTS = {
    "bumi_technical": "BUMI",
    "dewa_regime": "DEWA",
    "dewa_technical": "DEWA",
}


def load_named_store(store: PredictionModelStore) -> None:
    model_path = store.model_path
    metadata_path = store.metadata_path
    store.model = None
    store.metadata = None
    if model_path is None or metadata_path is None:
        return
    if not model_path.is_file() or not metadata_path.is_file():
        return
    try:
        store.model = joblib.load(model_path)
        with metadata_path.open("r", encoding="utf-8") as handle:
            store.metadata = json.load(handle)
    except Exception:
        store.model = None
        store.metadata = None


for production_store in production_stores.values():
    load_named_store(production_store)
ranking_store = PredictionModelStore([DEFAULT_RANKING_MODEL_DIR])
ranking_store.load()


SENTIMENT_FEATURE_COLUMNS = [
    "has_sentiment_data",
    "sentiment_average_5d",
    "weighted_sentiment_5d",
    "news_volume_5d",
    "sentiment_average_5d_x_regime",
    "weighted_sentiment_5d_x_regime",
]


def is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def sentiment_availability(features: dict[str, object]) -> tuple[bool, list[str]]:
    missing = [column for column in SENTIMENT_FEATURE_COLUMNS if is_missing(features.get(column))]
    has_flag = features.get("has_sentiment_data")
    volume = features.get("news_volume_5d")
    try:
        has_data = int(has_flag) == 1
    except (TypeError, ValueError):
        has_data = False
    try:
        has_volume = float(volume) > 0
    except (TypeError, ValueError):
        has_volume = False
    if not has_data:
        missing.append("has_sentiment_data=0")
    if not has_volume:
        missing.append("news_volume_5d<=0")
    return len(missing) == 0, sorted(set(missing))

def request_ticker(features: dict[str, object]) -> str | None:
    value = features.get("ticker") or features.get("code") or features.get("stock_code") or features.get("stock")
    if value is None:
        return None
    return str(value).upper().strip()


@app.get("/health")
def health() -> dict[str, object]:
    ready = store.model is not None and store.metadata is not None
    ranking_ready = ranking_store.model is not None and ranking_store.metadata is not None
    production_ready = {
        variant: production_store.model is not None and production_store.metadata is not None
        for variant, production_store in production_stores.items()
    }
    return {
        "status": "ok" if ready else "model_missing",
        "model_ready": ready,
        "model_path": str(store.model_path) if store.model_path else None,
        "production_models_ready": production_ready,
        "production_model_paths": {
            variant: str(production_store.model_path) if production_store.model_path else None
            for variant, production_store in production_stores.items()
        },
        "ranking_model_ready": ranking_ready,
        "ranking_model_path": str(ranking_store.model_path) if ranking_store.model_path else None,
    }


@app.post("/predict")
def predict(payload: PredictionRequest) -> dict[str, object]:
    model_variant = payload.model_variant
    if model_variant not in production_stores:
        raise HTTPException(status_code=422, detail=f"Unsupported model_variant: {model_variant}")

    required_ticker = TICKER_SPECIFIC_VARIANTS.get(model_variant)
    if required_ticker is not None and request_ticker(payload.features) != required_ticker:
        raise HTTPException(
            status_code=422,
            detail=f"model_variant {model_variant} is specific to ticker {required_ticker}.",
        )

    selected_store = production_stores[model_variant]
    if selected_store.model is None or selected_store.metadata is None:
        if model_variant == "technical" and store.model is not None and store.metadata is not None:
            selected_store = store
        else:
            raise HTTPException(status_code=503, detail=f"Prediction model is not ready for variant: {model_variant}")

    assert selected_store.metadata is not None
    assert selected_store.model is not None

    if model_variant == "technical_sentiment":
        has_sentiment, missing_sentiment = sentiment_availability(payload.features)
        if not has_sentiment:
            return {
                "predicted_direction": None,
                "probability": None,
                "confidence": None,
                "model_variant": model_variant,
                "has_sufficient_sentiment_data": False,
                "message": "Data sentimen tidak memadai untuk saham ini pada tanggal ini, gunakan model Technical.",
                "missing_sentiment_features": missing_sentiment,
            }

    feature_columns = list(selected_store.metadata["feature_columns"])
    row = {column: payload.features.get(column) for column in feature_columns}
    frame = pd.DataFrame([row], columns=feature_columns)

    raw_direction = selected_store.model.predict(frame)[0]
    predicted_direction = normalize_direction(raw_direction)
    probabilities = selected_store.model.predict_proba(frame)[0]
    classes = list(selected_store.model.classes_)
    probability_map = {normalize_direction(label): float(probabilities[idx]) for idx, label in enumerate(classes)}
    probability = probability_map.get(predicted_direction, max(probability_map.values()))

    if model_variant == "dewa_regime":
        predicted_regime = str(raw_direction).lower()
        regime_probability_map = {str(label).lower(): float(probabilities[idx]) for idx, label in enumerate(classes)}
        regime_probability = regime_probability_map.get(predicted_regime, max(regime_probability_map.values()))
        return {
            "predicted_regime": predicted_regime,
            "probability": round(regime_probability, 4),
            "confidence": round(regime_probability, 4),
            "model_variant": model_variant,
            "model_version": selected_store.metadata.get("model_version"),
            "label_type": selected_store.metadata.get("label_type"),
            "basis": "Model khusus DEWA untuk deteksi rezim move/no_move; ini bukan prediksi arah up/down/flat.",
            "message": "Prediksi ini mendeteksi apakah DEWA cenderung bergerak signifikan atau tidak, bukan arah pergerakannya.",
            "model_name": selected_store.metadata["selected_model"]["model_name"],
            "feature_columns": feature_columns,
        }

    regime = "bullish" if payload.features.get("market_regime_bullish") else "non-bullish"
    weighted_sentiment = float(payload.features.get("weighted_sentiment_5d") or 0.0)
    feature_columns_lower = {str(column).lower() for column in feature_columns}
    uses_sentiment = any("sentiment" in column for column in feature_columns_lower)
    basis = (
        f"Model {selected_store.metadata['selected_model']['model_name']} memakai return_5d, return_20d, "
        f"ATR14, volume ratio, price-vs-EMA50, dan regime {regime}."
    )
    if uses_sentiment:
        basis += f" Weighted sentiment 5D saat ini {weighted_sentiment:.4f} ikut dipertimbangkan."
        scenario_bullish = "Jika regime bullish bertahan dan sentimen tetap mendukung, probabilitas kenaikan membaik."
        scenario_neutral = "Jika regime dan sentimen bercampur, prediksi cenderung kembali ke flat."
        scenario_bearish = "Jika regime melemah dan sentimen memburuk, probabilitas downside meningkat."
    else:
        scenario_bullish = "Jika momentum relatif dan regime bullish bertahan, kandidat teknikal menguat."
        scenario_neutral = "Jika kekuatan relatif antarticker bercampur, pembacaan model cenderung kembali netral."
        scenario_bearish = "Jika momentum melemah dan regime memburuk, risiko underperformance meningkat."

    return {
        "predicted_direction": predicted_direction,
        "probability": round(probability, 4),
        "confidence": round(probability, 4),
        "model_variant": model_variant,
        "model_version": selected_store.metadata.get("model_version"),
        "has_sufficient_sentiment_data": True if model_variant == "technical_sentiment" else None,
        "basis": basis,
        "scenario_bullish": scenario_bullish,
        "scenario_neutral": scenario_neutral,
        "scenario_bearish": scenario_bearish,
        "model_name": selected_store.metadata["selected_model"]["model_name"],
        "label_type": selected_store.metadata.get("label_type"),
        "feature_columns": feature_columns,
    }


@app.post("/rank-stocks")
def rank_stocks(payload: RankingRequest) -> dict[str, object]:
    ranking_store.ensure_ready()
    assert ranking_store.metadata is not None
    assert ranking_store.model is not None

    feature_columns = list(ranking_store.metadata["feature_columns"])
    frame = pd.DataFrame(
        [{column: stock.features.get(column) for column in feature_columns} for stock in payload.stocks],
        columns=feature_columns,
    )

    probabilities = ranking_store.model.predict_proba(frame)
    classes = list(ranking_store.model.classes_)
    positive_class = resolve_positive_class(classes)
    positive_index = classes.index(positive_class)

    ranked = []
    for stock, probability_row in zip(payload.stocks, probabilities):
        score = float(probability_row[positive_index])
        ranked.append(
            {
                "ticker": stock.ticker,
                "score": round(score, 4),
                "signal": score_to_signal(score),
            }
        )

    ranked.sort(key=lambda row: (-row["score"], row["ticker"]))
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index

    return {
        "ranked": ranked,
        "model_version": RANKING_MODEL_VERSION,
        "horizon_days": 5,
        "generated_at": datetime.now(JAKARTA_TZ).date().isoformat(),
    }
