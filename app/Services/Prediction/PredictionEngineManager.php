<?php

namespace App\Services\Prediction;

class PredictionEngineManager
{
    public function __construct(
        protected ?BaselinePredictionService $baseline = null
    ) {
        $this->baseline ??= new BaselinePredictionService();
    }

    public function predict(array $features): array
    {
        return $this->baseline->predict($features);
    }
}
