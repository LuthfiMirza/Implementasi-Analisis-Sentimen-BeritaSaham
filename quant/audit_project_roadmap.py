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


def _load_execution_context(output_dir: Path) -> Dict[str, Optional[Dict[str, object]]]:
    """Load optional execution artifacts used to keep the roadmap current."""

    artifact_map = {
        "phase_b_postmortem": "phase_b_postmortem.json",
        "phase_b_next_phase": "phase_b_go_no_go_next_phase.json",
        "phase_b_final_closeout": "phase_b_final_closeout.json",
        "project_after_phase_b_decision": "project_after_phase_b_decision.json",
        "phase_b_retest_readiness_gate": "phase_b_retest_readiness_gate.json",
        "phase_b_v2_redesign_decision": "phase_b_v2_redesign_decision.json",
        "phase_b_v2_next_best_experiment": "phase_b_v2_next_best_experiment.json",
        "baseline_redesign": "baseline_redesign_go_no_go.json",
        "baseline_v3_signal_rule": "baseline_v3_signal_rule_go_no_go.json",
        "baseline_v3_signal_rule_summary": "baseline_v3_signal_rule_summary.json",
        "baseline_revision": "baseline_v2_go_no_go.json",
        "baseline_v2_validation": "baseline_v2_validation_go_no_go.json",
        "baseline_v2_validation_summary": "baseline_v2_validation_summary.json",
        "baseline_v2_subset": "baseline_v2_subset_go_no_go.json",
        "baseline_v2_subset_summary": "baseline_v2_subset_validation_summary.json",
        "transition": "phase_a_to_phase_b_transition.json",
        "item5_go_no_go": "phase_b_item5_go_no_go.json",
        "item6_go_no_go": "phase_b_item6_go_no_go.json",
        "item7_go_no_go": "phase_b_item7_go_no_go.json",
        "item7_summary": "phase_b_item7_sentiment_momentum_summary.json",
        "item8_go_no_go": "phase_b_item8_go_no_go.json",
        "item8_summary": "phase_b_item8_global_summary.json",
    }

    context: Dict[str, Optional[Dict[str, object]]] = {}
    for key, filename in artifact_map.items():
        payload, _ = _load_optional_json(output_dir / filename)
        context[key] = payload
    return context


def _safe_str(value: object) -> str:
    """Return a trimmed string representation with empty fallback."""

    return str(value).strip() if value is not None else ""


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
    context = _load_execution_context(output_dir)

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
    item5_payload = context.get("item5_go_no_go") or {}
    item5_decision = _safe_str(item5_payload.get("decision"))
    item5_next_action = _safe_str(item5_payload.get("next_action"))
    item5_evidence = [
        "quant/phase_a.py sudah memiliki helper candlestick-volume confirmation yang default-off.",
        "quant/evaluate_phase_a_real_data.py sudah dapat menjalankan evaluator dengan flag experimental candle confirmation.",
        "quant/test_phase_a.py menguji bahwa filter ini hanya aktif bila diminta.",
    ] if candle_starter else ["Belum ada rule candlestick-volume confirmation yang nyata di engine quant."]
    if item5_decision == "no_go":
        item5_evidence.extend(
            [
                "Artifact output/phase_b_item5_go_no_go.json memutuskan item 5 final no_go dengan next_action=stop.",
                "Eksperimen item 5 collapse ke effective threshold baseline sehingga tidak menambah informasi baru.",
            ]
        )
    items.append(
        _make_item(
            phase="phase_b",
            item_number=5,
            item_name="Volume confirmation per candlestick",
            status=candle_status,
            evidence=item5_evidence,
            key_files=inspector.existing_files(
                [
                    "quant/phase_a.py",
                    "quant/evaluate_phase_a_real_data.py",
                    "quant/test_phase_a.py",
                    "output/phase_b_item5_go_no_go.json",
                ]
            ),
            remaining_gap=(
                "Eksperimen item 5 sudah final no_go. Filter tambahan overlap dengan baseline aktif, retensi trade tidak membaik, dan fitur ini belum additive."
                if item5_decision == "no_go"
                else (
                    "Starter baru ada di engine/evaluator. Belum ada evidence sweep/backtest khusus yang memutuskan apakah rule ini layak dinaikkan menjadi default Fase B."
                    if candle_starter
                    else "Tambahkan helper candle confirmation yang transparan dan evaluasi tanpa mengubah default Phase A."
                )
            ),
            recommended_next_action=(
                "Biarkan item 5 tetap stop; evaluasi ulang hanya setelah baseline inti direvisi dan tervalidasi."
                if item5_next_action == "stop"
                else "Gunakan starter ini hanya sebagai arm eksperimen: bandingkan vs baseline Phase A beku sebelum memasukkannya ke threshold sweep atau default harian."
            ),
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
    item6_payload = context.get("item6_go_no_go") or {}
    item6_decision = _safe_str(item6_payload.get("decision"))
    item6_next_action = _safe_str(item6_payload.get("next_action"))
    item6_evidence = [
        "PriceSeriesService.php sudah memiliki abstraksi interval_type yang bisa dipakai untuk 1d/1w.",
    ] if weekly_foundation else ["Belum ada abstraksi interval yang siap dipakai untuk weekly trend."]
    if item6_decision == "no_go":
        item6_evidence.extend(
            [
                "Artifact output/phase_b_item6_go_no_go.json memutuskan item 6 final no_go dengan next_action=stop.",
                "Eksperimen multi-timeframe gagal terutama karena trade retention terlalu rendah dan tidak ada ticker improve dengan retention memadai.",
            ]
        )
    items.append(
        _make_item(
            phase="phase_b",
            item_number=6,
            item_name="Multi-timeframe (weekly trend sebelum entry daily)",
            status="partial" if weekly_foundation else "not_started",
            evidence=item6_evidence,
            key_files=inspector.existing_files(
                [
                    "app/Services/Stocks/PriceSeriesService.php",
                    "app/Services/Analytics/BacktestService.php",
                    "quant/phase_a.py",
                    "output/phase_b_item6_go_no_go.json",
                ]
            ),
            remaining_gap=(
                "Eksperimen item 6 sudah final no_go. Weekly trend belum terbukti usable karena tambahan filter membuat trade retention runtuh sebelum ada edge yang bisa dipromosikan."
                if item6_decision == "no_go"
                else (
                    "Belum ada rule weekly trend, belum ada resampling/ingestion 1w, dan belum ada test bahwa trend mingguan memfilter entry daily."
                    if not weekly_rule
                    else "Rule weekly sudah mulai muncul tetapi belum utuh."
                )
            ),
            recommended_next_action=(
                "Tetap nonaktifkan item 6; kembali ke perbaikan baseline inti sebelum memikirkan gate weekly lagi."
                if item6_next_action == "stop"
                else "Tambahkan ingestion/akses 1w lebih dulu, lalu buat weekly trend filter sebagai gate di atas sinyal daily yang sudah stabil."
            ),
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
    item7_payload = context.get("item7_go_no_go") or {}
    item7_summary = context.get("item7_summary") or {}
    item7_decision = _safe_str(item7_payload.get("decision"))
    item7_next_action = _safe_str(item7_payload.get("next_action"))
    item7_aggregate = dict(item7_summary.get("aggregate") or {})
    item7_evidence = [
        "SentimentPriceAnalyticsService.php sudah menghasilkan per_date_sentiment dan sentiment_trend.",
        "Watchlist/analytics sudah punya seri sentimen harian yang bisa menjadi fondasi momentum 3 hari.",
    ] if sentiment_momentum_foundation else ["Belum ada seri sentimen harian yang cukup untuk membangun momentum 3 hari."]
    if item7_decision == "no_go":
        item7_evidence.extend(
            [
                "Artifact output/phase_b_item7_go_no_go.json memutuskan item 7 final no_go dengan next_action=stop.",
                (
                    "Real-data rerun menunjukkan sentiment momentum collapse: "
                    f"candidate_total_trades_sum={item7_aggregate.get('candidate_total_trades_sum', 'n/a')}, "
                    f"trade_retention_mean_pct={item7_aggregate.get('trade_retention_mean_pct', 'n/a')}."
                ),
            ]
        )
    items.append(
        _make_item(
            phase="phase_b",
            item_number=7,
            item_name="Sentiment momentum (tren 3 hari terakhir)",
            status="partial" if sentiment_momentum_foundation else "not_started",
            evidence=item7_evidence,
            key_files=inspector.existing_files(
                [
                    "app/Services/Analytics/SentimentPriceAnalyticsService.php",
                    "app/Services/Analytics/DecisionSupportService.php",
                    "app/Services/Analytics/BacktestService.php",
                    "output/phase_b_item7_go_no_go.json",
                    "output/phase_b_item7_sentiment_momentum_summary.json",
                ]
            ),
            remaining_gap=(
                "Eksperimen item 7 sudah final no_go. Sinyal sentimen belum cukup informatif untuk gating karena trade collapse ke nol pada data real yang runnable."
                if item7_decision == "no_go"
                else (
                    "Belum ada rule eksplisit rolling 3 hari, belum ada scoring/backtest untuk sentiment momentum, dan belum ada test dedicated."
                    if not sentiment_momentum_rule
                    else "Rule sentiment momentum mulai muncul tetapi belum cukup operasional."
                )
            ),
            recommended_next_action=(
                "Jangan hidupkan lagi item 7; audit relevansi sentiment series dan baseline entry dulu sebelum mencoba gating sentimen baru."
                if item7_next_action == "stop"
                else "Tambahkan metrik 3-day sentiment momentum di analytics dulu, lalu injeksikan ke decision/backtest sebagai signal tambahan yang bisa dimatikan."
            ),
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
    item8_payload = context.get("item8_go_no_go") or {}
    item8_summary = context.get("item8_summary") or {}
    item8_decision = _safe_str(item8_payload.get("decision"))
    item8_next_action = _safe_str(item8_payload.get("next_action"))
    item8_evidence = [
        "Threshold sweep sudah tersedia per ticker/group/global.",
        "Phase A baseline bisa dibekukan dan secara opsional diterapkan kembali ke evaluator lewat phase_a_baseline.py.",
        "Adaptive runtime saat ini masih bergantung pada artifact freeze, belum menjadi model adaptif penuh lintas stack.",
    ] if adaptive_foundation else ["Belum ada sweep/adaptive tooling per ticker atau per group."]
    if item8_decision == "no_go":
        item8_evidence.extend(
            [
                "Artifact output/phase_b_item8_go_no_go.json memutuskan item 8 final no_go dengan next_action=stop.",
                (
                    "Adaptive backtest tidak usable pada data real: "
                    f"evaluated_config_count={item8_summary.get('evaluated_config_count', 'n/a')}, "
                    f"eligible_best_ticker_count={item8_summary.get('eligible_best_ticker_count', 'n/a')}, "
                    f"adaptive_model_supported={item8_summary.get('adaptive_model_supported', 'n/a')}."
                ),
            ]
        )
    items.append(
        _make_item(
            phase="phase_b",
            item_number=8,
            item_name="Backtest per saham / model adaptif per ticker",
            status="partial" if adaptive_foundation else "not_started",
            evidence=item8_evidence,
            key_files=inspector.existing_files(
                [
                    "quant/run_phase_a_threshold_sweep.py",
                    "quant/freeze_phase_a_baseline.py",
                    "quant/phase_a_baseline.py",
                    "quant/evaluate_phase_a_real_data.py",
                    "output/phase_b_item8_go_no_go.json",
                    "output/phase_b_item8_global_summary.json",
                ]
            ),
            remaining_gap=(
                "Eksperimen item 8 sudah final no_go. Search space adaptif belum usable dan belum ada ticker/group yang lolos guardrail sample untuk promosi."
                if item8_decision == "no_go"
                else (
                    "Sudah ada fondasi riset adaptif, tetapi belum ada runtime adaptive model yang menyalurkan keputusan per ticker/group secara konsisten ke semua consumer."
                    if adaptive_foundation
                    else "Bangun dulu tooling riset per ticker/group sebelum memikirkan model adaptif runtime."
                )
            ),
            recommended_next_action=(
                "Tetap parkirkan item 8; revisi baseline inti dulu sebelum memperlebar adaptive search space lagi."
                if item8_next_action == "stop"
                else "Pertahankan adaptive logic sebagai refinement Phase B: finalkan baseline global Phase A dulu, baru perluas override per ticker/group yang benar-benar punya sample kuat."
            ),
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

    normalized_closeout_blocking: List[str] = []
    for item in closeout_blocking:
        normalized = str(item).lower()
        if "baseline" in normalized and baseline_status in {"provisional", "final"}:
            continue
        if "strict mode" in normalized and strict_final:
            continue
        normalized_closeout_blocking.append(str(item))

    if closeout_status in FINAL_PHASE_A_STATUSES:
        status = closeout_status
        reason = closeout_reason or "Phase A final status mengikuti artifact closeout yang tersedia."
        blocking_items = _dedupe(normalized_closeout_blocking)
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
    output_dir: Optional[Path] = None,
) -> Dict[str, object]:
    """Build a realistic execution plan for Phase B."""

    item_lookup = {int(item["item_number"]): item for item in roadmap_items}
    context = _load_execution_context(Path(output_dir)) if output_dir is not None else {}
    transition = context.get("transition") or {}
    phase_b_closeout = context.get("phase_b_final_closeout") or {}
    project_after_phase_b = context.get("project_after_phase_b_decision") or {}
    readiness_gate = context.get("phase_b_retest_readiness_gate") or {}

    transition_mode = _safe_str(transition.get("phase_b_entry_mode"))
    redesign_track = _safe_str((context.get("phase_b_v2_redesign_decision") or {}).get("recommended_redesign_track"))
    official_next_action = _safe_str(phase_b_closeout.get("recommended_primary_next_step")) or _safe_str(project_after_phase_b.get("recommended_primary_next_step"))
    readiness_status = _safe_str(readiness_gate.get("final_decision")) or "belum_boleh_retest"
    gate_status = "phase_b_closed_waiting_data_extension_and_framework_redesign"
    gate_reason = (
        "Per 21 April 2026, Phase B sudah ditutup tanpa kandidat. "
        "Langkah berikutnya hanya data extension, baseline evaluation redesign, dan refresh readiness blocker audit."
    )

    execution_order = [
        {
            "priority": 1,
            "step_code": "baseline_trade_design_redesign_audit",
            "item_number": 0,
            "item_name": "Baseline trade-design redesign audit",
            "current_status": "planned",
            "goal": "Audit ulang baseline tanpa fitur baru untuk memperbaiki hold period, trade labeling, trade retention, dan floor sample sebagai fondasi redesign framework evaluasi.",
            "priority_reason": "Postmortem Phase B menempatkan trade design baseline sebagai failure mode utama, jadi baseline harus diaudit ulang sebelum ada diskusi tentang retry strategi.",
            "likely_files": [
                "quant/run_baseline_trade_design_redesign.py",
                "quant/test_run_baseline_trade_design_redesign.py",
                "quant/run_phase_b_v2_redesign_diagnostics.py",
            ],
            "data_dependencies": [
                "OHLCV harian yang sama dengan Phase A",
                "Baseline Phase A beku sebagai control arm",
            ],
            "risks": [
                "Coverage bisa tetap terlalu kecil walau hold period dipersingkat.",
                "Perbaikan score global bisa tampak membaik tetapi tetap belum cukup usable untuk redesign framework.",
            ],
            "tests_needed": [
                "Unit test redesign scorer dan selection logic",
                "Smoke run redesign di data real yang sama dengan baseline aktif",
            ],
            "expected_artifacts": [
                "output/baseline_redesign_go_no_go.json",
                "output/baseline_redesign_global_summary.json",
            ],
            "starter_available": True,
            "starter_command": "python3 -m quant.run_baseline_trade_design_redesign --data-dir data --output-dir output --baseline-config output/phase_a_baseline_final.json --metadata-file data/ticker_metadata.csv --hold-period-options 3 5 7 --min-trades-options 5 8 10",
        },
        {
            "priority": 2,
            "step_code": "baseline_v2_candidate_validation_audit",
            "item_number": 0,
            "item_name": "Baseline v2 candidate validation audit",
            "current_status": "planned",
            "goal": "Validasi kandidat redesign hanya untuk memastikan usability audit, bukan untuk promosi baseline operasional atau membuka retry.",
            "priority_reason": "Data extension adalah prasyarat. Validation hanya boleh menjawab apakah kandidat redesign layak disimpan sebagai input framework redesign.",
            "likely_files": [
                "quant/run_baseline_v2_candidate_validation.py",
                "quant/run_baseline_revision_diagnostics.py",
                "quant/test_run_baseline_v2_candidate_validation.py",
            ],
            "data_dependencies": [
                "Baseline redesign candidate JSON",
                "Metadata ticker/group yang sama dengan evaluasi baseline",
            ],
            "risks": [
                "Candidate bisa improve pada score tetapi tetap gagal guardrail eligible ticker.",
                "Candidate terlihat lebih baik pada subset kecil tetapi tetap tidak boleh dipromosikan ke baseline operasional.",
            ],
            "tests_needed": [
                "Unit test validation delta vs active baseline",
                "Regression test decision guardrail min_eligible_tickers",
            ],
            "expected_artifacts": [
                "output/baseline_v2_go_no_go.json",
                "output/baseline_v2_validation_summary.json",
            ],
            "starter_available": True,
            "starter_command": "python3 -m quant.run_baseline_v2_candidate_validation --data-dir data --output-dir output --baseline-config output/phase_a_baseline_final.json --candidate-file output/baseline_v2_best_candidate.json --metadata-file data/ticker_metadata.csv --min-trades 5 --min-eligible-tickers 3",
        },
        {
            "priority": 3,
            "step_code": "phase_b_readiness_guardrail_hardening",
            "item_number": 0,
            "item_name": "Readiness guardrail hardening",
            "current_status": "planned",
            "goal": "Tambahkan blocker eksplisit untuk coverage, usable OOS window, overlap audit, signal sparsity, dan baseline redesign usability agar retry prematur terkunci.",
            "priority_reason": "Artefak gate lama masih bisa menghasilkan status seolah retest siap, padahal keputusan resmi proyek sudah menutup track eksperimen strategi.",
            "likely_files": [
                "quant/run_phase_b_retest_readiness_gate.py",
                "quant/run_phase_b_distribution_and_oos_target_audit.py",
                "quant/test_run_phase_b_retest_readiness_gate.py",
            ],
            "data_dependencies": [
                "output/phase_b_v2_overlap_audit.json",
                "output/phase_b_v2_trade_design_audit.json",
                "output/baseline_redesign_go_no_go.json",
                "output/baseline_v2_validation_go_no_go.json",
            ],
            "risks": [
                "Policy realignment lama bisa tetap menurunkan ambang terlalu agresif bila tidak dikunci ulang.",
                "Gate yang tidak membaca audit overlap/sparsity akan terus membuka jalur retry terlalu dini.",
            ],
            "tests_needed": [
                "Regression test readiness blocker baru",
                "Smoke audit untuk memastikan final_decision tetap belum_boleh_retest",
            ],
            "expected_artifacts": [
                "output/phase_b_retest_readiness_gate.json",
                "output/phase_b_readiness_blocker_audit.json",
            ],
            "starter_available": True,
            "starter_command": "python3 -m quant.run_phase_b_retest_readiness_gate --data-dir data --output-dir output --metadata-file data/ticker_metadata.csv",
        },
        {
            "priority": 4,
            "step_code": "phase_b_data_extension_execution",
            "item_number": 0,
            "item_name": "Phase B data extension execution",
            "current_status": "planned",
            "goal": "Jalankan perluasan data sebagai prasyarat resmi sebelum ada evaluasi readiness ulang apa pun.",
            "priority_reason": "Keputusan final proyek menyatakan fokus berikutnya adalah collect more data + redesign evaluation framework, bukan strategi baru.",
            "likely_files": [
                "quant/run_phase_b_data_extension_execution_plan.py",
                "quant/run_phase_b_data_extension_progress_update.py",
                "quant/test_run_phase_b_data_extension_execution_plan.py",
            ],
            "data_dependencies": [
                "Ticker metadata yang diperbarui",
                "Segmentation dan fairness audit terbaru",
            ],
            "risks": [
                "History bertambah tetapi article-day dan OOS fairness tetap timpang.",
                "Progress tanpa refresh metadata/segmentation bisa membuat audit salah membaca blocker aktif.",
            ],
            "tests_needed": [
                "Smoke plan generation",
                "Regression test progress tracker dan recheck status",
            ],
            "expected_artifacts": [
                "output/phase_b_data_extension_execution_plan.json",
                "output/phase_b_data_extension_progress_update.json",
            ],
            "starter_available": True,
            "starter_command": "python3 -m quant.run_phase_b_data_extension_execution_plan --data-dir data --output-dir output --metadata-file data/ticker_metadata.csv",
        },
        {
            "priority": 5,
            "step_code": "phase_b_items_5_to_8_parking_rule",
            "item_number": 5,
            "item_name": item_lookup[5]["item_name"],
            "current_status": item_lookup[5]["status"],
            "goal": "Tetap parkir item 5-8 global selama track data extension dan framework redesign berjalan.",
            "priority_reason": "Postmortem resmi menyatakan item 5-8 final no_go pada konfigurasi lama dan tidak boleh diaktifkan ulang secara prematur.",
            "likely_files": [
                "output/phase_b_postmortem.txt",
                "output/phase_b_go_no_go_next_phase.json",
                "output/project_current_state_summary.txt",
            ],
            "data_dependencies": [
                "Postmortem Phase B final",
                "Current state summary yang masih freeze",
            ],
            "risks": [
                "Membuka ulang item 5-8 secara global terlalu dini akan menghabiskan sample tanpa edge baru.",
            ],
            "tests_needed": [
                "Tidak ada test code baru; ini guardrail keputusan eksekusi.",
            ],
            "expected_artifacts": [
                "Phase B artifacts tetap konsisten dengan status freeze saat ini",
            ],
        },
    ]

    return {
        "generated_at": _now_iso(),
        "gate_status": gate_status,
        "gate_reason": gate_reason,
        "retry_scope": "none",
        "strategy_context": {
            "transition_mode": transition_mode or None,
            "recommended_redesign_track": redesign_track or None,
            "official_next_action": official_next_action or None,
            "readiness_gate_status": readiness_status,
        },
        "phase_a_guardrails": [
            "Jangan ubah default volume spike threshold tanpa artifact sweep real yang baru.",
            "Jangan ubah strict_mode_default tanpa tuning decision real yang eksplisit.",
            "Pertahankan macro_regulatory_signal sebagai context-only moderation sampai ada bukti directional lift yang konsisten.",
            "Semua fitur baru Fase B harus default-off sampai dibandingkan melawan baseline Phase A beku.",
            "Jangan hidupkan lagi item 7 sentiment momentum atau item 8 adaptive selama data extension dan redesign framework belum ditutup resmi.",
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
    latest_execution_status: Optional[Dict[str, object]] = None,
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
        ]
    )

    latest = dict(latest_execution_status or {})
    if latest:
        lines.extend(["", "Status terkini strategi:"])
        ordered_keys = [
            ("phase_b_status", "Phase B status"),
            ("phase_c_decision", "Phase C decision"),
            ("root_problem_class", "Root problem class"),
            ("retest_readiness_status", "Retest readiness status"),
            ("can_continue_strategy_experiments_now", "Can continue strategy experiments now"),
            ("baseline_redesign_status", "Baseline redesign status"),
            ("baseline_v3_signal_rule_status", "Baseline v3 signal rule status"),
            ("baseline_v3_signal_rule_best_rule", "Baseline v3 signal rule best rule"),
            ("baseline_revision_status", "Baseline revision status"),
            ("baseline_v2_validation_status", "Baseline v2 validation status"),
            ("baseline_v2_subset_status", "Baseline v2 subset status"),
            ("current_track", "Current track"),
            ("recommended_next_action", "Recommended next action"),
        ]
        for key, label in ordered_keys:
            value = _safe_str(latest.get(key))
            if value:
                lines.append(f"- {label}: {value}")

    lines.extend(["", "Audit item per item:"])

    for item in roadmap_items:
        lines.append(
            f"{item['item_number']}. [{item['status']}] {item['item_name']} ({item['phase']})"
        )
        for evidence in item["evidence"]:
            lines.append(f"   Evidence: {evidence}")
        lines.append(f"   Remaining gap: {item['remaining_gap']}")
        lines.append(f"   Next action: {item['recommended_next_action']}")

    return "\n".join(lines) + "\n"


def _build_latest_execution_status(output_dir: Path) -> Dict[str, object]:
    """Summarize the latest strategic status from execution artifacts."""

    context = _load_execution_context(output_dir)
    transition = context.get("transition") or {}
    phase_b_postmortem = context.get("phase_b_postmortem") or {}
    phase_b_next_phase = context.get("phase_b_next_phase") or {}
    phase_b_final_closeout = context.get("phase_b_final_closeout") or {}
    project_after_phase_b = context.get("project_after_phase_b_decision") or {}
    retest_gate = context.get("phase_b_retest_readiness_gate") or {}
    baseline_redesign = context.get("baseline_redesign") or {}
    baseline_v3_signal_rule = context.get("baseline_v3_signal_rule") or {}
    baseline_revision = context.get("baseline_revision") or {}
    baseline_v2_validation = context.get("baseline_v2_validation") or {}
    baseline_v2_subset = context.get("baseline_v2_subset") or {}

    baseline_v3_status = _safe_str(baseline_v3_signal_rule.get("decision"))
    baseline_v3_next_action = _safe_str(baseline_v3_signal_rule.get("recommended_next_action"))
    baseline_v3_track = (
        "redesign_baseline_v2_again"
        if baseline_v3_status == "no_go"
        else baseline_v3_next_action
    )

    return {
        "phase_b_status": _safe_str(
            phase_b_final_closeout.get("phase_b_final_status")
            or project_after_phase_b.get("phase_b_final_status")
            or phase_b_postmortem.get("phase_b_status")
            or transition.get("phase_b_status")
        ),
        "phase_c_decision": _safe_str(
            project_after_phase_b.get("phase_c_decision")
            or phase_b_next_phase.get("phase_c_decision")
        ),
        "root_problem_class": _safe_str(
            project_after_phase_b.get("root_problem_class")
            or phase_b_next_phase.get("root_problem_class")
        ),
        "baseline_redesign_status": _safe_str(baseline_redesign.get("decision") or transition.get("baseline_redesign_status")),
        "baseline_v3_signal_rule_status": baseline_v3_status,
        "baseline_v3_signal_rule_best_rule": _safe_str(baseline_v3_signal_rule.get("best_rule")),
        "baseline_revision_status": _safe_str(baseline_revision.get("decision") or transition.get("baseline_revision_status")),
        "baseline_v2_validation_status": _safe_str(
            baseline_v2_validation.get("decision") or transition.get("baseline_v2_validation_status")
        ),
        "baseline_v2_subset_status": _safe_str(
            baseline_v2_subset.get("decision") or transition.get("baseline_v2_subset_status")
        ),
        "retest_readiness_status": _safe_str(retest_gate.get("final_decision")),
        "can_continue_strategy_experiments_now": str(
            bool(project_after_phase_b.get("can_continue_strategy_experiments_now"))
            if "can_continue_strategy_experiments_now" in project_after_phase_b
            else bool(phase_b_final_closeout.get("can_continue_strategy_experiments_now"))
        ).lower(),
        "current_track": _safe_str(
            project_after_phase_b.get("recommended_primary_next_step")
            or phase_b_final_closeout.get("recommended_primary_next_step")
            or baseline_v3_track
            or transition.get("baseline_v2_subset_next_action")
            or baseline_v2_subset.get("next_action")
            or transition.get("baseline_v2_validation_next_action")
            or baseline_v2_validation.get("recommended_next_action")
            or transition.get("baseline_revision_next_action")
            or baseline_revision.get("next_action")
        ),
        "recommended_next_action": _safe_str(
            phase_b_final_closeout.get("recommended_primary_next_step")
            or project_after_phase_b.get("recommended_primary_next_step")
            or baseline_v3_track
            or baseline_v2_subset.get("next_action")
            or baseline_v2_validation.get("recommended_next_action")
            or baseline_revision.get("next_action")
            or baseline_redesign.get("next_action")
            or phase_b_next_phase.get("recommended_next_action")
        ),
    }


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
        output_dir=resolved_output_dir,
    )
    phase_c_backlog = build_phase_c_backlog(
        roadmap_items=roadmap_items,
        final_status=final_status,
    )

    latest_execution_status = _build_latest_execution_status(resolved_output_dir)

    roadmap_payload = {
        "generated_at": _now_iso(),
        "project_root": str(root),
        "phase_summary": phase_summary,
        "current_focus": (
            "phase_b_closed_data_extension_and_framework_redesign"
            if _safe_str((context := _load_execution_context(resolved_output_dir)).get("phase_b_final_closeout", {}).get("phase_b_final_status")).startswith("phase_b_closed")
            else "phase_b_execution"
            if final_status["ready_to_start_phase_b"]
            else "phase_a_closeout_and_phase_b_preparation"
        ),
        "latest_execution_status": latest_execution_status,
        "phase_a_final_status": final_status,
        "warnings": warnings,
        "items": roadmap_items,
    }

    phase_gap_df = _status_df(roadmap_items)
    roadmap_txt = _roadmap_txt(
        roadmap_items=roadmap_items,
        phase_summary=phase_summary,
        final_status=final_status,
        latest_execution_status=latest_execution_status,
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
