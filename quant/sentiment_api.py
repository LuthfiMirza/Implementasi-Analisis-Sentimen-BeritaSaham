#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_DIR = Path(os.environ.get("SENTIMENT_MODEL_DIR", "storage/app/sentiment_model/indobert_finetuned_v1"))

app = FastAPI(title="Laravel Sentiment API", version="1.0.0")

_tokenizer = None
_model = None


class SentimentRequest(BaseModel):
    inputs: str = Field(default="")


def load_model() -> None:
    global _tokenizer, _model
    if not MODEL_DIR.is_dir():
        return
    _tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    _model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR))
    _model.eval()


load_model()


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok" if _model is not None else "model_not_loaded",
        "model_dir": str(MODEL_DIR),
    }


@app.post("/sentiment")
def sentiment(payload: SentimentRequest) -> dict[str, object]:
    if _model is None or _tokenizer is None:
        raise HTTPException(status_code=503, detail="Fine-tuned sentiment model is not loaded.")

    text = payload.inputs.strip()
    if not text:
        raise HTTPException(status_code=422, detail="inputs must not be empty.")

    with torch.no_grad():
        encoded = _tokenizer(text, truncation=True, max_length=256, return_tensors="pt")
        logits = _model(**encoded).logits[0]
        probs = torch.softmax(logits, dim=-1)

    predicted_id = int(torch.argmax(probs).item())
    label = _model.config.id2label[predicted_id]
    confidence = round(float(probs[predicted_id].item()), 4)
    score = {"positive": confidence, "negative": -confidence, "neutral": 0.0}.get(label, 0.0)

    return {
        "label": label,
        "confidence": confidence,
        "score": round(score, 4),
        "prob_positive": round(float(probs[_model.config.label2id["positive"]].item()), 4),
        "prob_neutral": round(float(probs[_model.config.label2id["neutral"]].item()), 4),
        "prob_negative": round(float(probs[_model.config.label2id["negative"]].item()), 4),
    }
