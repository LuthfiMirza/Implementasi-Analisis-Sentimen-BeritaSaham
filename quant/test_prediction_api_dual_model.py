from __future__ import annotations

import importlib

import numpy as np
from fastapi.testclient import TestClient


class DummyModel:
    classes_ = np.array(["down", "flat", "up"])

    def predict(self, frame):
        return np.array(["up"])

    def predict_proba(self, frame):
        return np.array([[0.1, 0.2, 0.7]])


def ready_store(feature_columns):
    api = importlib.import_module("quant.prediction_api")
    store = api.PredictionModelStore([])
    store.model = DummyModel()
    store.metadata = {
        "model_version": "test-version",
        "feature_columns": feature_columns,
        "selected_model": {"model_name": "dummy_model"},
    }
    return store


def test_predict_technical_variant_returns_model_metadata(monkeypatch):
    api = importlib.import_module("quant.prediction_api")
    monkeypatch.setitem(api.production_stores, "technical", ready_store(["return_5d", "return_20d"]))
    client = TestClient(api.app)

    response = client.post(
        "/predict",
        json={"model_variant": "technical", "features": {"return_5d": 0.01, "return_20d": 0.02}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_direction"] == "up"
    assert payload["probability"] == 0.7
    assert payload["model_variant"] == "technical"
    assert payload["model_version"] == "test-version"


def test_predict_technical_sentiment_requires_sentiment_data(monkeypatch):
    api = importlib.import_module("quant.prediction_api")
    monkeypatch.setitem(
        api.production_stores,
        "technical_sentiment",
        ready_store(["return_5d", "weighted_sentiment_5d", "has_sentiment_data", "news_volume_5d"]),
    )
    client = TestClient(api.app)

    response = client.post(
        "/predict",
        json={
            "model_variant": "technical_sentiment",
            "features": {"return_5d": 0.01, "has_sentiment_data": 0, "news_volume_5d": 0},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_direction"] is None
    assert payload["has_sufficient_sentiment_data"] is False
    assert "gunakan model Technical" in payload["message"]


def test_health_reports_both_production_variants(monkeypatch):
    api = importlib.import_module("quant.prediction_api")
    monkeypatch.setitem(api.production_stores, "technical", ready_store(["return_5d"]))
    monkeypatch.setitem(api.production_stores, "technical_sentiment", ready_store(["return_5d", "weighted_sentiment_5d"]))
    client = TestClient(api.app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["production_models_ready"]["technical"] is True
    assert payload["production_models_ready"]["technical_sentiment"] is True
