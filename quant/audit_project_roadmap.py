"""Audit roadmap status across Phases A-C and export actionable artifacts.

This script inspects the repository and existing output artifacts to answer:
- which roadmap items are done, partial, or not started
- whether Phase A is operationally closed or still blocked
- what the minimum blockers are before Phase A can be considered complete
- what the execution order should be for Phase B
- what should remain in the Phase C backlog

The audit is evidence-based: it uses concrete files, tests, and JSON artifacts
from the current workspace. It does not assume external runtime state that is
not represented in the repository or exported outputs.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

ROADMAP_PHASES = ["phase_a", "phase_b", "phase_c"]
ROADMAP_STATUS_VALUES = {"done", "partial", "not_started"}
FINAL_PHASE_A_STATUSES = {"closed", "closed_with_notes", "partially_ready", "blocked"}
CSV_COLUMNS = [
    "phase",
    "item_number",
    "item_name",
    "status",
    "evidence",
    "key_files",
    "remaining_gap",
    "recommended_next_action",
]
PHASE_A_BLOCKER_COLUMNS = [
    "priority",
    "blocker_code",
    "blocking_item",
    "why_it_blocks",
    "minimum_action",
    "command_hint",
]


class AuditCliError(ValueError):
    """Friendly CLI error for roadmap auditing."""


@dataclass
class RepoInspector:
    """Small helper for cached file existence/text checks."""

    root: Path
    _text_cache: Dict[str, str] = field(default_factory=dict)

    def path(self, relative_path: str | Path) -> Path:
        """Return the absolute path for a repository-relative file."""

        return self.root / Path(relative_path)

    def exists(self, relative_path: str | Path) -> bool:
        """Return True when the repository-relative path exists."""

        return self.path(relative_path).exists()

    def read_text(self, relative_path: str | Path) -> str:
        """Read file text with caching; return empty string when unavailable."""

        key = str(Path(relative_path))
        if key in self._text_cache:
            return self._text_cache[key]

        path = self.path(relative_path)
        if not path.exists() or not path.is_file():
            self._text_cache[key] = ""
            return ""

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""

        self._text_cache[key] = text
        return text

    def contains_all(self, relative_path: str | Path, needles: Sequence[str]) -> bool:
        """Return True when all case-insensitive needles are present."""

        haystack = self.read_text(relative_path).lower()
        return bool(haystack) and all(str(needle).lower() in haystack for needle in needles)

    def contains_any(self, relative_path: str | Path, needles: Sequence[str]) -> bool:
        """Return True when any case-insensitive needle is present."""

        haystack = self.read_text(relative_path).lower()
        return bool(haystack) and any(str(needle).lower() in haystack for needle in needles)

    def existing_files(self, relative_paths: Iterable[str | Path]) -> List[str]:
        """Return existing repository-relative files as strings."""

        found: List[str] = []
        for relative_path in relative_paths:
            path = self.path(relative_path)
            if path.exists():
                found.append(str(Path(relative_path)))
        return found


def _now_iso() -> str:
    """Return a stable UTC timestamp for exported artifacts."""

    return datetime.now(timezone.utc).isoformat()


def _load_optional_json(path: Path) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    """Load optional JSON data and return a warning string when invalid."""

    if not path.exists() or not path.is_file():
        return None, None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON in {path}: {exc}"
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"Failed to read {path}: {exc}"

    if not isinstance(payload, dict):
        return None, f"JSON payload in {path} is not an object."

    return payload, None


def _dedupe(items: Iterable[str]) -> List[str]:
    """Deduplicate strings while preserving order."""

    seen = set()
    ordered: List[str] = []
    for item in items:
        token = str(item).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _make_item(
    phase: str,
    item_number: int,
    item_name: str,
    status: str,
    evidence: Sequence[str],
    key_files: Sequence[str],
    remaining_gap: str,
    recommended_next_action: str,
) -> Dict[str, object]:
    """Normalize one roadmap item row."""

    if phase not in ROADMAP_PHASES:
        raise ValueError(f"Unsupported phase: {phase}")
    if status not in ROADMAP_STATUS_VALUES:
        raise ValueError(f"Unsupported roadmap status: {status}")

    return {
        "phase": phase,
        "item_number": int(item_number),
        "item_name": item_name,
        "status": status,
        "evidence": _dedupe(evidence),
        "key_files": _dedupe(key_files),
        "remaining_gap": remaining_gap,
        "recommended_next_action": recommended_next_action,
    }


def _phase_summary(items: Sequence[Dict[str, object]]) -> Dict[str, Dict[str, int]]:
    """Aggregate roadmap counts by phase and status."""

    summary: Dict[str, Dict[str, int]] = {
        phase: {"done": 0, "partial": 0, "not_started": 0, "total": 0}
        for phase in ROADMAP_PHASES
    }

    for item in items:
        phase = str(item["phase"])
        status = str(item["status"])
        summary[phase][status] += 1
        summary[phase]["total"] += 1

    return summary


def build_roadmap_items(
    inspector: RepoInspector,
    output_dir: Path,
    baseline_payload: Optional[Dict[str, object]],
    closeout_payload: Optional[Dict[str, object]],
) -> List[Dict[str, object]]:
    """Build roadmap item rows for items 1-12."""

    items: List[Dict[str, object]] = []

    volume_done = inspector.contains_all(
        "quant/phase_a.py",
        ["def add_volume_features", "is_volume_spike", "volume_ratio"],
    ) and inspector.exists("quant/test_phase_a.py")
    items.append(
        _make_item(
            phase="phase_a",
            item_number=1,
            item_name="Volume spike detection",
            status="done" if volume_done else "partial",
            evidence=[
                "quant/phase_a.py menambahkan add_volume_features, volume_ratio, dan is_volume_spike.",
                "quant/test_phase_a.py menguji volume spike dan threshold injection.",
            ]
            if volume_done
            else ["Fondasi volume spike ada, tetapi coverage evidence belum lengkap."],
            key_files=inspector.existing_files(
                [
                    "quant/phase_a.py",
                    "quant/test_phase_a.py",
                    "quant/evaluate_phase_a_real_data.py",
                ]
            ),
            remaining_gap="Tidak ada gap fitur inti. Pertahankan sebagai baseline Phase A dan jangan ubah default tanpa evidence real-data."
            if volume_done
            else "Lengkapi coverage dan jalur evaluasi agar volume spike bisa dianggap stabil.",
            recommended_next_action="Pertahankan default threshold dari baseline freeze dan gunakan threshold sweep real sebagai satu-satunya dasar perubahan.",
        )
    )

    ema_done = inspector.contains_all(
        "quant/phase_a.py",
        ["def add_trend_features", "ema50", "trend_ok", "ema50_slope_up"],
    ) and inspector.exists("quant/test_phase_a.py")
    items.append(
        _make_item(
            phase="phase_a",
            item_number=2,
            item_name="EMA50 trend filter",
            status="done" if ema_done else "partial",
            evidence=[
                "quant/phase_a.py menambahkan EMA50, trend_ok, dan ema50_slope_up.",
                "quant/test_phase_a.py menguji trend filter Phase A.",
            ]
            if ema_done
            else ["Fondasi EMA50 ada, tetapi evidence test belum lengkap."],
            key_files=inspector.existing_files(
                [
                    "quant/phase_a.py",
                    "quant/test_phase_a.py",
                    "quant/evaluate_phase_a_real_data.py",
                ]
            ),
            remaining_gap="Tidak ada gap inti. EMA50 sudah menjadi bagian default pipeline Phase A."
            if ema_done
            else "Pastikan EMA50 ikut dievaluasi dan diuji end-to-end.",
            recommended_next_action="Bekukan EMA50 sebagai guardrail Phase A; eksperimen Fase B harus dibangun di atas filter ini, bukan menggantikannya.",
        )
    )

    backfill_done = (
        inspector.contains_all(
            "app/Services/News/OjkRssFetcher.php",
            ["fetchForMarketInRange", "Default.aspx", "fetchFromPaginatedListing"],
        )
        and inspector.contains_all(
            "app/Console/Commands/FetchOjkNewsCommand.php",
            ["news:fetch-ojk", "--backfill", "refreshOjkBackfill"],
        )
        and inspector.exists("tests/Feature/FetchOjkNewsCommandTest.php")
    )
    backfill_evidence = [
        "app/Services/News/OjkRssFetcher.php mendukung RSS + HTML fallback + paginated Default.aspx untuk backfill historis.",
        "app/Console/Commands/FetchOjkNewsCommand.php menyediakan mode --backfill dengan --from/--to.",
        "tests/Feature/FetchOjkNewsCommandTest.php menguji backfill dan idempotency untuk artikel OJK global.",
    ]
    if closeout_payload and isinstance(closeout_payload.get("ojk_backfill"), dict):
        ojk_backfill = closeout_payload["ojk_backfill"]
        backfill_evidence.append(
            "phase_a_closeout_status.json mencatat inspeksi runtime OJK backfill saat closeout."
        )
        if ojk_backfill.get("ready"):
            backfill_evidence.append("Closeout terakhir menandai OJK backfill sebagai ready.")
    items.append(
        _make_item(
            phase="phase_a",
            item_number=3,
            item_name="Berita backfill Jan-Mar/Feb-Apr 2026",
            status="done" if backfill_done else "partial",
            evidence=backfill_evidence,
            key_files=inspector.existing_files(
                [
                    "app/Services/News/OjkRssFetcher.php",
                    "app/Console/Commands/FetchOjkNewsCommand.php",
                    "tests/Feature/FetchOjkNewsCommandTest.php",
                ]
            ),
            remaining_gap="Tidak ada gap implementasi inti. Gap yang tersisa hanya verifikasi runtime pada environment yang punya MySQL + data historis aktif."
            if backfill_done
            else "Jalur backfill historis belum lengkap atau belum cukup teruji.",
            recommended_next_action="Perlakukan rerun closeout dengan MySQL aktif sebagai verifikasi operasional, bukan sebagai fitur baru.",
        )
    )

    macro_done = (
        inspector.contains_all(
            "app/Services/Analytics/BacktestService.php",
            ["includeMacroNews", "macro_regulatory_summary", "macro_regulatory_attention_score"],
        )
        and inspector.contains_all(
            "app/Services/Analytics/EvaluationReportService.php",
            ["include_macro_news", "macro_regulatory", "macro_regulatory_adjusted"],
        )
        and inspector.contains_all(
            "app/Services/Analytics/SentimentComparisonService.php",
            ["include_macro_news", "macro_regulatory"],
        )
        and inspector.exists("app/Services/Analytics/MacroRegulatorySignalService.php")
        and inspector.exists("tests/Feature/EvaluationReportTest.php")
        and inspector.exists("tests/Unit/MacroRegulatorySignalServiceTest.php")
    )
    items.append(
        _make_item(
            phase="phase_a",
            item_number=4,
            item_name="OJK scheduler / macro news integration",
            status="done" if macro_done else "partial",
            evidence=[
                "OJK disimpan sebagai global news (stock_id = null) dan dibaca oleh jalur backtest/evaluation/comparison.",
                "MacroRegulatorySignalService.php memberi moderation layer untuk OJK neutral-only tanpa memaksa arah bullish/bearish.",
                "EvaluationReportTest dan MacroRegulatorySignalServiceTest menguji jalur macro news serta moderation output.",
            ]
            if macro_done
            else ["Fondasi macro integration ada, tetapi jalur report/backtest belum lengkap."],
            key_files=inspector.existing_files(
                [
                    "app/Services/News/NewsAggregationService.php",
                    "app/Services/Analytics/MacroRegulatorySignalService.php",
                    "app/Services/Analytics/BacktestService.php",
                    "app/Services/Analytics/EvaluationReportService.php",
                    "app/Services/Analytics/SentimentComparisonService.php",
                    "tests/Feature/EvaluationReportTest.php",
                    "tests/Unit/MacroRegulatorySignalServiceTest.php",
                ]
            ),
            remaining_gap="Integrasi sudah selesai. Catatan yang tersisa ada pada kualitas pengaruh sinyal, bukan pada plumbing macro news."
            if macro_done
            else "Selesaikan plumbing macro global news ke evaluation/backtest/controller.",
            recommended_next_action="Pertahankan macro_regulatory_signal sebagai context-only moderation sampai ada bukti kuat untuk directional lift.",
        )
    )

    candle_starter = inspector.contains_all(
        "quant/phase_a.py",
        [
            "def add_candlestick_volume_confirmation_features",
            "candle_volume_confirmed",
            "require_candle_volume_confirmation",
        ],
    )
    candle_eval = inspector.contains_all(
        "quant/evaluate_phase_a_real_data.py",
        [
            "require_candle_volume_confirmation",
            "candle_volume_confirmation_threshold",
        ],
    )
    candle_test = inspector.contains_all(
        "quant/test_phase_a.py",
        ["candle_volume_confirmed", "require_candle_volume_confirmation"]
    )
    candle_status = "partial" if candle_starter else "not_started"
    if candle_starter and candle_eval and candle_test:
        candle_status = "partial"
    items.append(
        _make_item(
            phase="phase_b",
            item_number=5,
            item_name="Volume confirmation per candlestick",
            status=candle_status,
            evidence=[
                "quant/phase_a.py sudah memiliki helper candlestick-volume confirmation yang default-off.",
                "quant/evaluate_phase_a_real_data.py sudah dapat menjalankan evaluator dengan flag experimental candle confirmation.",
                "quant/test_phase_a.py menguji bahwa filter ini hanya aktif bila diminta.",
            ]
            if candle_starter
            else ["Belum ada rule candlestick-volume confirmation yang nyata di engine quant."],
            key_files=inspector.existing_files(
                [
                    "quant/phase_a.py",
                    "quant/evaluate_phase_a_real_data.py",
                    "quant/test_phase_a.py",
                ]
            ),
            remaining_gap="Starter baru ada di engine/evaluator. Belum ada evidence sweep/backtest khusus yang memutuskan apakah rule ini layak dinaikkan menjadi default Fase B."
            if candle_starter
            else "Tambahkan helper candle confirmation yang transparan dan evaluasi tanpa mengubah default Phase A.",
            recommended_next_action="Gunakan starter ini hanya sebagai arm eksperimen: bandingkan vs baseline Phase A beku sebelum memasukkannya ke threshold sweep atau default harian.",
        )
    )

    weekly_foundation = inspector.contains_all(
        "app/Services/Stocks/PriceSeriesService.php",
        ["getSeries", "interval_type", "interval = '1d'"],
    )
    weekly_rule = inspector.contains_any(
        "quant/phase_a.py",
        ["weekly", "multi-timeframe", "1w"]
    ) or inspector.contains_any(
        "app/Services/Analytics/BacktestService.php",
        ["weekly", "1w", "multi-timeframe"]
    )
    items.append(
        _make_item(
            phase="phase_b",
            item_number=6,
            item_name="Multi-timeframe (weekly trend sebelum entry daily)",
            status="partial" if weekly_foundation else "not_started",
            evidence=[
                "PriceSeriesService.php sudah memiliki abstraksi interval_type yang bisa dipakai untuk 1d/1w.",
            ]
            if weekly_foundation
            else ["Belum ada abstraksi interval yang siap dipakai untuk weekly trend."],
            key_files=inspector.existing_files(
                [
                    "app/Services/Stocks/PriceSeriesService.php",
                    "app/Services/Analytics/BacktestService.php",
                    "quant/phase_a.py",
                ]
            ),
            remaining_gap="Belum ada rule weekly trend, belum ada resampling/ingestion 1w, dan belum ada test bahwa trend mingguan memfilter entry daily."
            if not weekly_rule
            else "Rule weekly sudah mulai muncul tetapi belum utuh.",
            recommended_next_action="Tambahkan ingestion/akses 1w lebih dulu, lalu buat weekly trend filter sebagai gate di atas sinyal daily yang sudah stabil.",
        )
    )

    sentiment_momentum_foundation = inspector.contains_all(
        "app/Services/Analytics/SentimentPriceAnalyticsService.php",
        ["per_date_sentiment", "sentiment_trend", "sentimentByDate"],
    )
    sentiment_momentum_rule = inspector.contains_any(
        "app/Services/Analytics/DecisionSupportService.php",
        ["3 hari", "3-day", "sentiment momentum"]
    )
    items.append(
        _make_item(
            phase="phase_b",
            item_number=7,
            item_name="Sentiment momentum (tren 3 hari terakhir)",
            status="partial" if sentiment_momentum_foundation else "not_started",
            evidence=[
                "SentimentPriceAnalyticsService.php sudah menghasilkan per_date_sentiment dan sentiment_trend.",
                "Watchlist/analytics sudah punya seri sentimen harian yang bisa menjadi fondasi momentum 3 hari.",
            ]
            if sentiment_momentum_foundation
            else ["Belum ada seri sentimen harian yang cukup untuk membangun momentum 3 hari."],
            key_files=inspector.existing_files(
                [
                    "app/Services/Analytics/SentimentPriceAnalyticsService.php",
                    "app/Services/Analytics/DecisionSupportService.php",
                    "app/Services/Analytics/BacktestService.php",
                ]
            ),
            remaining_gap="Belum ada rule eksplisit rolling 3 hari, belum ada scoring/backtest untuk sentiment momentum, dan belum ada test dedicated."
            if not sentiment_momentum_rule
            else "Rule sentiment momentum mulai muncul tetapi belum cukup operasional.",
            recommended_next_action="Tambahkan metrik 3-day sentiment momentum di analytics dulu, lalu injeksikan ke decision/backtest sebagai signal tambahan yang bisa dimatikan.",
        )
    )

    adaptive_foundation = (
        inspector.exists("quant/run_phase_a_threshold_sweep.py")
        and inspector.exists("quant/freeze_phase_a_baseline.py")
        and inspector.exists("quant/phase_a_baseline.py")
    )
    adaptive_runtime = bool(
        baseline_payload and baseline_payload.get("adaptive_threshold_enabled")
    )
    items.append(
        _make_item(
            phase="phase_b",
            item_number=8,
            item_name="Backtest per saham / model adaptif per ticker",
            status="partial" if adaptive_foundation else "not_started",
            evidence=[
                "Threshold sweep sudah tersedia per ticker/group/global.",
                "Phase A baseline bisa dibekukan dan secara opsional diterapkan kembali ke evaluator lewat phase_a_baseline.py.",
                "Adaptive runtime saat ini masih bergantung pada artifact freeze, belum menjadi model adaptif penuh lintas stack.",
            ]
            if adaptive_foundation
            else ["Belum ada sweep/adaptive tooling per ticker atau per group."],
            key_files=inspector.existing_files(
                [
                    "quant/run_phase_a_threshold_sweep.py",
                    "quant/freeze_phase_a_baseline.py",
                    "quant/phase_a_baseline.py",
                    "quant/evaluate_phase_a_real_data.py",
                ]
            ),
            remaining_gap="Sudah ada fondasi riset adaptif, tetapi belum ada runtime adaptive model yang menyalurkan keputusan per ticker/group secara konsisten ke semua consumer."
            if adaptive_foundation
            else "Bangun dulu tooling riset per ticker/group sebelum memikirkan model adaptif runtime.",
            recommended_next_action="Pertahankan adaptive logic sebagai refinement Phase B: finalkan baseline global Phase A dulu, baru perluas override per ticker/group yang benar-benar punya sample kuat.",
        )
    )

    net_broker_started = inspector.contains_any(
        "app",
        ["net broker", "broker flow"]
    )
    items.append(
        _make_item(
            phase="phase_c",
            item_number=9,
            item_name="Net broker flow",
            status="partial" if net_broker_started else "not_started",
            evidence=[
                "Belum ada service, model, fetcher, atau test khusus net broker flow di codebase."
            ]
            if not net_broker_started
            else ["Ada jejak awal net broker flow, tetapi belum operasional."],
            key_files=inspector.existing_files(
                [
                    "app/Services",
                    "app/Models",
                    "tests",
                ]
            ),
            remaining_gap="Perlu sumber data broker flow, skema penyimpanan, feature engineering, dan backtest integration penuh.",
            recommended_next_action="Tunda sampai Phase B stabil dan sumber data broker flow sudah dipilih.",
        )
    )

    ihsg_started = inspector.contains_any(
        "app/Services/Analytics",
        ["ihsg", "index correlation", "market index"]
    )
    items.append(
        _make_item(
            phase="phase_c",
            item_number=10,
            item_name="Correlation IHSG",
            status="partial" if ihsg_started else "not_started",
            evidence=[
                "IHSG baru muncul sebagai keyword berita/relevansi, bukan sebagai seri data korelasi di analytics."
            ]
            if not ihsg_started
            else ["Ada fondasi korelasi IHSG, tetapi belum utuh."],
            key_files=inspector.existing_files(
                [
                    "app/Services/Analytics/SentimentPriceAnalyticsService.php",
                    "app/Services/Stocks/PriceSeriesService.php",
                    "tests/Unit/NewsRelevanceTest.php",
                ]
            ),
            remaining_gap="Belum ada ingestion indeks IHSG, belum ada join return saham vs IHSG, dan belum ada report/backtest untuk market correlation regime.",
            recommended_next_action="Sentuh setelah multi-timeframe dan sentiment momentum Phase B stabil, supaya korelasi IHSG punya konteks pemakaian yang jelas.",
        )
    )

    ml_sentiment_foundation = (
        inspector.exists("app/Services/Sentiment/PythonApiSentimentAnalyzer.php")
        and inspector.exists("tests/Unit/PythonApiSentimentAnalyzerTest.php")
    )
    items.append(
        _make_item(
            phase="phase_c",
            item_number=11,
            item_name="Python ML sentiment / IndoBERT",
            status="partial" if ml_sentiment_foundation else "not_started",
            evidence=[
                "PythonApiSentimentAnalyzer.php sudah mendukung endpoint Python/HuggingFace dengan fallback rule-based.",
                "Test unit sudah ada untuk payload valid, payload invalid, dan fallback error.",
                "Belum ada model IndoBERT lokal/evaluasi eksperimen ML yang dibekukan di repo.",
            ]
            if ml_sentiment_foundation
            else ["Belum ada jalur ML sentiment yang nyata di codebase."],
            key_files=inspector.existing_files(
                [
                    "app/Services/Sentiment/PythonApiSentimentAnalyzer.php",
                    "app/Services/Sentiment/HybridSentimentAnalyzer.php",
                    "tests/Unit/PythonApiSentimentAnalyzerTest.php",
                    "config/sentiment.php",
                ]
            ),
            remaining_gap="Integrasi endpoint sudah ada, tetapi model/evaluasi ML belum menjadi baseline resmi. Itu masih backlog lanjutan, bukan close-out Phase A/B."
            if ml_sentiment_foundation
            else "Bangun jalur integrasi ML terlebih dahulu sebelum menyentuh model IndoBERT.",
            recommended_next_action="Tunda sampai fitur sinyal Phase B stabil, lalu ukur apakah ML sentiment benar-benar menambah edge dibanding hybrid rule/current API fallback.",
        )
    )

    journal_started = inspector.contains_any(
        "app/Services/Analytics",
        ["trade journal", "journal analytics", "trading journal"]
    ) or inspector.contains_any(
        "quant",
        ["trade journal", "journal analytics"]
    )
    items.append(
        _make_item(
            phase="phase_c",
            item_number=12,
            item_name="Trade journal analytics",
            status="partial" if journal_started else "not_started",
            evidence=[
                "Belum ada persistence/jurnal trade khusus di repo. Backtest trades ada, tetapi belum diturunkan menjadi journal analytics."
            ]
            if not journal_started
            else ["Ada fondasi journal analytics, tetapi belum lengkap."],
            key_files=inspector.existing_files(
                [
                    "quant/phase_a.py",
                    "app/Services/Analytics/BacktestService.php",
                ]
            ),
            remaining_gap="Perlu penyimpanan journal, agregasi performa per setup, dan UI/report khusus trader workflow.",
            recommended_next_action="Tunda sampai sinyal Phase B stabil, lalu putuskan schema journal yang mengikuti output backtest/trade windows yang sudah matang.",
        )
    )

    return items


def build_phase_a_final_status(
    roadmap_items: Sequence[Dict[str, object]],
    baseline_payload: Optional[Dict[str, object]],
    closeout_payload: Optional[Dict[str, object]],
    inspector: RepoInspector,
) -> Dict[str, object]:
    """Derive one explicit finalization decision for Phase A."""

    phase_a_items = [
        item for item in roadmap_items if item["phase"] == "phase_a"
    ]
    core_items_done = all(item["status"] == "done" for item in phase_a_items)

    baseline_status = str((baseline_payload or {}).get("baseline_status", "draft"))
    readiness_status = str((baseline_payload or {}).get("readiness_status", "partially_ready"))
    strict_code = str((baseline_payload or {}).get("strict_mode_decision_code", ""))
    strict_final = strict_code in {"strict_default_yes", "strict_default_no"}
    baseline_usable_now = baseline_status in {"provisional", "final"} and strict_final

    closeout_status = str((closeout_payload or {}).get("status", "")).strip()
    closeout_reason = str((closeout_payload or {}).get("reason", "")).strip()
    closeout_blocking = list((closeout_payload or {}).get("blocking_items", []))
    closeout_notes = list((closeout_payload or {}).get("notes", []))

    ojk_status = (closeout_payload or {}).get("ojk_backfill", {})
    if not isinstance(ojk_status, dict):
        ojk_status = {}
    macro_status = (closeout_payload or {}).get("macro_regulatory_signal", {})
    if not isinstance(macro_status, dict):
        macro_status = {}

    macro_neutral_policy = "note_if_macro_regulatory_signal_ready_else_blocker"
    if ojk_status.get("neutral_only"):
        macro_neutral_current = (
            "note"
            if macro_status.get("neutral_only_handled") or macro_status.get("ready")
            else "blocker"
        )
    elif ojk_status.get("error"):
        macro_neutral_current = "unknown_runtime"
    else:
        macro_neutral_current = "not_observed"

    ui_paths_present = (
        inspector.exists("app/Http/Controllers/BacktestController.php")
        and inspector.exists("app/Http/Controllers/AnalyticsController.php")
        and inspector.exists("tests/Feature/EvaluationReportTest.php")
        and inspector.exists("tests/Unit/SentimentComparisonServiceTest.php")
    )
    ui_manual_verification_blocker = False
    ui_manual_verification_note = (
        "Controller/report coverage sudah ada; verifikasi UI manual include_macro_news dan macro_regulatory_signal tetap berguna, tetapi bukan blocker formal."
        if ui_paths_present
        else "UI/controller coverage belum lengkap; ini perlu diverifikasi sebelum close-out bisa dipercaya."
    )

    if closeout_status in FINAL_PHASE_A_STATUSES:
        status = closeout_status
        reason = closeout_reason or "Phase A final status mengikuti artifact closeout yang tersedia."
        blocking_items = _dedupe(closeout_blocking)
        notes = _dedupe(closeout_notes + [ui_manual_verification_note])
    else:
        blocking_items = []
        notes = [ui_manual_verification_note]
        if not core_items_done:
            blocking_items.append("Masih ada item inti Phase A yang belum done.")
        if baseline_status == "draft":
            blocking_items.append("Baseline final masih draft; artifact real belum cukup untuk freeze operasional.")
        if not strict_final:
            blocking_items.append("Strict mode default belum final.")
        if macro_neutral_current == "blocker":
            blocking_items.append(
                "OJK neutral-only belum punya moderation layer yang siap, sehingga macro news masih belum berarti."
            )

        if blocking_items:
            status = "blocked" if baseline_status == "draft" else "partially_ready"
            reason = "Phase A belum bisa ditutup karena finalisasi baseline atau runtime closeout masih kurang kuat."
        else:
            status = "closed_with_notes"
            reason = "Item inti Phase A selesai, tetapi closeout artifact resmi belum ditemukan."

    if status not in FINAL_PHASE_A_STATUSES:
        raise ValueError(f"Unsupported Phase A final status: {status}")

    if macro_neutral_current == "note":
        notes.append(
            "OJK historical yang neutral-only diperlakukan sebagai note, bukan blocker, karena moderation layer context-only sudah tersedia."
        )
    elif macro_neutral_current == "unknown_runtime":
        notes.append(
            "Status neutral-only OJK belum bisa diklasifikasikan penuh karena runtime closeout terakhir tidak dapat membaca database."
        )

    ready_for_phase_b = status in {"closed", "closed_with_notes"}
    ready_for_phase_b_reason = (
        "Phase A sudah cukup stabil untuk menjadi baseline resmi sebelum Fase B."
        if ready_for_phase_b
        else "Jangan masuk ke Fase B penuh sebelum baseline freeze real dan closeout runtime tervalidasi."
    )

    return {
        "generated_at": _now_iso(),
        "status": status,
        "reason": reason,
        "baseline_status": baseline_status,
        "readiness_status": readiness_status,
        "baseline_usable_now": bool(baseline_usable_now),
        "baseline_final_now": baseline_status == "final",
        "strict_mode_final_now": bool(strict_final),
        "core_phase_a_items_done": bool(core_items_done),
        "macro_regulatory_mode": "context_only_moderation",
        "macro_ojk_neutral_only_policy": macro_neutral_policy,
        "macro_ojk_neutral_only_current_classification": macro_neutral_current,
        "ui_manual_verification_blocker": bool(ui_manual_verification_blocker),
        "ui_manual_verification_note": ui_manual_verification_note,
        "closeout_artifact_available": closeout_payload is not None,
        "baseline_artifact_available": baseline_payload is not None,
        "ready_to_start_phase_b": bool(ready_for_phase_b),
        "ready_to_start_phase_b_reason": ready_for_phase_b_reason,
        "blocking_items": _dedupe(blocking_items),
        "notes": _dedupe(notes),
    }


def build_phase_a_blockers(
    final_status: Dict[str, object],
    baseline_payload: Optional[Dict[str, object]],
    closeout_payload: Optional[Dict[str, object]],
) -> Tuple[pd.DataFrame, List[str]]:
    """Build minimum blocker rows and prioritized next steps for Phase A."""

    rows: List[Dict[str, object]] = []
    next_steps: List[str] = []

    if final_status["status"] in {"closed", "closed_with_notes"}:
        empty = pd.DataFrame(columns=PHASE_A_BLOCKER_COLUMNS)
        next_steps.append("Phase A sudah melewati gate minimum. Gunakan baseline beku saat memulai eksperimen Fase B.")
        return empty, next_steps

    baseline_status = str(final_status.get("baseline_status", "draft"))
    strict_final = bool(final_status.get("strict_mode_final_now", False))
    closeout_available = bool(final_status.get("closeout_artifact_available", False))
    closeout_blocking = list((closeout_payload or {}).get("blocking_items", []))
    runtime_blocked = any("SQLSTATE" in str(item) or "database" in str(item).lower() for item in closeout_blocking)

    priority = 1
    if baseline_status == "draft" or not strict_final:
        rows.append(
            {
                "priority": priority,
                "blocker_code": "phase_a_real_baseline_not_frozen",
                "blocking_item": "Baseline real belum benar-benar beku atau strict mode belum final.",
                "why_it_blocks": "Tanpa artifact keputusan real, Fase A belum punya baseline resmi untuk screening/evaluation harian.",
                "minimum_action": "Regenerasi artifact evaluator/analyzer/tuning/threshold sweep real, lalu freeze baseline lagi.",
                "command_hint": "python3 -m quant.run_phase_a_threshold_sweep --data-dir data --output-dir output --metadata-file data/ticker_metadata.csv --thresholds 1.5 2.0 2.5 3.0 --min-trades 8",
            }
        )
        priority += 1
        next_steps.extend(
            [
                "Jalankan threshold sweep real untuk menghasilkan phase_a_threshold_decision.json dan best-by-group/best-by-ticker yang aktual.",
                "Jalankan decision layer tuning real jika phase_a_tuning_decision.json belum tersedia, lalu refreeze baseline dengan python3 -m quant.freeze_phase_a_baseline --output-dir output.",
            ]
        )

    if runtime_blocked or not closeout_available:
        rows.append(
            {
                "priority": priority,
                "blocker_code": "phase_a_runtime_closeout_not_validated",
                "blocking_item": "Closeout runtime belum tervalidasi pada environment yang punya MySQL + OJK historical data aktif.",
                "why_it_blocks": "Status final Phase A tidak bisa dipercaya jika baseline, backfill OJK, dan macro_regulatory_signal belum diperiksa pada runtime nyata.",
                "minimum_action": "Pastikan MySQL aktif dan data OJK historis tersedia, lalu rerun closeout.",
                "command_hint": "php artisan phase-a:closeout",
            }
        )
        priority += 1
        next_steps.append(
            "Aktifkan koneksi MySQL yang benar, pastikan artikel OJK historis tersedia, lalu rerun php artisan phase-a:closeout sampai status tidak lagi blocked."
        )

    if str(final_status.get("macro_ojk_neutral_only_current_classification")) == "blocker":
        rows.append(
            {
                "priority": priority,
                "blocker_code": "phase_a_macro_regulatory_moderation_missing",
                "blocking_item": "Macro OJK neutral-only masih tidak berarti karena moderation layer belum siap.",
                "why_it_blocks": "Macro news sudah masuk ke pipeline tetapi belum memoderasi confidence/risk dengan benar.",
                "minimum_action": "Aktifkan atau validasi macro_regulatory_signal sebagai context-only moderation sebelum menyatakan Phase A selesai.",
                "command_hint": "php artisan evaluate:report BBCA --period=30 --macro-regulatory-signal=1",
            }
        )
        priority += 1
        next_steps.append(
            "Validasi bahwa macro_regulatory_signal aktif dan benar-benar muncul di evaluation/backtest/comparison output."
        )

    next_steps.append(
        "Verifikasi UI /backtest dan /analytics dengan include_macro_news=1 dan macro_regulatory_signal=1 sebagai catatan penutup, bukan blocker formal."
    )

    blockers_df = pd.DataFrame(rows, columns=PHASE_A_BLOCKER_COLUMNS)
    return blockers_df, _dedupe(next_steps)


def build_phase_b_execution_plan(
    roadmap_items: Sequence[Dict[str, object]],
    final_status: Dict[str, object],
) -> Dict[str, object]:
    """Build a realistic execution plan for Phase B."""

    item_lookup = {int(item["item_number"]): item for item in roadmap_items}
    gate_status = "ready_to_execute" if final_status["ready_to_start_phase_b"] else "prepare_only"

    execution_order = [
        {
            "priority": 1,
            "item_number": 5,
            "item_name": item_lookup[5]["item_name"],
            "current_status": item_lookup[5]["status"],
            "goal": "Tambahkan filter candle bullish + volume confirmation sebagai eksperimen yang transparan dan default-off.",
            "priority_reason": "Ini quick win Fase B yang paling dekat dengan engine quant Phase A dan paling murah untuk diuji terhadap baseline beku.",
            "likely_files": [
                "quant/phase_a.py",
                "quant/evaluate_phase_a_real_data.py",
                "quant/test_phase_a.py",
            ],
            "data_dependencies": [
                "OHLCV harian yang sama dengan Phase A",
                "Baseline Phase A beku sebagai control arm",
            ],
            "risks": [
                "Trade count bisa turun terlalu tajam jika confirmation terlalu ketat.",
                "Mudah terlihat bagus hanya karena sample trade mengecil.",
            ],
            "tests_needed": [
                "Unit test rule candle confirmation aktif vs nonaktif",
                "Smoke evaluation dengan flag experimental aktif",
            ],
            "expected_artifacts": [
                "Evaluator summary dengan phase_b_candle_confirmation_enabled=true",
                "Perbandingan hasil vs baseline Phase A beku",
            ],
            "starter_available": True,
            "starter_command": "python3 -m quant.evaluate_phase_a_real_data --data-dir data --output-dir output --baseline-config output/phase_a_baseline_final.json --require-candle-volume-confirmation --candle-volume-confirmation-threshold 1.0",
        },
        {
            "priority": 2,
            "item_number": 6,
            "item_name": item_lookup[6]["item_name"],
            "current_status": item_lookup[6]["status"],
            "goal": "Tambahkan weekly trend gate di atas entry daily tanpa mengganggu logika Phase A yang sudah stabil.",
            "priority_reason": "Multi-timeframe paling berguna setelah candle confirmation tersedia, karena weekly trend berperan sebagai gate yang lebih struktural.",
            "likely_files": [
                "app/Services/Stocks/PriceSeriesService.php",
                "app/Services/Analytics/BacktestService.php",
                "quant/phase_a.py",
                "tests/Unit/BacktestServiceTest.php",
            ],
            "data_dependencies": [
                "Series harga interval 1w atau resampling dari 1d",
                "Definisi weekly trend sederhana yang konsisten",
            ],
            "risks": [
                "Kompleksitas data meningkat jika belum ada 1w yang bersih.",
                "Gate weekly bisa menurunkan coverage terlalu besar jika definisinya terlalu kaku.",
            ],
            "tests_needed": [
                "Unit test weekly trend classifier",
                "Backtest regression untuk memastikan default harian tetap utuh saat weekly gate dimatikan",
            ],
            "expected_artifacts": [
                "Report perbandingan daily-only vs weekly-gated entry",
            ],
        },
        {
            "priority": 3,
            "item_number": 7,
            "item_name": item_lookup[7]["item_name"],
            "current_status": item_lookup[7]["status"],
            "goal": "Tambahkan signal momentum sentimen 3 hari yang bisa dipakai sebagai overlay, bukan pengganti core signal.",
            "priority_reason": "Fondasi seri sentimen harian sudah ada; setelah price-side confirmation lebih rapi, momentum sentimen menjadi enhancer yang logis.",
            "likely_files": [
                "app/Services/Analytics/SentimentPriceAnalyticsService.php",
                "app/Services/Analytics/DecisionSupportService.php",
                "app/Services/Analytics/BacktestService.php",
                "tests/Feature/EvaluationReportTest.php",
            ],
            "data_dependencies": [
                "per_date_sentiment yang sudah dihitung analytics service",
                "Definisi rolling 3-day sentiment momentum",
            ],
            "risks": [
                "Noise sentimen harian bisa lebih tinggi daripada sinyal harga.",
                "Momentum mudah double-count dengan weighted sentiment jika tidak dipisah jelas.",
            ],
            "tests_needed": [
                "Unit test 3-day momentum classification",
                "Evaluation/backtest assertion bahwa feature bisa dimatikan tanpa regresi output lama",
            ],
            "expected_artifacts": [
                "Field sentiment_momentum_3d di evaluation/backtest report",
            ],
        },
        {
            "priority": 4,
            "item_number": 8,
            "item_name": item_lookup[8]["item_name"],
            "current_status": item_lookup[8]["status"],
            "goal": "Naikkan tooling per ticker/group dari riset menjadi adaptive refinement yang disiplin dan sample-aware.",
            "priority_reason": "Adaptive refinement paling aman dikerjakan setelah tiga enhancer sebelumnya punya bukti yang bersih terhadap baseline Phase A.",
            "likely_files": [
                "quant/run_phase_a_threshold_sweep.py",
                "quant/freeze_phase_a_baseline.py",
                "quant/phase_a_baseline.py",
                "config/phase_a_baseline.json",
            ],
            "data_dependencies": [
                "Threshold sweep real dengan sample memadai",
                "Metadata ticker/group yang lengkap",
                "Baseline Phase A beku sebagai control arm",
            ],
            "risks": [
                "Overfitting per ticker jika sample trade terlalu sedikit.",
                "Adaptive override sulit dipelihara jika grup/ticker bergeser terlalu sering.",
            ],
            "tests_needed": [
                "Unit test resolver override per group/ticker",
                "Regression test bahwa fallback global baseline tetap aman",
            ],
            "expected_artifacts": [
                "Refined baseline freeze dengan override yang benar-benar evidence-based",
            ],
        },
    ]

    return {
        "generated_at": _now_iso(),
        "gate_status": gate_status,
        "gate_reason": final_status["ready_to_start_phase_b_reason"],
        "phase_a_guardrails": [
            "Jangan ubah default volume spike threshold tanpa artifact sweep real yang baru.",
            "Jangan ubah strict_mode_default tanpa tuning decision real yang eksplisit.",
            "Pertahankan macro_regulatory_signal sebagai context-only moderation sampai ada bukti directional lift yang konsisten.",
            "Semua fitur baru Fase B harus default-off sampai dibandingkan melawan baseline Phase A beku.",
        ],
        "execution_order": execution_order,
    }


def build_phase_c_backlog(
    roadmap_items: Sequence[Dict[str, object]],
    final_status: Dict[str, object],
) -> Dict[str, object]:
    """Build a formal backlog for Phase C."""

    item_lookup = {int(item["item_number"]): item for item in roadmap_items}

    backlog_items = [
        {
            "item_number": 9,
            "item_name": item_lookup[9]["item_name"],
            "current_status": item_lookup[9]["status"],
            "goal": "Tambahkan feature order-flow broker sebagai signal lanjutan setelah stack price/sentiment stabil.",
            "depends_on_phase_b": [
                "Item 5-8 selesai dan baseline baru sudah stabil",
                "Sumber data broker flow dipilih",
            ],
            "effort_estimate": "high",
            "ready_to_touch_when": "Setelah Fase B selesai dan ada vendor/data source broker flow yang jelas.",
        },
        {
            "item_number": 10,
            "item_name": item_lookup[10]["item_name"],
            "current_status": item_lookup[10]["status"],
            "goal": "Ukur korelasi saham vs IHSG untuk market-regime filtering dan context overlay.",
            "depends_on_phase_b": [
                "Item 6 multi-timeframe selesai",
                "Tersedia seri IHSG yang bersih",
            ],
            "effort_estimate": "medium",
            "ready_to_touch_when": "Setelah weekly trend dan sentiment momentum sudah stabil sehingga korelasi IHSG punya konteks pemakaian yang jelas.",
        },
        {
            "item_number": 11,
            "item_name": item_lookup[11]["item_name"],
            "current_status": item_lookup[11]["status"],
            "goal": "Naikkan jalur ML sentiment dari sekadar endpoint integration menjadi eksperimen model yang benar-benar dievaluasi.",
            "depends_on_phase_b": [
                "Fitur sinyal Phase B stabil sehingga uplift ML bisa diukur dengan fair",
                "Dataset evaluasi/label cukup untuk membandingkan hybrid vs ML",
            ],
            "effort_estimate": "high",
            "ready_to_touch_when": "Setelah baseline heuristik + hybrid sentiment tidak banyak berubah lagi.",
        },
        {
            "item_number": 12,
            "item_name": item_lookup[12]["item_name"],
            "current_status": item_lookup[12]["status"],
            "goal": "Bangun analytics journal trade untuk memahami setup mana yang paling efektif dari hasil backtest/live workflow.",
            "depends_on_phase_b": [
                "Setup sinyal Phase B stabil",
                "Ada schema trade log/journal yang disepakati",
            ],
            "effort_estimate": "medium_high",
            "ready_to_touch_when": "Setelah sinyal Phase B cukup stabil untuk menghasilkan trade windows yang pantas dijournal.",
        },
    ]

    return {
        "generated_at": _now_iso(),
        "phase_a_gate_status": final_status["status"],
        "phase_c_should_start_now": False,
        "phase_c_reason": "Fase C sebaiknya baru disentuh setelah Fase B selesai atau minimal closed_with_notes dengan baseline yang stabil.",
        "items": backlog_items,
    }


def _roadmap_txt(
    roadmap_items: Sequence[Dict[str, object]],
    phase_summary: Dict[str, Dict[str, int]],
    final_status: Dict[str, object],
) -> str:
    """Render the roadmap audit into a readable text report."""

    lines = [
        "Project Roadmap Audit",
        "=====================",
        "",
        "Ringkasan fase:",
    ]

    for phase in ROADMAP_PHASES:
        counts = phase_summary[phase]
        lines.append(
            f"- {phase}: done={counts['done']}, partial={counts['partial']}, not_started={counts['not_started']}, total={counts['total']}"
        )

    lines.extend(
        [
            "",
            "Status final Phase A:",
            f"- Status: {final_status['status']}",
            f"- Reason: {final_status['reason']}",
            f"- Ready to start Phase B: {final_status['ready_to_start_phase_b']}",
            "",
            "Audit item per item:",
        ]
    )

    for item in roadmap_items:
        lines.append(
            f"{item['item_number']}. [{item['status']}] {item['item_name']} ({item['phase']})"
        )
        for evidence in item["evidence"]:
            lines.append(f"   Evidence: {evidence}")
        lines.append(f"   Remaining gap: {item['remaining_gap']}")
        lines.append(f"   Next action: {item['recommended_next_action']}")

    return "\n".join(lines) + "\n"


def _phase_a_summary_txt(final_status: Dict[str, object], blockers_df: pd.DataFrame, next_steps: Sequence[str]) -> str:
    """Render one explicit Phase A finalization summary."""

    lines = [
        "Phase A Final Summary",
        "=====================",
        "",
        f"- Status: {final_status['status']}",
        f"- Reason: {final_status['reason']}",
        f"- Baseline status: {final_status['baseline_status']}",
        f"- Readiness status: {final_status['readiness_status']}",
        f"- Baseline usable now: {final_status['baseline_usable_now']}",
        f"- Baseline final now: {final_status['baseline_final_now']}",
        f"- Strict mode final now: {final_status['strict_mode_final_now']}",
        f"- Macro OJK neutral-only policy: {final_status['macro_ojk_neutral_only_policy']}",
        f"- Macro OJK current classification: {final_status['macro_ojk_neutral_only_current_classification']}",
        f"- UI verification blocker: {final_status['ui_manual_verification_blocker']}",
        f"- Ready to start Phase B: {final_status['ready_to_start_phase_b']}",
        "",
    ]

    if final_status["blocking_items"]:
        lines.append("Blocking items:")
        for item in final_status["blocking_items"]:
            lines.append(f"- {item}")
        lines.append("")

    if final_status["notes"]:
        lines.append("Notes:")
        for item in final_status["notes"]:
            lines.append(f"- {item}")
        lines.append("")

    if blockers_df.empty:
        lines.append("Minimum blockers: none")
    else:
        lines.append("Minimum blockers:")
        for _, row in blockers_df.iterrows():
            lines.append(
                f"- P{int(row['priority'])} {row['blocker_code']}: {row['blocking_item']}"
            )
            lines.append(f"  Action: {row['minimum_action']}")

    lines.append("")
    lines.append("Minimum next steps:")
    for step in next_steps:
        lines.append(f"- {step}")

    return "\n".join(lines) + "\n"


def _phase_b_plan_txt(plan: Dict[str, object]) -> str:
    """Render the Phase B execution plan into plain text."""

    lines = [
        "Phase B Execution Plan",
        "======================",
        "",
        f"- Gate status: {plan['gate_status']}",
        f"- Gate reason: {plan['gate_reason']}",
        "",
        "Phase A guardrails:",
    ]

    for item in plan["phase_a_guardrails"]:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("Execution order:")
    for item in plan["execution_order"]:
        lines.append(
            f"- P{item['priority']} Item {item['item_number']} {item['item_name']} [{item['current_status']}]"
        )
        lines.append(f"  Goal: {item['goal']}")
        lines.append(f"  Why now: {item['priority_reason']}")
        if item.get("starter_available"):
            lines.append(f"  Starter command: {item['starter_command']}")

    return "\n".join(lines) + "\n"


def _phase_c_backlog_txt(backlog: Dict[str, object]) -> str:
    """Render the Phase C backlog into plain text."""

    lines = [
        "Phase C Backlog",
        "===============",
        "",
        f"- Phase A gate status: {backlog['phase_a_gate_status']}",
        f"- Start now: {backlog['phase_c_should_start_now']}",
        f"- Reason: {backlog['phase_c_reason']}",
        "",
        "Backlog items:",
    ]

    for item in backlog["items"]:
        lines.append(
            f"- Item {item['item_number']} {item['item_name']} [{item['current_status']}]"
        )
        lines.append(f"  Goal: {item['goal']}")
        lines.append(f"  Effort: {item['effort_estimate']}")
        lines.append(f"  Ready when: {item['ready_to_touch_when']}")

    return "\n".join(lines) + "\n"


def _status_df(roadmap_items: Sequence[Dict[str, object]]) -> pd.DataFrame:
    """Convert roadmap items into a flat CSV-friendly DataFrame."""

    rows = []
    for item in roadmap_items:
        rows.append(
            {
                "phase": item["phase"],
                "item_number": item["item_number"],
                "item_name": item["item_name"],
                "status": item["status"],
                "evidence": " | ".join(item["evidence"]),
                "key_files": " | ".join(item["key_files"]),
                "remaining_gap": item["remaining_gap"],
                "recommended_next_action": item["recommended_next_action"],
            }
        )
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def export_audit_outputs(
    output_dir: Path,
    roadmap_payload: Dict[str, object],
    roadmap_txt: str,
    phase_gap_df: pd.DataFrame,
    final_status: Dict[str, object],
    phase_a_summary_txt: str,
    blockers_df: pd.DataFrame,
    next_steps_txt: str,
    phase_b_plan: Dict[str, object],
    phase_b_plan_txt: str,
    phase_c_backlog: Dict[str, object],
    phase_c_backlog_txt: str,
) -> Dict[str, Path]:
    """Write all roadmap, Phase A, Phase B, and Phase C artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "project_roadmap_status_json": output_dir / "project_roadmap_status.json",
        "project_roadmap_status_txt": output_dir / "project_roadmap_status.txt",
        "project_phase_gap_analysis_csv": output_dir / "project_phase_gap_analysis.csv",
        "phase_a_final_status_json": output_dir / "phase_a_final_status.json",
        "phase_a_final_summary_txt": output_dir / "phase_a_final_summary.txt",
        "phase_a_minimum_blockers_csv": output_dir / "phase_a_minimum_blockers.csv",
        "phase_a_minimum_next_steps_txt": output_dir / "phase_a_minimum_next_steps.txt",
        "phase_b_execution_plan_json": output_dir / "phase_b_execution_plan.json",
        "phase_b_execution_plan_txt": output_dir / "phase_b_execution_plan.txt",
        "phase_c_backlog_json": output_dir / "phase_c_backlog.json",
        "phase_c_backlog_txt": output_dir / "phase_c_backlog.txt",
    }

    paths["project_roadmap_status_json"].write_text(
        json.dumps(roadmap_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    paths["project_roadmap_status_txt"].write_text(roadmap_txt, encoding="utf-8")
    phase_gap_df.to_csv(paths["project_phase_gap_analysis_csv"], index=False)

    paths["phase_a_final_status_json"].write_text(
        json.dumps(final_status, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    paths["phase_a_final_summary_txt"].write_text(phase_a_summary_txt, encoding="utf-8")
    blockers_df.to_csv(paths["phase_a_minimum_blockers_csv"], index=False)
    paths["phase_a_minimum_next_steps_txt"].write_text(next_steps_txt, encoding="utf-8")

    paths["phase_b_execution_plan_json"].write_text(
        json.dumps(phase_b_plan, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    paths["phase_b_execution_plan_txt"].write_text(phase_b_plan_txt, encoding="utf-8")

    paths["phase_c_backlog_json"].write_text(
        json.dumps(phase_c_backlog, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    paths["phase_c_backlog_txt"].write_text(phase_c_backlog_txt, encoding="utf-8")

    return paths


def audit_project_roadmap(
    project_root: Path,
    output_dir: Path,
) -> Dict[str, object]:
    """Run the roadmap audit and export all requested artifacts."""

    root = Path(project_root)
    if not root.exists() or not root.is_dir():
        raise AuditCliError(f"Project root not found or not a directory: {root}")

    resolved_output_dir = root / output_dir if not Path(output_dir).is_absolute() else Path(output_dir)
    inspector = RepoInspector(root=root)

    baseline_payload, baseline_warning = _load_optional_json(
        resolved_output_dir / "phase_a_baseline_final.json"
    )
    closeout_payload, closeout_warning = _load_optional_json(
        resolved_output_dir / "phase_a_closeout_status.json"
    )

    warnings = _dedupe([warning for warning in [baseline_warning, closeout_warning] if warning])

    roadmap_items = build_roadmap_items(
        inspector=inspector,
        output_dir=resolved_output_dir,
        baseline_payload=baseline_payload,
        closeout_payload=closeout_payload,
    )
    phase_summary = _phase_summary(roadmap_items)
    final_status = build_phase_a_final_status(
        roadmap_items=roadmap_items,
        baseline_payload=baseline_payload,
        closeout_payload=closeout_payload,
        inspector=inspector,
    )
    blockers_df, next_steps = build_phase_a_blockers(
        final_status=final_status,
        baseline_payload=baseline_payload,
        closeout_payload=closeout_payload,
    )
    phase_b_plan = build_phase_b_execution_plan(
        roadmap_items=roadmap_items,
        final_status=final_status,
    )
    phase_c_backlog = build_phase_c_backlog(
        roadmap_items=roadmap_items,
        final_status=final_status,
    )

    roadmap_payload = {
        "generated_at": _now_iso(),
        "project_root": str(root),
        "phase_summary": phase_summary,
        "current_focus": (
            "phase_b_execution"
            if final_status["ready_to_start_phase_b"]
            else "phase_a_closeout_and_phase_b_preparation"
        ),
        "phase_a_final_status": final_status,
        "warnings": warnings,
        "items": roadmap_items,
    }

    phase_gap_df = _status_df(roadmap_items)
    roadmap_txt = _roadmap_txt(
        roadmap_items=roadmap_items,
        phase_summary=phase_summary,
        final_status=final_status,
    )
    phase_a_summary_txt = _phase_a_summary_txt(
        final_status=final_status,
        blockers_df=blockers_df,
        next_steps=next_steps,
    )
    next_steps_txt = "\n".join(["Phase A Minimum Next Steps", "==========================", "", *[f"- {step}" for step in next_steps]]) + "\n"
    phase_b_plan_txt = _phase_b_plan_txt(phase_b_plan)
    phase_c_backlog_txt = _phase_c_backlog_txt(phase_c_backlog)

    export_paths = export_audit_outputs(
        output_dir=resolved_output_dir,
        roadmap_payload=roadmap_payload,
        roadmap_txt=roadmap_txt,
        phase_gap_df=phase_gap_df,
        final_status=final_status,
        phase_a_summary_txt=phase_a_summary_txt,
        blockers_df=blockers_df,
        next_steps_txt=next_steps_txt,
        phase_b_plan=phase_b_plan,
        phase_b_plan_txt=phase_b_plan_txt,
        phase_c_backlog=phase_c_backlog,
        phase_c_backlog_txt=phase_c_backlog_txt,
    )

    return {
        "roadmap_payload": roadmap_payload,
        "final_status": final_status,
        "phase_b_plan": phase_b_plan,
        "phase_c_backlog": phase_c_backlog,
        "export_paths": {key: str(path) for key, path in export_paths.items()},
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Audit roadmap status across Phases A-C and export closeout/planning artifacts."
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Repository root to inspect. Default: current working directory",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory for audit outputs and Phase A input artifacts. Default: output",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)

    try:
        result = audit_project_roadmap(
            project_root=Path(args.project_root),
            output_dir=Path(args.output_dir),
        )
    except AuditCliError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(f"Roadmap audit failed: {exc}")
        return 1

    final_status = result["final_status"]
    export_paths = result["export_paths"]

    print("Roadmap audit complete.")
    print(f"Phase A final status: {final_status['status']}")
    print(f"Reason: {final_status['reason']}")
    print(f"Roadmap JSON: {export_paths['project_roadmap_status_json']}")
    print(f"Phase A final JSON: {export_paths['phase_a_final_status_json']}")
    print(f"Phase B plan JSON: {export_paths['phase_b_execution_plan_json']}")
    print(f"Phase C backlog JSON: {export_paths['phase_c_backlog_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
