<?php

namespace App\Services\Trading;

use Illuminate\Support\Carbon;

class TradingDecisionService
{
    public function __construct(
        protected DecisionEvidenceService $evidenceService,
        protected ?array $config = null,
        protected ?ConfidenceEngineService $confidenceEngine = null,
        protected ?ReasonEngineService $reasonEngine = null,
        protected ?RiskEngineService $riskEngine = null,
        protected ?TradePlanService $tradePlanService = null,
        protected ?ActionCandidateService $actionCandidateService = null,
        protected ?ActionSelectionService $actionSelectionService = null,
        protected ?ActionPromotionService $actionPromotionService = null,
    ) {
        $this->config ??= config('trading_research.decision');
        $this->confidenceEngine ??= new ConfidenceEngineService();
        $this->reasonEngine ??= new ReasonEngineService();
        $this->riskEngine ??= new RiskEngineService();
        $this->tradePlanService ??= new TradePlanService();
        $this->actionCandidateService ??= new ActionCandidateService();
        $this->actionSelectionService ??= new ActionSelectionService();
        $this->actionPromotionService ??= new ActionPromotionService();
    }

    public function decide(array $input): array
    {
        $ticker = strtoupper((string) ($input['ticker'] ?? ''));
        $decisionAtRaw = (string) ($input['decision_at'] ?? '');
        $decisionAt = $this->parseTime($decisionAtRaw);
        $reasonCodes = [];
        $reasons = [];
        $warnings = [];
        $blockers = [];
        $gates = [];
        $evidence = [];

        [$decisionScope, $positionContext, $positionStatus, $openTradeIdentity, $openTradeValid] = $this->positionContext($input['open_trade'] ?? null, $ticker);
        if ($positionContext === 'open_trade') {
            $this->addReason($reasonCodes, $reasons, $warnings, 'OPEN_TRADE_PRESENT', 'position', 'warning', 'Open trade is present.');
            $this->addReason($reasonCodes, $reasons, $blockers, 'POSITION_MANAGEMENT_NOT_IMPLEMENTED', 'position', 'blocking', 'Position management is not implemented.');
        } elseif ($positionContext === 'invalid_open_trade') {
            $this->addReason($reasonCodes, $reasons, $blockers, 'OPEN_TRADE_INVALID', 'position', 'blocking', 'Open trade input is invalid.');
        }

        $inputValid = $ticker !== '' && $decisionAt !== null && in_array($ticker, $this->config['supported_tickers'], true) && $openTradeValid;
        if (! $inputValid) {
            $this->addReason($reasonCodes, $reasons, $blockers, in_array($ticker, $this->config['supported_tickers'], true) ? 'PREDICTION_INVALID' : 'UNSUPPORTED_TICKER', 'input_validity', 'blocking', 'Decision input is invalid or ticker is unsupported.');
        }
        $gates[] = $this->gate('input_validity', true, $inputValid, $inputValid ? 'passed' : 'blocking', $inputValid ? 'INPUT_VALID' : 'PREDICTION_INVALID');

        $predictionNormalization = $this->normalizePredictions($input, $decisionAt);
        $predictionSnapshots = $predictionNormalization['snapshots'];
        foreach ($predictionNormalization['warnings'] as $code => $message) {
            $this->addReason($reasonCodes, $reasons, $warnings, $code, 'prediction', 'warning', $message);
        }
        foreach ($predictionNormalization['blockers'] as $code => $message) {
            $this->addReason($reasonCodes, $reasons, $blockers, $code, 'prediction', 'blocking', $message);
        }
        $predictionAvailable = $predictionSnapshots !== [] && collect($predictionSnapshots)->contains(fn ($p) => $p['available']);
        if (! $predictionAvailable) {
            $this->addReason($reasonCodes, $reasons, $blockers, 'PREDICTION_UNAVAILABLE', 'prediction', 'blocking', 'Prediction snapshot is unavailable.');
        }
        $gates[] = $this->gate('prediction_availability', true, $predictionAvailable, $predictionAvailable ? 'passed' : 'blocking', $predictionAvailable ? 'PREDICTION_AVAILABLE' : 'PREDICTION_UNAVAILABLE');
        $predictionValid = $predictionNormalization['valid'] && $predictionAvailable;
        $gates[] = $this->gate('prediction_validity', true, $predictionValid, $predictionValid ? 'passed' : 'blocking', $predictionValid ? 'PREDICTION_VALID' : 'PREDICTION_INVALID');
        $fresh = $predictionValid && collect($predictionSnapshots)->every(fn ($p) => $p['freshness_status'] === 'fresh');
        if (! $fresh && $predictionAvailable) {
            $this->addReason($reasonCodes, $reasons, $blockers, 'PREDICTION_STALE', 'prediction', 'blocking', 'One or more predictions are stale or timestamp-invalid.');
        }
        $gates[] = $this->gate('prediction_freshness', true, $fresh, $fresh ? 'passed' : 'blocking', $fresh ? 'PREDICTION_FRESH' : 'PREDICTION_STALE');

        $predictionEvidence = $this->predictionEvidence($predictionSnapshots);
        foreach ($predictionEvidence['reason_codes'] as $code) {
            $supportivePredictionCodes = ['DIRECTIONAL_PREDICTION_AVAILABLE', 'REGIME_PREDICTION_AVAILABLE'];
            $severity = in_array($code, $supportivePredictionCodes, true) ? 'supportive' : 'warning';
            $this->addReason($reasonCodes, $reasons, $warnings, $code, 'prediction_evidence', $severity, str_replace('_', ' ', strtolower($code)).'.');
        }
        if ($predictionEvidence['conflict_status'] === 'conflicting') {
            $this->addReason($reasonCodes, $reasons, $blockers, 'PREDICTION_CONFLICT', 'prediction_evidence', 'blocking', 'Directional predictions are contradictory.');
            $predictionValid = false;
        }

        $registryQueried = $inputValid;
        if ($registryQueried) {
            $evidence = $this->evidenceService->resolve($ticker);
        }
        $gates[] = $this->gate('registry_availability', $inputValid, $registryQueried && $evidence !== [], $registryQueried && $evidence !== [] ? 'passed' : 'blocking', $registryQueried ? 'REGISTRY_AVAILABLE' : 'REGISTRY_SKIPPED');
        $gates[] = $this->gate('registry_integrity', $registryQueried, $registryQueried ? true : null, $registryQueried ? 'passed' : 'not_evaluated', $registryQueried ? 'REGISTRY_INTEGRITY_CHECKED' : 'REGISTRY_SKIPPED');

        $researchOk = $registryQueried && $evidence !== [];
        $partialResearch = false;
        foreach ($this->config['required_research_artifacts'] as $type) {
            if ($evidence[$type]['latest_research_available'] ?? false) {
                $partialResearch = true;
            } else {
                $researchOk = false;
            }
        }
        if ($researchOk) {
            $this->addReason($reasonCodes, $reasons, $warnings, 'RESEARCH_ARTIFACTS_AVAILABLE', 'artifact_availability', 'informational', 'Required research artifacts are available.');
        }
        $gates[] = $this->gate('research_artifact_availability', $registryQueried, $researchOk, $researchOk ? 'passed' : 'blocking', $researchOk ? 'RESEARCH_ARTIFACTS_AVAILABLE' : 'RESEARCH_ARTIFACT_MISSING');

        $decisionOk = $registryQueried && $evidence !== [];
        foreach ($this->config['required_decision_artifacts'] as $type) {
            if (! ($evidence[$type]['latest_decision_available'] ?? false)) {
                $decisionOk = false;
                $this->addReason($reasonCodes, $reasons, $blockers, $type === 'tp_optimizer' ? 'NO_DECISION_USABLE_TP' : 'NO_DECISION_USABLE_SL', 'artifact_usability', 'blocking', strtoupper(str_replace('_optimizer', '', $type)).' research exists but is not decision-usable.', $type, $evidence[$type]['latest_valid'] ?? null);
            }
        }
        if (! ($evidence['reentry_research']['latest_decision_available'] ?? false)) {
            $this->addReason($reasonCodes, $reasons, $warnings, 'NO_DECISION_USABLE_REENTRY', 'artifact_usability', 'warning', 'Re-entry research is not decision-usable.', 'reentry_research', $evidence['reentry_research']['latest_valid'] ?? null);
        }
        if (! $decisionOk && $researchOk) {
            $this->addReason($reasonCodes, $reasons, $warnings, 'RESEARCH_ONLY_EVIDENCE', 'artifact_usability', 'warning', 'Evidence is research-only and cannot produce trading action.');
        }
        $gates[] = $this->gate('decision_artifact_usability', $registryQueried, $decisionOk, $decisionOk ? 'passed' : 'blocking', $decisionOk ? 'DECISION_ARTIFACTS_AVAILABLE' : 'NO_DECISION_USABLE_ARTIFACT');

        $selectedOk = $decisionOk;
        foreach (['tp_optimizer' => 'SELECTED_TP_UNAVAILABLE', 'sl_optimizer' => 'SELECTED_SL_UNAVAILABLE', 'reentry_research' => 'SELECTED_REENTRY_UNAVAILABLE'] as $type => $selectedCode) {
            if (($evidence[$type]['latest_valid_available'] ?? false) && ! ($evidence[$type]['selected_available'] ?? false)) {
                if ($type !== 'reentry_research') {
                    $selectedOk = false;
                    $this->addReason($reasonCodes, $reasons, $blockers, $selectedCode, 'selected_parameter', 'blocking', 'Selected parameter is unavailable.', $type, $evidence[$type]['latest_valid'] ?? null);
                } else {
                    $this->addReason($reasonCodes, $reasons, $warnings, $selectedCode, 'selected_parameter', 'warning', 'Selected parameter is unavailable.', $type, $evidence[$type]['latest_valid'] ?? null);
                }
            }
        }
        $gates[] = $this->gate('selected_parameter_availability', $registryQueried, $selectedOk, $selectedOk ? 'passed' : 'blocking', $selectedOk ? 'SELECTED_AVAILABLE' : 'SELECTED_PARAMETER_UNAVAILABLE');

        [$dependencyOk, $staleOk, $quarantineOk] = $this->artifactIntegrity($evidence, $reasonCodes, $reasons, $warnings, $blockers);
        $gates[] = $this->gate('dependency_resolution', $registryQueried, $dependencyOk, $dependencyOk ? 'passed' : 'blocking', $dependencyOk ? 'DEPENDENCIES_OK' : 'DEPENDENCY_INVALID');
        $gates[] = $this->gate('staleness', $registryQueried, $staleOk, $staleOk ? 'passed' : 'blocking', $staleOk ? 'NOT_STALE' : 'ARTIFACT_STALE');
        $gates[] = $this->gate('quarantine', $registryQueried, $quarantineOk, $quarantineOk ? 'passed' : 'blocking', $quarantineOk ? 'NOT_QUARANTINED' : 'ARTIFACT_QUARANTINED');

        if ($positionContext === 'open_trade') {
            $gates[] = $this->gate('position_management_capability', true, false, 'blocking', 'POSITION_MANAGEMENT_NOT_IMPLEMENTED');
        } else {
            $gates[] = $this->gate('position_management_capability', true, null, 'not_applicable', 'POSITION_MANAGEMENT_NOT_REQUIRED');
        }

        $evidenceReadiness = $this->evidenceReadiness($inputValid, $predictionValid, $researchOk, $partialResearch, $decisionOk, $selectedOk, $dependencyOk, $staleOk, $quarantineOk);
        if ($evidenceReadiness === 'research_ready') $this->addReason($reasonCodes, $reasons, $warnings, 'EVIDENCE_RESEARCH_READY', 'readiness', 'informational', 'Evidence is research-ready.');
        if ($evidenceReadiness === 'decision_ready') $this->addReason($reasonCodes, $reasons, $warnings, 'EVIDENCE_DECISION_READY', 'readiness', 'informational', 'Evidence is decision-ready.');
        $capabilityReadiness = 'basic_only';
        $actionEligibility = $this->actionEligibility($evidenceReadiness, $positionContext);
        if ($actionEligibility === 'eligible_but_not_supported') {
            $this->addReason($reasonCodes, $reasons, $blockers, 'ACTION_ELIGIBLE_BUT_NOT_SUPPORTED', 'implementation_capability', 'blocking', 'Action evidence is eligible but aggressive action selection is not supported.');
        }
        $this->addReason($reasonCodes, $reasons, $blockers, 'ACTION_SELECTION_NOT_IMPLEMENTED', 'capability', 'blocking', 'Action Selection Engine is not implemented.');
        $this->addReason($reasonCodes, $reasons, $blockers, 'ACTION_CAPABILITY_NOT_IMPLEMENTED', 'capability', 'blocking', 'Aggressive action capability is not implemented.');
        $gates[] = $this->gate('current_implementation_capability', true, false, 'blocking', $actionEligibility === 'eligible_but_not_supported' ? 'ACTION_ELIGIBLE_BUT_NOT_SUPPORTED' : 'ACTION_CAPABILITY_NOT_IMPLEMENTED');

        $action = in_array($evidenceReadiness, ['research_ready', 'decision_ready'], true) ? 'WAIT' : 'NO_TRADE';
        $actionStatus = $this->actionStatus($action, $evidenceReadiness, $actionEligibility);
        $recommendationQuality = $evidenceReadiness === 'decision_ready' ? 'decision_ready' : ($evidenceReadiness === 'research_ready' ? 'research_only' : 'unavailable');
        $this->addReason($reasonCodes, $reasons, $warnings, $action === 'WAIT' ? 'SAFE_DOWNGRADE_WAIT' : 'SAFE_DOWNGRADE_NO_TRADE', 'action_selection', 'informational', "Action downgraded to {$action}.");
        foreach (['CONFIDENCE_ENGINE_NOT_IMPLEMENTED','RISK_ENGINE_NOT_IMPLEMENTED','TRADE_PLAN_NOT_IMPLEMENTED'] as $code) {
            $this->addReason($reasonCodes, $reasons, $warnings, $code, 'implementation', 'informational', str_replace('_', ' ', strtolower($code)).'.');
        }

        $sourceArtifacts = $this->sourceArtifacts($evidence);
        $confidence = $this->confidenceEngine->calculate([
            'decision_at' => $decisionAtRaw,
            'prediction_snapshots' => $predictionSnapshots,
            'prediction_evidence' => $predictionEvidence,
            'artifact_availability' => $this->availabilityOnly($evidence),
            'evidence_readiness' => $evidenceReadiness,
            'capability_readiness' => $capabilityReadiness,
            'action_eligibility' => $actionEligibility,
            'reason_codes' => $this->sortReasonCodes($reasonCodes),
        ]);
        $candidateSeed = hash('sha256', json_encode([
            'ticker' => $ticker,
            'decision_at' => $decisionAtRaw,
            'prediction_snapshots' => $predictionSnapshots,
            'source_artifacts' => $sourceArtifacts,
            'service_contract_version' => $this->config['service_contract_version'],
        ], JSON_UNESCAPED_SLASHES));
        $actionCandidate = $this->actionCandidateService->build([
            'ticker' => $ticker,
            'decision_at' => $decisionAtRaw,
            'prediction_snapshots' => $predictionSnapshots,
            'prediction_evidence' => $predictionEvidence,
            'artifact_availability' => $this->availabilityOnly($evidence),
            'evidence_readiness' => $evidenceReadiness,
            'confidence' => $confidence,
            'position_context' => $positionContext,
            'decision_fingerprint_seed' => $candidateSeed,
        ]);
        $legacyActionPromotion = $this->actionCandidateService->promotion($actionCandidate);
        $this->appendCandidateReasons($reasonCodes, $reasons, $warnings, $blockers, $actionCandidate, $legacyActionPromotion);
        $confidence = $this->confidenceEngine->calculate([
            'decision_at' => $decisionAtRaw,
            'prediction_snapshots' => $predictionSnapshots,
            'prediction_evidence' => $predictionEvidence,
            'artifact_availability' => $this->availabilityOnly($evidence),
            'evidence_readiness' => $evidenceReadiness,
            'capability_readiness' => $capabilityReadiness,
            'action_eligibility' => $actionEligibility,
            'reason_codes' => $this->sortReasonCodes($reasonCodes),
            'action_candidate' => $actionCandidate,
        ]);
        $risk = $this->riskEngine->assess([
            'decision_at' => $decisionAtRaw,
            'artifact_availability' => $this->availabilityOnly($evidence),
            'confidence' => $confidence,
            'action_candidate' => $actionCandidate,
            'selected_parameters' => $input['selected_parameters'] ?? null,
            'entry_reference' => $input['entry_reference'] ?? null,
        ]);
        $tradePlan = $this->tradePlanService->build([
            'decision_at' => $decisionAtRaw,
            'risk' => $risk,
            'action_candidate' => $actionCandidate,
            'position_context' => $positionContext,
            'artifact_availability' => $this->availabilityOnly($evidence),
            'selected_parameters' => $input['selected_parameters'] ?? null,
            'entry_reference' => $input['entry_reference'] ?? null,
        ]);
        $actionSelection = $this->actionSelectionService->select([
            'action_candidate' => $actionCandidate,
            'trade_action_confidence' => $confidence['trade_action_confidence'],
            'decision_risk' => $risk['decision_risk'],
            'trade_plan' => $tradePlan,
            'safety_action' => $action,
        ]);
        $actionPromotion = $this->actionPromotionService->promote(['selection' => $actionSelection]);
        $this->appendContractReasons($reasonCodes, $reasons, $warnings, $blockers, $risk, $tradePlan);
        $this->appendSelectionPromotionReasons($reasonCodes, $reasons, $warnings, $blockers, $actionSelection, $actionPromotion);
        $reasonResult = $this->reasonEngine->build(['base_reasons' => $reasons, 'confidence' => $confidence, 'risk' => $risk, 'trade_plan' => $tradePlan]);
        $canonicalReasons = $reasonResult['reasons'];
        $reasonCodes = $this->sortReasonCodes(array_merge($reasonCodes, array_column($canonicalReasons, 'code')));
        $warnings = collect($canonicalReasons)->whereIn('severity', ['warning'])->values()->all();
        $blockers = collect($canonicalReasons)->whereIn('severity', ['blocking', 'critical'])->values()->all();
        $metadata = [
            'service_version' => 'trading_decision_service_1_2',
            'service_contract_version' => $this->config['service_contract_version'],
            'allowed_actions' => $this->config['allowed_actions'],
            'decision_fingerprint_algorithm' => 'sha256',
        ];
        $fingerprint = $this->fingerprint($ticker, $decisionAtRaw, $predictionSnapshots, $sourceArtifacts, $openTradeIdentity, $confidence, $reasonResult, $risk, $tradePlan, $actionCandidate, $actionPromotion, $actionSelection);
        $metadata['decision_fingerprint'] = $fingerprint;
        $this->addReason($reasonCodes, $canonicalReasons, $warnings, 'DECISION_FINGERPRINT_GENERATED', 'audit', 'informational', 'Deterministic decision fingerprint generated.');
        $reasonResult = $this->reasonEngine->build(['base_reasons' => $canonicalReasons, 'confidence' => $confidence, 'risk' => $risk, 'trade_plan' => $tradePlan]);
        $canonicalReasons = $reasonResult['reasons'];
        $warnings = collect($canonicalReasons)->where('severity', 'warning')->values()->all();
        $blockers = collect($canonicalReasons)->whereIn('severity', ['blocking', 'critical'])->values()->all();
        $reasonCodes = $this->sortReasonCodes(array_column($canonicalReasons, 'code'));

        $result = [
            'schema_version' => $this->config['schema_version'],
            'artifact_type' => 'trading_decision',
            'ticker' => $ticker,
            'decision_at' => $decisionAtRaw,
            'decision_scope' => $decisionScope,
            'position_context' => $positionContext,
            'position_management_status' => $positionStatus,
            'action' => $action,
            'action_status' => $actionStatus,
            'recommendation_quality' => $recommendationQuality,
            'evidence_readiness' => $evidenceReadiness,
            'capability_readiness' => $capabilityReadiness,
            'action_eligibility' => $actionEligibility,
            'action_candidate' => $actionCandidate,
            'action_selection' => $actionSelection,
            'action_promotion' => $actionPromotion,
            'confidence' => $confidence,
            'confidence_status' => $confidence['status'],
            'prediction_snapshots' => $predictionSnapshots,
            'prediction_snapshot' => $predictionSnapshots[0] ?? null,
            'prediction_evidence' => collect($predictionEvidence)->except('reason_codes')->all(),
            'artifact_availability' => $this->availabilityOnly($evidence),
            'evidence' => ['prediction_semantics' => $predictionEvidence, 'safety_gates' => $gates],
            'trade_plan' => $tradePlan,
            'risk' => $risk,
            'gates' => $gates,
            'reason_summary' => $reasonResult['summary'],
            'reason_codes' => $reasonCodes,
            'reasons' => $canonicalReasons,
            'warnings' => $warnings,
            'blockers' => $blockers,
            'source_artifacts' => $sourceArtifacts,
            'metadata' => $metadata,
        ];
        $this->validateDecisionResult($result);
        return $result;
    }

    public function validateDecisionResult(array $result): void
    {
        if (($result['schema_version'] ?? null) !== $this->config['schema_version']) throw new \InvalidArgumentException('invalid decision schema');
        if (($result['artifact_type'] ?? null) !== 'trading_decision') throw new \InvalidArgumentException('invalid decision artifact type');
        foreach (['action'=>'allowed_actions','action_status'=>'action_statuses','recommendation_quality'=>'recommendation_qualities','evidence_readiness'=>'evidence_readiness','capability_readiness'=>'capability_readiness','action_eligibility'=>'action_eligibility','decision_scope'=>'decision_scopes','position_context'=>'position_contexts','position_management_status'=>'position_management_statuses'] as $field => $configKey) {
            if (! in_array($result[$field] ?? null, $this->config[$configKey], true)) throw new \InvalidArgumentException("invalid {$field}");
        }
        if (($result['risk']['schema_version'] ?? null) !== config('trading_risk.risk_schema_version')) throw new \InvalidArgumentException('invalid risk schema');
        if (($result['trade_plan']['schema_version'] ?? null) !== config('trading_trade_plan.trade_plan_schema_version')) throw new \InvalidArgumentException('invalid trade plan schema');
        (new ActionCandidateService())->validateCandidate($result['action_candidate']);
        (new ActionSelectionService())->validateSelection($result['action_selection']);
        (new ActionPromotionService())->validatePromotion($result['action_promotion']);
        if (($result['action_selection']['safety_action'] ?? null) !== ($result['action'] ?? null)) throw new \InvalidArgumentException('safety action mismatch');
        if (($result['action_selection']['selected_candidate'] ?? null) !== null) throw new \InvalidArgumentException('selected candidate disabled');
        if (($result['action_promotion']['promoted_action'] ?? null) !== null || ($result['action_promotion']['executable_action'] ?? null) !== null) throw new \InvalidArgumentException('promoted action disabled');
        (new RiskEngineService())->validateRisk($result['risk']);
        (new TradePlanService())->validateTradePlan($result['trade_plan']);
        if (($result['risk']['decision_risk']['status'] ?? null) === 'unavailable') {
            foreach (['entry_price','take_profit','stop_loss','expected_return_pct','expected_loss_pct','risk_reward_ratio','probability_tp_hit','probability_sl_hit','expected_drawdown_pct','cvar_pct','holding_days'] as $key) {
                if (($result['risk']['decision_risk'][$key] ?? null) !== null) throw new \InvalidArgumentException('unavailable decision risk numeric must be null');
            }
        }
        if (($result['trade_plan']['status'] ?? null) === 'unavailable') {
            foreach ([['entry','price'],['take_profit','price'],['stop_loss','price'],['stop_loss','atr_multiple']] as [$section, $field]) {
                if (($result['trade_plan'][$section][$field] ?? null) !== null) throw new \InvalidArgumentException('unavailable trade plan numeric must be null');
            }
        }
        if (($result['confidence']['schema_version'] ?? null) !== config('trading_confidence.schema_version')) throw new \InvalidArgumentException('invalid confidence schema');
        foreach (['evidence_confidence','safety_decision_confidence','trade_action_confidence'] as $scope) if (! array_key_exists($scope, $result['confidence'])) throw new \InvalidArgumentException('missing confidence scope');
        if (($result['confidence']['trade_action_confidence']['action'] ?? null) === null && ($result['confidence']['trade_action_confidence']['score'] ?? null) !== null) throw new \InvalidArgumentException('trade action confidence requires action identity');
        if (count($result['reason_codes']) !== count(array_unique($result['reason_codes']))) throw new \InvalidArgumentException('duplicate reason codes');
        if ($this->sortReasonCodes($result['reason_codes']) !== $result['reason_codes']) throw new \InvalidArgumentException('reason codes not deterministic');
        foreach ($result['gates'] as $gate) {
            foreach (['gate','evaluated','passed','severity','code','details'] as $key) if (! array_key_exists($key, $gate)) throw new \InvalidArgumentException('invalid gate');
            if ($gate['evaluated'] && $gate['passed'] === false && $gate['severity'] === 'blocking' && ! collect($result['blockers'])->contains('code', $gate['code']) && ! in_array($gate['code'], ['NO_DECISION_USABLE_ARTIFACT','SELECTED_PARAMETER_UNAVAILABLE','DEPENDENCY_INVALID','ARTIFACT_STALE','ARTIFACT_QUARANTINED','ACTION_CAPABILITY_NOT_IMPLEMENTED','ACTION_ELIGIBLE_BUT_NOT_SUPPORTED','RESEARCH_ARTIFACT_MISSING','PREDICTION_INVALID','PREDICTION_STALE','REGISTRY_SKIPPED','REGISTRY_AVAILABLE','REGISTRY_UNAVAILABLE'], true)) throw new \InvalidArgumentException('blocking gate lacks blocker');
        }
        if (($result['metadata']['decision_fingerprint_algorithm'] ?? null) !== 'sha256' || empty($result['metadata']['decision_fingerprint'])) throw new \InvalidArgumentException('missing fingerprint');
    }

    protected function appendContractReasons(array &$reasonCodes, array &$reasons, array &$warnings, array &$blockers, array $risk, array $tradePlan): void
    {
        foreach ($risk['reason_codes'] as $code) {
            $severity = in_array($code, ['DECISION_RISK_UNAVAILABLE','ACTION_CANDIDATE_NOT_AVAILABLE','DECISION_USABLE_TP_UNAVAILABLE','DECISION_USABLE_SL_UNAVAILABLE','SELECTED_TP_REQUIRED_FOR_RISK','SELECTED_SL_REQUIRED_FOR_RISK'], true) ? 'blocking' : 'warning';
            $category = str_starts_with($code, 'RESEARCH_RISK') ? 'risk_evidence' : (str_starts_with($code, 'POSITION_SIZING') ? 'position_sizing' : 'risk');
            $target = $severity === 'blocking' ? $blockers : $warnings;
            $this->addReason($reasonCodes, $reasons, $target, $code, $category, $severity, str_replace('_', ' ', strtolower($code)).'.');
            if ($severity === 'blocking') $blockers = $target; else $warnings = $target;
        }
        foreach ($tradePlan['reason_codes'] as $code) {
            $severity = in_array($code, ['TRADE_PLAN_UNAVAILABLE','ACTION_CANDIDATE_REQUIRED_FOR_PLAN','DECISION_RISK_REQUIRED_FOR_PLAN'], true) ? 'blocking' : 'warning';
            $target = $severity === 'blocking' ? $blockers : $warnings;
            $this->addReason($reasonCodes, $reasons, $target, $code, 'trade_plan', $severity, str_replace('_', ' ', strtolower($code)).'.');
            if ($severity === 'blocking') $blockers = $target; else $warnings = $target;
        }
    }

    protected function appendCandidateReasons(array &$reasonCodes, array &$reasons, array &$warnings, array &$blockers, array $candidate, array $promotion): void
    {
        foreach ($candidate['reason_codes'] as $code) {
            $severity = in_array($code, ['ACTION_CANDIDATE_AVAILABLE_NOT_PROMOTED','ACTION_PROMOTION_NOT_IMPLEMENTED','POSITION_MANAGEMENT_CANDIDATE_NOT_IMPLEMENTED','DECISION_USABLE_TP_REQUIRED_FOR_CANDIDATE','DECISION_USABLE_SL_REQUIRED_FOR_CANDIDATE','SELECTED_TP_REQUIRED_FOR_CANDIDATE','SELECTED_SL_REQUIRED_FOR_CANDIDATE','DIRECTIONAL_SIGNAL_NOT_ELIGIBLE'], true) ? 'blocking' : 'warning';
            $target = $severity === 'blocking' ? $blockers : $warnings;
            $this->addReason($reasonCodes, $reasons, $target, $code, 'action_candidate', $severity, str_replace('_', ' ', strtolower($code)).'.');
            if ($severity === 'blocking') $blockers = $target; else $warnings = $target;
        }
        foreach ($promotion['reason_codes'] as $code) {
            $this->addReason($reasonCodes, $reasons, $blockers, $code, 'action_promotion', 'blocking', str_replace('_', ' ', strtolower($code)).'.');
        }
    }

    protected function appendSelectionPromotionReasons(array &$reasonCodes, array &$reasons, array &$warnings, array &$blockers, array $selection, array $promotion): void
    {
        foreach (array_merge($selection['reason_codes'], $promotion['reason_codes']) as $code) {
            $severity = in_array($code, ['SAFETY_ACTION_WAIT_SELECTED','SAFETY_ACTION_NO_TRADE_SELECTED','CANDIDATE_ELIGIBLE_BUT_NOT_SELECTABLE'], true) ? 'warning' : 'blocking';
            $target = $severity === 'blocking' ? $blockers : $warnings;
            $this->addReason($reasonCodes, $reasons, $target, $code, str_starts_with($code, 'ACTION_PROMOTION') || str_starts_with($code, 'PROMOTED') || str_starts_with($code, 'EXEC') ? 'action_promotion' : 'action_selection', $severity, str_replace('_', ' ', strtolower($code)).'.');
            if ($severity === 'blocking') $blockers = $target; else $warnings = $target;
        }
    }

    protected function normalizePredictions(array $input, ?Carbon $decisionAt): array
    {
        $hasCollection = array_key_exists('predictions', $input);
        $hasLegacy = array_key_exists('prediction', $input);
        $raw = [];
        $warnings = [];
        $blockers = [];
        if ($hasCollection) {
            $raw = is_array($input['predictions']) ? $input['predictions'] : [];
            if ($hasLegacy && $input['prediction'] !== ($raw[0] ?? null)) $blockers['CONFLICTING_PREDICTION_INPUTS'] = 'Legacy prediction and predictions collection conflict.';
        } elseif ($hasLegacy) {
            $raw = [is_array($input['prediction']) ? $input['prediction'] : []];
            $warnings['LEGACY_PREDICTION_INPUT_DEPRECATED'] = 'Single prediction input is deprecated; use predictions collection.';
        }
        $snapshots = [];
        $identities = [];
        foreach ($raw as $prediction) {
            $role = $prediction['semantic_role'] ?? $this->inferRole($prediction);
            $value = $prediction['predicted_value'] ?? $prediction['predicted_direction'] ?? $prediction['predicted_regime'] ?? null;
            $semantic = $this->normalizePredictionSemantics($role, $value);
            $generatedAt = $prediction['generated_at'] ?? null;
            $identity = implode('|', [(string) ($prediction['variant'] ?? ''), (string) $role, (string) $generatedAt]);
            if (isset($identities[$identity])) $blockers['DUPLICATE_PREDICTION'] = 'Duplicate prediction identity.';
            $identities[$identity] = true;
            $prob = $prediction['probability'] ?? null;
            $itemWarnings = [];
            if (! in_array($role, $this->config['semantic_roles'], true) || $semantic === 'unknown') $itemWarnings[] = 'unknown semantic';
            if ($prob !== null && (! is_numeric($prob) || $prob < 0 || $prob > 1)) $blockers['PREDICTION_INVALID'] = 'Prediction probability is invalid.';
            $fresh = $this->freshnessStatus($generatedAt, $decisionAt);
            $snapshots[] = ['variant'=>$prediction['variant'] ?? null,'semantic_role'=>$role,'raw_predicted_value'=>$value,'normalized_semantic'=>$semantic,'probability'=>$prob,'generated_at'=>$generatedAt,'freshness_status'=>$fresh,'schema_version'=>$prediction['schema_version'] ?? null,'source_identifier'=>$prediction['source_identifier'] ?? null,'available'=>(bool)($prediction['available'] ?? false),'warnings'=>$itemWarnings,'identity'=>$identity];
        }
        if ($snapshots === []) $blockers['PREDICTION_UNAVAILABLE'] = 'No prediction snapshots provided.';
        if (collect($snapshots)->contains(fn($p)=>$p['normalized_semantic']==='unknown')) $blockers['UNKNOWN_PREDICTION_SEMANTICS'] = 'Unknown prediction semantics.';
        return ['snapshots'=>$this->sortPredictionSnapshots($snapshots),'valid'=>$blockers === [],'warnings'=>$warnings,'blockers'=>$blockers];
    }

    protected function inferRole(array $prediction): string
    {
        if (! empty($prediction['predicted_direction'])) return 'directional';
        if (! empty($prediction['predicted_regime'])) return 'regime';
        return 'unknown';
    }

    protected function normalizePredictionSemantics(string $role, mixed $value): string
    {
        $value = strtolower((string) $value);
        return match ($role) {
            'directional' => ['up'=>'directional_up','down'=>'directional_down','neutral'=>'directional_neutral'][$value] ?? 'unknown',
            'regime' => ['move'=>'regime_move','no_move'=>'regime_no_move'][$value] ?? 'unknown',
            default => 'unknown',
        };
    }

    protected function predictionEvidence(array $snapshots): array
    {
        $directional = collect($snapshots)->where('semantic_role','directional')->values();
        $regime = collect($snapshots)->where('semantic_role','regime')->values();
        $directionalSemantics = $directional->pluck('normalized_semantic')->filter(fn($v)=>$v!=='unknown')->unique()->values();
        $codes = [];
        if ($snapshots !== [] && count($snapshots) > 1) $codes[] = 'MULTIPLE_PREDICTIONS_AVAILABLE';
        if ($directional->isNotEmpty()) $codes[] = 'DIRECTIONAL_PREDICTION_AVAILABLE';
        if ($regime->isNotEmpty()) $codes[] = 'REGIME_PREDICTION_AVAILABLE';
        if ($directional->isEmpty() && $regime->isNotEmpty()) $codes[] = 'REGIME_ONLY_NOT_DIRECTIONAL';
        if ($directional->isEmpty()) $codes[] = 'DIRECTIONAL_PREDICTION_MISSING';
        $conflict = $directionalSemantics->count() > 1;
        return ['directional_available'=>$directional->isNotEmpty(),'regime_available'=>$regime->isNotEmpty(),'directional_semantic'=>$directionalSemantics->first(),'regime_semantic'=>$regime->pluck('normalized_semantic')->filter(fn($v)=>$v!=='unknown')->first(),'agreement_status'=>$directional->isNotEmpty() && $regime->isNotEmpty() ? 'supportive' : ($directional->isNotEmpty() ? 'not_applicable' : 'insufficient'),'conflict_status'=>$conflict ? 'conflicting' : 'none','quality_status'=>$snapshots === [] ? 'unavailable' : 'available','reason_codes'=>$codes];
    }

    protected function positionContext(mixed $openTrade, string $ticker): array
    {
        if ($openTrade === null) return ['entry_evaluation','no_open_trade','not_required',null,true];
        if (! is_array($openTrade)) return ['unsupported','invalid_open_trade','blocked',null,false];
        $identity = $openTrade['id'] ?? $openTrade['trade_id'] ?? null;
        $valid = strtoupper((string)($openTrade['ticker'] ?? '')) === $ticker && ($openTrade['status'] ?? null) === 'open' && is_numeric($openTrade['entry_price'] ?? null) && (float)$openTrade['entry_price'] > 0 && ! empty($openTrade['entry_date']);
        return $valid ? ['position_management','open_trade','not_implemented',(string)$identity,true] : ['unsupported','invalid_open_trade','blocked',(string)$identity,false];
    }

    protected function artifactIntegrity(array $evidence, array &$reasonCodes, array &$reasons, array &$warnings, array &$blockers): array
    {
        $dependencyOk = $staleOk = $quarantineOk = true;
        foreach ($evidence as $type=>$artifactEvidence) {
            foreach ($artifactEvidence['dependency_status'] ?? [] as $status) {
                if (in_array($status, $this->config['dependency_blocker_statuses'], true)) { $dependencyOk=false; $this->addReason($reasonCodes,$reasons,$blockers,$status==='checksum_mismatch'?'DEPENDENCY_CHECKSUM_MISMATCH':'DEPENDENCY_UNRESOLVED','dependency','blocking','Artifact dependency failed resolution.',$type,$artifactEvidence['latest_valid']??null); }
                elseif (in_array($status,['unresolved','missing_file'],true)) $this->addReason($reasonCodes,$reasons,$warnings,'DEPENDENCY_UNRESOLVED','dependency','warning','Artifact dependency is unresolved.',$type,$artifactEvidence['latest_valid']??null);
            }
            if ($artifactEvidence['is_stale'] ?? false) { $staleOk=false; $this->addReason($reasonCodes,$reasons,$blockers,'ARTIFACT_STALE','artifact_integrity','blocking','Artifact is stale.',$type,$artifactEvidence['latest_valid']??null); }
            if ($artifactEvidence['is_quarantined'] ?? false) { $quarantineOk=false; $this->addReason($reasonCodes,$reasons,$blockers,'ARTIFACT_QUARANTINED','artifact_integrity','blocking','Artifact is quarantined.',$type,$artifactEvidence['latest_valid']??null); }
            foreach ($artifactEvidence['warnings'] ?? [] as $warning) $this->warningFromArtifact($warning,$reasonCodes,$reasons,$warnings,$type,$artifactEvidence['latest_valid']??null);
        }
        return [$dependencyOk,$staleOk,$quarantineOk];
    }

    protected function evidenceReadiness(bool $inputValid, bool $predictionValid, bool $researchOk, bool $partialResearch, bool $decisionOk, bool $selectedOk, bool $dependencyOk, bool $staleOk, bool $quarantineOk): string
    {
        if (! $inputValid || ! $predictionValid || ! $dependencyOk || ! $staleOk || ! $quarantineOk) return 'invalid';
        if ($decisionOk && $selectedOk) return 'decision_ready';
        if ($researchOk) return 'research_ready';
        return $partialResearch ? 'partial' : 'unavailable';
    }

    protected function actionEligibility(string $readiness, string $positionContext): string
    {
        if ($positionContext === 'invalid_open_trade') return 'ineligible';
        if ($positionContext === 'open_trade') return 'blocked';
        return $readiness === 'decision_ready' ? 'eligible_but_not_supported' : ($readiness === 'research_ready' ? 'blocked' : 'ineligible');
    }

    protected function actionStatus(string $action, string $readiness, string $eligibility): string
    {
        if ($eligibility === 'eligible_but_not_supported') return 'unsupported';
        if ($action === 'NO_TRADE') return 'blocked';
        return $readiness === 'research_ready' ? 'safe_downgrade' : 'blocked';
    }

    protected function freshnessStatus(?string $generatedAt, ?Carbon $decisionAt): string
    {
        if (! $generatedAt || ! $decisionAt) return 'invalid';
        try { $generated = Carbon::parse($generatedAt); } catch (\Throwable) { return 'invalid'; }
        return $generated->lessThanOrEqualTo($decisionAt) && $generated->greaterThanOrEqualTo($decisionAt->copy()->subMinutes((int)$this->config['prediction_freshness_minutes'])) ? 'fresh' : 'stale';
    }

    protected function parseTime(string $value): ?Carbon { try { return $value !== '' ? Carbon::parse($value) : null; } catch (\Throwable) { return null; } }
    protected function gate(string $gate, bool $evaluated, ?bool $passed, string $severity, string $code, array $details=[]): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function addReason(array &$codes, array &$reasons, array &$target, string $code, string $category, string $severity, string $message, ?string $artifactType=null, ?array $artifact=null): void { $codes[]=$code; $reason=['code'=>$code,'category'=>$category,'severity'=>$severity,'message'=>$message,'source'=>['artifact_type'=>$artifactType,'artifact_id'=>$artifact['id']??null,'schema_version'=>$artifact['schema_version']??null]]; $reasons[]=$reason; $target[]=$reason; }
    protected function warningFromArtifact(string $warning, array &$codes, array &$reasons, array &$warnings, string $type, ?array $artifact): void { foreach(['high_unclassified_rate'=>'HIGH_UNCLASSIFIED_RATE','ATR family unavailable'=>'ATR_FAMILY_UNAVAILABLE','extreme_winner_dependency'=>'EXTREME_WINNER_DEPENDENCY'] as $needle=>$code) if(str_contains($warning,$needle)) $this->addReason($codes,$reasons,$warnings,$code,'artifact_warning','warning',$warning,$type,$artifact); }
    protected function availabilityOnly(array $evidence): array { return collect($evidence)->map(fn($item)=>collect($item)->except(['latest_valid','latest_research','latest_decision'])->all())->all(); }
    protected function sourceArtifacts(array $evidence): array { return collect($evidence)->map(fn($item)=>['latest_valid'=>$item['latest_valid']??null,'latest_research_usable'=>$item['latest_research']??null,'latest_decision_usable'=>$item['latest_decision']??null])->all(); }
    protected function sortPredictionSnapshots(array $snapshots): array { usort($snapshots, fn($a,$b)=>[$a['variant'],$a['semantic_role'],$a['generated_at']] <=> [$b['variant'],$b['semantic_role'],$b['generated_at']]); return $snapshots; }
    protected function uniqueReasons(array $reasons): array { return collect($reasons)->unique('code')->values()->all(); }
    protected function sortReasonCodes(array $codes): array { $order=array_flip($this->config['reason_codes']); $unique=array_values(array_unique($codes)); usort($unique, fn($a,$b)=>($order[$a]??999)<=>($order[$b]??999) ?: strcmp($a,$b)); return $unique; }
    protected function fingerprint(string $ticker, string $decisionAt, array $predictions, array $sourceArtifacts, ?string $openTradeIdentity, array $confidence = [], array $reasonResult = [], array $risk = [], array $tradePlan = [], array $actionCandidate = [], array $actionPromotion = [], array $actionSelection = []): string { $actionRisk=$risk['action_specific_risk']??[]; $ref=$tradePlan['reference_plan']??[]; $payload=['ticker'=>$ticker,'decision_at'=>$decisionAt,'prediction_snapshots'=>$predictions,'source_artifacts'=>$sourceArtifacts,'open_trade_identity'=>$openTradeIdentity,'schema_version'=>$this->config['schema_version'],'service_contract_version'=>$this->config['service_contract_version'],'action_candidate_schema'=>$actionCandidate['schema_version']??null,'candidate_status'=>$actionCandidate['status']??null,'candidate_id'=>$actionCandidate['candidate_id']??null,'candidate_intent'=>$actionCandidate['intent']??null,'candidate_eligibility'=>$actionCandidate['eligibility']??null,'candidate_gates'=>$actionCandidate['eligibility_gates']??[],'selection_schema'=>$actionSelection['schema_version']??null,'selection_status'=>$actionSelection['status']??null,'selection_eligibility'=>$actionSelection['selection_eligibility']??null,'selected_candidate_id'=>$actionSelection['selected_candidate']['candidate_id']??null,'safety_action'=>$actionSelection['safety_action']??null,'promotion_schema'=>$actionPromotion['schema_version']??null,'promotion_status'=>$actionPromotion['status']??null,'promotion_eligibility'=>$actionPromotion['promotion_eligibility']??null,'promoted_action'=>$actionPromotion['promoted_action']??null,'executable_action'=>$actionPromotion['executable_action']??null,'confidence_schema_version'=>$confidence['schema_version']??null,'confidence_weight_profile'=>$confidence['calculation']['weight_profile']??null,'evidence_confidence_final'=>$confidence['evidence_confidence']['score']??null,'safety_decision_confidence'=>$confidence['safety_decision_confidence']??null,'trade_action_confidence_status'=>$confidence['trade_action_confidence']['status']??null,'confidence_components'=>$confidence['evidence_confidence']['components']??[],'risk_schema_version'=>$risk['schema_version']??null,'action_risk_schema'=>$actionRisk['schema_version']??null,'action_risk_status'=>$actionRisk['status']??null,'action_risk_eligibility'=>$actionRisk['eligibility']??null,'action_risk_candidate_id'=>$actionRisk['candidate_id']??null,'action_risk_metrics'=>$actionRisk['metrics']??[],'action_risk_method'=>$actionRisk['calculation']['method']??null,'selected_parameter_sources'=>$actionRisk['parameter_snapshot']??null,'research_risk_status'=>$risk['research_risk_evidence']['status']??null,'decision_risk_status'=>$risk['decision_risk']['status']??null,'position_sizing_status'=>$risk['position_sizing']['status']??null,'capital_risk_status'=>$risk['capital_risk']['status']??null,'trade_plan_schema_version'=>$tradePlan['schema_version']??null,'reference_plan_schema'=>$ref['schema_version']??null,'reference_plan_status'=>$ref['status']??null,'reference_plan_eligibility'=>$ref['eligibility']??null,'entry_reference'=>$ref['entry']??null,'tp_reference'=>$ref['take_profit']['reference_price']??null,'sl_reference'=>$ref['stop_loss']['reference_price']??null,'execution_readiness'=>$tradePlan['execution_readiness']['status']??null,'executable'=>$tradePlan['execution_readiness']['executable']??null,'trade_plan_status'=>$tradePlan['status']??null,'trade_plan_eligibility'=>$tradePlan['eligibility']??null,'risk_reason_codes'=>$risk['reason_codes']??[],'trade_plan_reason_codes'=>$tradePlan['reason_codes']??[],'reason_schema_version'=>$reasonResult['schema_version']??null,'primary_reason_codes'=>$reasonResult['summary']['primary_reason_codes']??[]]; return hash('sha256', json_encode($payload, JSON_UNESCAPED_SLASHES|JSON_PRESERVE_ZERO_FRACTION)); }
}
