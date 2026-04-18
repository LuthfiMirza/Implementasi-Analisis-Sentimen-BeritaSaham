"""Ensure Phase A threshold/tuning decision artifacts exist or explain why not."""

from __future__ import annotations

import argparse
import json
import shutil
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.analyze_phase_a_results import AnalysisCliError, analyze_phase_a_results  # noqa: E402
from quant.decide_phase_a_tuning import TuningCliError, decide_phase_a_tuning  # noqa: E402
from quant.evaluate_phase_a_real_data import EvaluationCliError, evaluate_folder  # noqa: E402
from quant.phase_a_transition_utils import (  # noqa: E402
    dedupe,
    validate_threshold_artifact,
    validate_tuning_artifact,
)
from quant.run_phase_a_threshold_sweep import (  # noqa: E402
    ThresholdSweepCliError,
    resolve_metadata_file,
    run_phase_a_threshold_sweep,
)


class EnsureDecisionArtifactsCliError(ValueError):
    """Friendly CLI error for decision-artifact orchestration."""


def _now_iso() -> str:
    """Return a stable UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def _count_ticker_csv_files(data_dir: Path, metadata_file: Optional[Path] = None) -> int:
    """Count CSV files that look like ticker OHLCV inputs."""

    folder = Path(data_dir)
    if not folder.exists() or not folder.is_dir():
        return 0

    excluded = Path(metadata_file).resolve() if metadata_file is not None and Path(metadata_file).exists() else None
    count = 0
    for path in folder.glob("*.csv"):
        if excluded is not None and path.resolve() == excluded:
            continue
        count += 1
    return count


def _attempt_laravel_real_data_export(
    data_dir: Path,
    metadata_file: Optional[Path],
    min_rows: int = 50,
) -> Tuple[str, Optional[str]]:
    """Try exporting real OHLCV data from the Laravel stock_prices table."""

    php_binary = shutil.which("php")
    if php_binary is None:
        return "failed", "PHP binary tidak tersedia, jadi export data real dari Laravel DB tidak bisa dijalankan."

    project_root = Path(__file__).resolve().parent.parent
    command = [
        php_binary,
        "artisan",
        "phase-a:export-real-data",
        f"--data-dir={data_dir}",
        f"--min-rows={int(min_rows)}",
    ]
    if metadata_file is not None:
        command.append(f"--metadata-file={metadata_file}")

    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return "failed", f"Gagal menjalankan export data real Laravel: {exc}"

    output = "\n".join(
        part.strip()
        for part in [completed.stdout, completed.stderr]
        if part and part.strip()
    ).strip()

    if completed.returncode != 0:
        return "failed", output or "Export data real Laravel gagal tanpa pesan error."

    return "passed", output or None


def inspect_build_prerequisites(output_dir: Path, data_dir: Path, metadata_file: Optional[Path]) -> Dict[str, object]:
    """Inspect current prerequisites before attempting builds."""

    summary_file = Path(output_dir) / "phase_a_summary.csv"
    aggregate_file = Path(output_dir) / "phase_a_aggregate_summary.csv"
    skipped_file = Path(output_dir) / "phase_a_skipped.csv"
    recommendations_file = Path(output_dir) / "phase_a_recommendations.txt"
    classification_file = Path(output_dir) / "phase_a_ticker_classification.csv"
    analysis_summary_file = Path(output_dir) / "phase_a_analysis_summary.csv"
    group_analysis_file = Path(output_dir) / "phase_a_group_analysis.csv"

    data_dir = Path(data_dir)
    resolved_metadata = resolve_metadata_file(data_dir=data_dir, metadata_file=metadata_file)
    ticker_csv_count = _count_ticker_csv_files(data_dir, resolved_metadata)

    return {
        "data_dir": str(data_dir),
        "data_dir_exists": data_dir.exists() and data_dir.is_dir(),
        "ticker_csv_count": ticker_csv_count,
        "metadata_file": str(resolved_metadata) if resolved_metadata is not None else None,
        "metadata_exists": resolved_metadata is not None and Path(resolved_metadata).exists(),
        "evaluator_outputs_ready": summary_file.exists() and aggregate_file.exists() and skipped_file.exists(),
        "analysis_outputs_ready": recommendations_file.exists() and classification_file.exists(),
        "files": {
            "summary_file": str(summary_file),
            "aggregate_file": str(aggregate_file),
            "skipped_file": str(skipped_file),
            "recommendations_file": str(recommendations_file),
            "classification_file": str(classification_file),
            "analysis_summary_file": str(analysis_summary_file),
            "group_analysis_file": str(group_analysis_file),
        },
    }


def _build_evaluator_outputs(
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path],
) -> Tuple[str, Optional[str]]:
    """Build evaluator outputs needed by the analyzer/tuning layers."""

    try:
        evaluate_folder(
            folder_path=data_dir,
            output_dir=output_dir,
            evaluate_strict=True,
            metadata_file=metadata_file,
        )
    except EvaluationCliError as exc:
        return "failed", str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return "failed", f"Unexpected evaluator build failure: {exc}"

    return "passed", None


def _build_analysis_outputs(
    output_dir: Path,
    metadata_file: Optional[Path],
) -> Tuple[str, Optional[str]]:
    """Build analyzer outputs used by the tuning layer."""

    summary_file = Path(output_dir) / "phase_a_summary.csv"
    aggregate_file = Path(output_dir) / "phase_a_aggregate_summary.csv"
    skipped_file = Path(output_dir) / "phase_a_skipped.csv"

    try:
        analyze_phase_a_results(
            summary_file=summary_file,
            aggregate_file=aggregate_file,
            skipped_file=skipped_file,
            metadata_file=metadata_file,
            output_dir=output_dir,
        )
    except AnalysisCliError as exc:
        return "failed", str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return "failed", f"Unexpected analyzer build failure: {exc}"

    return "passed", None


def _build_threshold_decision(
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path],
    thresholds: Sequence[float],
    hold_period: int,
    allow_overlap: bool,
    min_trades: int,
) -> Tuple[str, Optional[str]]:
    """Build the threshold decision artifact from available OHLCV data."""

    try:
        run_phase_a_threshold_sweep(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
            thresholds=thresholds,
            strict=True,
            hold_period=hold_period,
            allow_overlap=allow_overlap,
            min_trades=min_trades,
        )
    except ThresholdSweepCliError as exc:
        return "failed", str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return "failed", f"Unexpected threshold build failure: {exc}"

    return "passed", None


def _build_tuning_decision(
    output_dir: Path,
    metadata_file: Optional[Path],
) -> Tuple[str, Optional[str]]:
    """Build the tuning decision artifact from analyzer outputs."""

    try:
        decide_phase_a_tuning(
            recommendations_file=Path(output_dir) / "phase_a_recommendations.txt",
            classification_file=Path(output_dir) / "phase_a_ticker_classification.csv",
            analysis_summary_file=Path(output_dir) / "phase_a_analysis_summary.csv",
            group_analysis_file=Path(output_dir) / "phase_a_group_analysis.csv",
            summary_file=Path(output_dir) / "phase_a_summary.csv",
            metadata_file=metadata_file,
            output_dir=output_dir,
        )
    except TuningCliError as exc:
        return "failed", str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return "failed", f"Unexpected tuning build failure: {exc}"

    return "passed", None


def ensure_phase_a_decision_artifacts(
    output_dir: Path,
    data_dir: Path = Path("data"),
    metadata_file: Optional[Path] = None,
    thresholds: Optional[Sequence[float]] = None,
    hold_period: int = 5,
    allow_overlap: bool = False,
    min_trades: int = 8,
    build_missing: bool = True,
) -> Dict[str, object]:
    """Ensure Phase A threshold/tuning decision artifacts exist or report blockers."""

    output_dir = Path(output_dir)
    data_dir = Path(data_dir)
    resolved_metadata = resolve_metadata_file(data_dir=data_dir, metadata_file=metadata_file)
    thresholds = list(thresholds or [1.5, 2.0, 2.5, 3.0])

    prerequisites = inspect_build_prerequisites(output_dir, data_dir, resolved_metadata)
    build_attempts: List[Dict[str, object]] = []
    blockers: List[str] = []
    next_actions: List[str] = []

    threshold_artifact = validate_threshold_artifact(output_dir)
    tuning_artifact = validate_tuning_artifact(output_dir)

    if (
        build_missing
        and prerequisites["ticker_csv_count"] == 0
        and (not threshold_artifact["valid"] or not tuning_artifact["valid"])
    ):
        status, error = _attempt_laravel_real_data_export(
            data_dir=data_dir,
            metadata_file=resolved_metadata,
            min_rows=50,
        )
        build_attempts.append(
            {
                "artifact": "laravel_real_data_export",
                "status": status,
                "command_hint": (
                    "php artisan phase-a:export-real-data "
                    f"--data-dir={shlex.quote(str(data_dir))} "
                    + (
                        f"--metadata-file={shlex.quote(str(resolved_metadata))} "
                        if resolved_metadata is not None
                        else ""
                    )
                    + "--min-rows=50"
                ).strip(),
                "error": None if status == "passed" else error,
                "output": error if status == "passed" else None,
            }
        )
        if status != "passed" and error:
            blockers.append(f"Export data real Laravel gagal: {error}")
            next_actions.append(
                "Export CSV OHLCV real dari Laravel DB dengan php artisan phase-a:export-real-data --data-dir=data --metadata-file=data/ticker_metadata.csv --min-rows=50"
            )
        prerequisites = inspect_build_prerequisites(output_dir, data_dir, resolved_metadata)

    if not threshold_artifact["valid"] and build_missing:
        if prerequisites["data_dir_exists"] and prerequisites["ticker_csv_count"] > 0:
            status, error = _build_threshold_decision(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=resolved_metadata,
                thresholds=thresholds,
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                min_trades=min_trades,
            )
            build_attempts.append(
                {
                    "artifact": "threshold_decision",
                    "status": status,
                    "command_hint": (
                        "python3 -m quant.run_phase_a_threshold_sweep "
                        f"--data-dir {shlex.quote(str(data_dir))} "
                        f"--output-dir {shlex.quote(str(output_dir))} "
                        f"--thresholds {' '.join(str(item) for item in thresholds)} "
                        f"--min-trades {int(min_trades)} --strict"
                    ),
                    "error": error,
                }
            )
            if status != "passed" and error:
                blockers.append(error)
        else:
            blockers.append("Threshold decision belum bisa dibangun karena data OHLCV per ticker belum siap.")
            next_actions.append(
                f"Sediakan CSV OHLCV per ticker di {data_dir} atau ekspor dari Laravel DB, lalu rerun resolver artifact."
            )

    threshold_artifact = validate_threshold_artifact(output_dir)
    if not threshold_artifact["valid"]:
        blockers.extend(threshold_artifact["blocking_reasons"])
        next_actions.append(
            "Bangun threshold artifact dengan python3 -m quant.run_phase_a_threshold_sweep --data-dir data --output-dir output --thresholds 1.5 2.0 2.5 3.0 --min-trades 8 --strict"
        )

    if not tuning_artifact["valid"] and build_missing:
        recommendations_ready = Path(prerequisites["files"]["recommendations_file"]).exists()
        classification_ready = Path(prerequisites["files"]["classification_file"]).exists()
        if not (recommendations_ready and classification_ready):
            if not prerequisites["evaluator_outputs_ready"]:
                if prerequisites["data_dir_exists"] and prerequisites["ticker_csv_count"] > 0:
                    status, error = _build_evaluator_outputs(
                        data_dir=data_dir,
                        output_dir=output_dir,
                        metadata_file=resolved_metadata,
                    )
                    build_attempts.append(
                        {
                            "artifact": "phase_a_evaluator_outputs",
                            "status": status,
                            "command_hint": (
                                "python3 -m quant.evaluate_phase_a_real_data "
                                f"--data-dir {shlex.quote(str(data_dir))} "
                                f"--output-dir {shlex.quote(str(output_dir))} --strict"
                            ),
                            "error": error,
                        }
                    )
                    if status != "passed" and error:
                        blockers.append(error)
                else:
                    blockers.append(
                        "Tuning decision belum bisa dibangun karena evaluator output belum ada dan data OHLCV belum siap."
                    )
                    next_actions.append(
                        f"Sediakan CSV OHLCV per ticker di {data_dir}, ekspor dari Laravel DB, atau siapkan hasil evaluator di {output_dir}."
                    )

            if Path(prerequisites["files"]["summary_file"]).exists():
                status, error = _build_analysis_outputs(
                    output_dir=output_dir,
                    metadata_file=resolved_metadata,
                )
                build_attempts.append(
                    {
                        "artifact": "phase_a_analysis_outputs",
                        "status": status,
                        "command_hint": (
                            "python3 -m quant.analyze_phase_a_results "
                            f"--summary-file {shlex.quote(prerequisites['files']['summary_file'])} "
                            f"--aggregate-file {shlex.quote(prerequisites['files']['aggregate_file'])} "
                            f"--skipped-file {shlex.quote(prerequisites['files']['skipped_file'])} "
                            f"--output-dir {shlex.quote(str(output_dir))}"
                        ),
                        "error": error,
                    }
                )
                if status != "passed" and error:
                    blockers.append(error)

        recommendations_ready = Path(prerequisites["files"]["recommendations_file"]).exists()
        classification_ready = Path(prerequisites["files"]["classification_file"]).exists()
        if recommendations_ready and classification_ready:
            status, error = _build_tuning_decision(
                output_dir=output_dir,
                metadata_file=resolved_metadata,
            )
            build_attempts.append(
                {
                    "artifact": "tuning_decision",
                    "status": status,
                    "command_hint": (
                        "python3 -m quant.decide_phase_a_tuning "
                        f"--recommendations-file {shlex.quote(prerequisites['files']['recommendations_file'])} "
                        f"--classification-file {shlex.quote(prerequisites['files']['classification_file'])} "
                        f"--analysis-summary-file {shlex.quote(prerequisites['files']['analysis_summary_file'])} "
                        f"--group-analysis-file {shlex.quote(prerequisites['files']['group_analysis_file'])} "
                        f"--summary-file {shlex.quote(prerequisites['files']['summary_file'])} "
                        f"--output-dir {shlex.quote(str(output_dir))}"
                    ),
                    "error": error,
                }
            )
            if status != "passed" and error:
                blockers.append(error)

    tuning_artifact = validate_tuning_artifact(output_dir)
    if not tuning_artifact["valid"]:
        blockers.extend(tuning_artifact["blocking_reasons"])
        next_actions.append(
            "Bangun tuning artifact dengan python3 -m quant.decide_phase_a_tuning --recommendations-file output/phase_a_recommendations.txt --classification-file output/phase_a_ticker_classification.csv --analysis-summary-file output/phase_a_analysis_summary.csv --group-analysis-file output/phase_a_group_analysis.csv --summary-file output/phase_a_summary.csv --output-dir output"
        )

    prerequisites = inspect_build_prerequisites(output_dir, data_dir, resolved_metadata)

    status_payload = {
        "generated_at": _now_iso(),
        "output_dir": str(output_dir),
        "data_dir": str(data_dir),
        "metadata_file": str(resolved_metadata) if resolved_metadata is not None else None,
        "threshold_decision_exists": bool(Path(output_dir / "phase_a_threshold_decision.json").exists()),
        "tuning_decision_exists": bool(Path(output_dir / "phase_a_tuning_decision.json").exists()),
        "threshold_decision_valid": bool(threshold_artifact["valid"]),
        "tuning_decision_valid": bool(tuning_artifact["valid"]),
        "threshold_artifact": threshold_artifact,
        "tuning_artifact": tuning_artifact,
        "build_attempts": build_attempts,
        "prerequisites": prerequisites,
        "blockers": dedupe(blockers),
        "next_action": dedupe(next_actions),
        "all_required_decisions_ready": bool(threshold_artifact["valid"] and tuning_artifact["valid"]),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "phase_a_decision_artifact_status.json"
    report_path = output_dir / "phase_a_decision_artifact_report.txt"
    status_path.write_text(
        json.dumps(status_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    report_lines = [
        "Phase A Decision Artifact Status",
        "===============================",
        "",
        f"- Generated at: {status_payload['generated_at']}",
        f"- Threshold decision exists: {status_payload['threshold_decision_exists']}",
        f"- Threshold decision valid: {status_payload['threshold_decision_valid']}",
        f"- Tuning decision exists: {status_payload['tuning_decision_exists']}",
        f"- Tuning decision valid: {status_payload['tuning_decision_valid']}",
        f"- All required decisions ready: {status_payload['all_required_decisions_ready']}",
        "",
        "Prerequisites:",
        f"- Data dir exists: {prerequisites['data_dir_exists']}",
        f"- Ticker CSV count: {prerequisites['ticker_csv_count']}",
        f"- Evaluator outputs ready: {prerequisites['evaluator_outputs_ready']}",
        f"- Analysis outputs ready: {prerequisites['analysis_outputs_ready']}",
    ]

    if build_attempts:
        report_lines.extend(["", "Build attempts:"])
        for attempt in build_attempts:
            report_lines.append(
                f"- {attempt['artifact']}: {attempt['status']}"
                + (f" | error={attempt['error']}" if attempt.get("error") else "")
            )

    if status_payload["blockers"]:
        report_lines.extend(["", "Blockers:"])
        for item in status_payload["blockers"]:
            report_lines.append(f"- {item}")
    else:
        report_lines.extend(["", "Blockers:", "- none"])

    if status_payload["next_action"]:
        report_lines.extend(["", "Next action:"])
        for item in status_payload["next_action"]:
            report_lines.append(f"- {item}")

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Saved decision artifact status JSON to {status_path}")
    print(f"Saved decision artifact report to {report_path}")

    return {
        "status_payload": status_payload,
        "status_path": status_path,
        "report_path": report_path,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Ensure Phase A threshold/tuning decision artifacts exist or explain blockers."
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory containing and receiving Phase A artifacts. Default: output",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing per-ticker OHLCV CSV files. Default: data",
    )
    parser.add_argument(
        "--metadata-file",
        default=None,
        help="Optional ticker metadata CSV. Example: data/ticker_metadata.csv",
    )
    parser.add_argument(
        "--thresholds",
        nargs="*",
        type=float,
        default=[1.5, 2.0, 2.5, 3.0],
        help="Optional threshold sweep values. Default: 1.5 2.0 2.5 3.0",
    )
    parser.add_argument(
        "--hold-period",
        type=int,
        default=5,
        help="Holding period used by the threshold sweep and evaluator fallback. Default: 5",
    )
    parser.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Allow overlapping trades in threshold/evaluator fallback runs.",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=8,
        help="Minimum trade floor used by the threshold sweep. Default: 8",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate prerequisites and artifacts; do not try to build missing outputs.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)

    try:
        result = ensure_phase_a_decision_artifacts(
            output_dir=Path(args.output_dir),
            data_dir=Path(args.data_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            thresholds=args.thresholds,
            hold_period=args.hold_period,
            allow_overlap=args.allow_overlap,
            min_trades=args.min_trades,
            build_missing=not args.validate_only,
        )
    except EnsureDecisionArtifactsCliError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(f"Unexpected decision-artifact resolution failure: {exc}")
        return 1

    payload = result["status_payload"]
    print(f"Threshold decision valid: {payload['threshold_decision_valid']}")
    print(f"Tuning decision valid: {payload['tuning_decision_valid']}")
    print(f"All decisions ready: {payload['all_required_decisions_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
