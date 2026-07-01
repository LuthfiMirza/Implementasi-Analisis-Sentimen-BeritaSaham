<?php

namespace App\Services\Trading;

use Carbon\Carbon;

class TradePlanMaterializationService
{
    public function __construct(protected ?array $config = null)
    {
        $this->config ??= config('trading_trade_plan');
    }

    public function materialize(array $context): array
    {
        $candidate = $context['action_candidate'] ?? null;
        $parameters = $context['selected_parameters'] ?? null;
        $risk = $context['action_risk'] ?? null;
        $entry = $context['entry_reference'] ?? null;
        $decisionAt = $context['decision_at'] ?? null;
        $codes = [];$warnings=[];$blockers=[];$gates=[];
        $metrics = $risk['metrics'] ?? [];

        $candidateAvailable = is_array($candidate);
        $candidateReady = ($candidate['status'] ?? null) === 'candidate_ready';
        $supportedIntent = in_array($candidate['intent'] ?? null, $this->config['supported_intents'], true);
        $paramAvailable = is_array($parameters);
        $riskAvailable = is_array($risk);
        $riskEvaluated = ($risk['status'] ?? null) === 'evaluated';
        $entryAvailable = is_array($entry);

        $gates[]=$this->gate('candidate_available',true,$candidateAvailable,$candidateAvailable?'passed':'blocking',$candidateAvailable?'ACTION_CANDIDATE_READY':'TRADE_PLAN_CANDIDATE_REQUIRED'); if(!$candidateAvailable)$this->add($codes,$blockers,'TRADE_PLAN_CANDIDATE_REQUIRED');
        $gates[]=$this->gate('candidate_valid',$candidateAvailable,$candidateAvailable?(($candidate['schema_version']??null)===config('trading_action.schema_version')):null,'passed','CANDIDATE_SCHEMA_VALID');
        $gates[]=$this->gate('candidate_ready',$candidateAvailable,$candidateAvailable?$candidateReady:null,$candidateReady?'passed':'blocking',$candidateReady?'CANDIDATE_READY':'TRADE_PLAN_CANDIDATE_NOT_READY'); if($candidateAvailable&&!$candidateReady)$this->add($codes,$blockers,'TRADE_PLAN_CANDIDATE_NOT_READY');
        $gates[]=$this->gate('supported_intent',$candidateAvailable,$candidateAvailable?$supportedIntent:null,$supportedIntent?'passed':'blocking',$supportedIntent?'TRADE_PLAN_INTENT_SUPPORTED':'TRADE_PLAN_CANDIDATE_NOT_READY');
        $gates[]=$this->gate('selected_parameters_available',true,$paramAvailable,$paramAvailable?'passed':'blocking',$paramAvailable?'SELECTED_PARAMETERS_AVAILABLE':'TRADE_PLAN_SELECTED_PARAMETERS_REQUIRED'); if(!$paramAvailable)$this->add($codes,$blockers,'TRADE_PLAN_SELECTED_PARAMETERS_REQUIRED');
        $paramValid = $paramAvailable && ($parameters['schema_version']??null)==='trading_selected_parameters_v1';
        $gates[]=$this->gate('selected_parameters_valid',$paramAvailable,$paramAvailable?$paramValid:null,$paramValid?'passed':'blocking',$paramValid?'SELECTED_PARAMETERS_VALID':'TRADE_PLAN_SELECTED_PARAMETERS_REQUIRED');
        $identity = $paramAvailable && $candidateAvailable && ($parameters['candidate_id']??null)===($candidate['candidate_id']??null) && ($parameters['candidate_intent']??null)===($candidate['intent']??null);
        $gates[]=$this->gate('candidate_identity_match',$paramAvailable&&$candidateAvailable,$paramAvailable&&$candidateAvailable?$identity:null,$identity?'passed':'blocking',$identity?'CANDIDATE_IDENTITY_MATCH':'TRADE_PLAN_IDENTITY_MISMATCH'); if($paramAvailable&&$candidateAvailable&&!$identity)$this->add($codes,$blockers,'TRADE_PLAN_IDENTITY_MISMATCH');

        foreach(['take_profit'=>'tp_source_decision_usable','stop_loss'=>'sl_source_decision_usable'] as $key=>$gate){$src=$parameters[$key]['source_artifact']??[];$ok=($src['usage_tier']??null)==='decision_usable';$gates[]=$this->gate($gate,$paramAvailable,$paramAvailable?$ok:null,$ok?'passed':'blocking',$ok?strtoupper($gate).'_OK':'TRADE_PLAN_RESEARCH_PARAMETER_REJECTED'); if($paramAvailable&&!$ok)$this->add($codes,$blockers,'TRADE_PLAN_RESEARCH_PARAMETER_REJECTED');}
        $deps=$this->sourcesOk($parameters,fn($s)=>collect($s['dependency_status']??['resolved'])->every(fn($v)=>$v==='resolved'));
        $fresh=$this->sourcesOk($parameters,fn($s)=>!($s['stale']??false));
        $quar=$this->sourcesOk($parameters,fn($s)=>!($s['quarantined']??false));
        foreach([['source_dependencies_resolved',$deps,'TRADE_PLAN_SELECTED_PARAMETERS_REQUIRED'],['source_fresh',$fresh,'TRADE_PLAN_SELECTED_PARAMETERS_REQUIRED'],['source_not_quarantined',$quar,'TRADE_PLAN_SELECTED_PARAMETERS_REQUIRED']] as [$g,$ok,$code]){$gates[]=$this->gate($g,$paramAvailable,$paramAvailable?$ok:null,$ok?'passed':'blocking',$ok?strtoupper($g).'_OK':$code); if($paramAvailable&&!$ok)$this->add($codes,$blockers,$code);}

        $gates[]=$this->gate('action_risk_available',true,$riskAvailable,$riskAvailable?'passed':'blocking',$riskAvailable?'ACTION_RISK_AVAILABLE':'TRADE_PLAN_ACTION_RISK_REQUIRED'); if(!$riskAvailable)$this->add($codes,$blockers,'TRADE_PLAN_ACTION_RISK_REQUIRED');
        $gates[]=$this->gate('action_risk_evaluated',$riskAvailable,$riskAvailable?$riskEvaluated:null,$riskEvaluated?'passed':'blocking',$riskEvaluated?'ACTION_RISK_EVALUATED':'TRADE_PLAN_ACTION_RISK_NOT_EVALUATED'); if($riskAvailable&&!$riskEvaluated)$this->add($codes,$blockers,'TRADE_PLAN_ACTION_RISK_NOT_EVALUATED');
        $riskIdentity=$riskAvailable&&$candidateAvailable&&($risk['candidate_id']??null)===($candidate['candidate_id']??null);
        $gates[]=$this->gate('action_risk_identity_match',$riskAvailable&&$candidateAvailable,$riskAvailable&&$candidateAvailable?$riskIdentity:null,$riskIdentity?'passed':'blocking',$riskIdentity?'RISK_IDENTITY_MATCH':'TRADE_PLAN_IDENTITY_MISMATCH'); if($riskAvailable&&$candidateAvailable&&!$riskIdentity)$this->add($codes,$blockers,'TRADE_PLAN_IDENTITY_MISMATCH');
        $geometryOk=$riskEvaluated&&($metrics['gross_reward_risk_ratio']??null)!==null;
        if ($geometryOk && $paramAvailable) {
            $precision = (int) ($this->config['rounding_precision'] ?? 6);
            $tp = (float) ($parameters['take_profit']['value'] ?? 0);
            $sl = abs((float) ($parameters['stop_loss']['value'] ?? 0));
            $expectedRatio = $sl > 0 ? round($tp / $sl, $precision) : null;
            $geometryOk = round((float) ($metrics['gross_upside_pct'] ?? -1), $precision) === round($tp, $precision)
                && round((float) ($metrics['gross_downside_pct'] ?? -1), $precision) === round($sl, $precision)
                && $expectedRatio !== null
                && round((float) ($metrics['gross_reward_risk_ratio'] ?? -1), $precision) === $expectedRatio;
        }
        $gates[]=$this->gate('risk_geometry_consistency',$riskAvailable,$riskAvailable?$geometryOk:null,$geometryOk?'passed':'blocking',$geometryOk?'RISK_GEOMETRY_CONSISTENT':'TRADE_PLAN_RISK_GEOMETRY_MISMATCH'); if($riskAvailable&&!$geometryOk)$this->add($codes,$blockers,'TRADE_PLAN_RISK_GEOMETRY_MISMATCH');

        $gates[]=$this->gate('entry_reference_available',true,$entryAvailable,$entryAvailable?'passed':'blocking',$entryAvailable?'ENTRY_REFERENCE_AVAILABLE':'TRADE_PLAN_ENTRY_REFERENCE_REQUIRED');
        $entryValid=$entryAvailable&&($entry['schema_version']??null)===$this->config['entry_reference_schema_version']&&($entry['executable']??null)===false&&is_numeric($entry['price']??null)&&$entry['price']>0&&!empty($entry['source']);
        $gates[]=$this->gate('entry_reference_valid',$entryAvailable,$entryAvailable?$entryValid:null,$entryValid?'passed':'blocking',$entryValid?'ENTRY_REFERENCE_VALID':'TRADE_PLAN_ENTRY_REFERENCE_REQUIRED'); if($entryAvailable&&!$entryValid)$this->add($codes,$blockers,'TRADE_PLAN_ENTRY_REFERENCE_REQUIRED');
        $entryIdentity=$entryAvailable&&$candidateAvailable&&($entry['candidate_id']??null)===($candidate['candidate_id']??null)&&($entry['candidate_intent']??null)===($candidate['intent']??null);
        $gates[]=$this->gate('entry_reference_identity_match',$entryAvailable&&$candidateAvailable,$entryAvailable&&$candidateAvailable?$entryIdentity:null,$entryIdentity?'passed':'blocking',$entryIdentity?'ENTRY_IDENTITY_MATCH':'TRADE_PLAN_IDENTITY_MISMATCH'); if($entryAvailable&&$candidateAvailable&&!$entryIdentity)$this->add($codes,$blockers,'TRADE_PLAN_IDENTITY_MISMATCH');
        $entryFresh=$this->entryFresh($entry,$decisionAt);
        $gates[]=$this->gate('entry_reference_freshness',$entryAvailable,$entryAvailable?$entryFresh:null,$entryFresh?'passed':'blocking',$entryFresh?'ENTRY_REFERENCE_FRESH':'TRADE_PLAN_ENTRY_REFERENCE_STALE'); if($entryAvailable&&!$entryFresh)$this->add($codes,$blockers,'TRADE_PLAN_ENTRY_REFERENCE_STALE');

        $baseReady=$candidateReady&&$supportedIntent&&$paramValid&&$identity&&$deps&&$fresh&&$quar&&$riskEvaluated&&$riskIdentity&&$geometryOk;
        $materialized=$baseReady&&$entryValid&&$entryIdentity&&$entryFresh;
        $eligibility=$materialized?'materialized':($baseReady?'entry_reference_unavailable':$this->eligibility($candidate,$parameters,$risk));
        $unavailableEligibilities = ['candidate_not_available', 'candidate_not_ready', 'selected_parameters_unavailable', 'action_risk_unavailable', 'action_risk_not_evaluated'];
        $status=$materialized?'materialized':($baseReady?'parameter_ready':(in_array($eligibility, $unavailableEligibilities, true) ? 'unavailable' : 'blocked'));
        $statusCode = $status === 'materialized'
            ? 'TRADE_PLAN_REFERENCE_MATERIALIZED'
            : ($status === 'parameter_ready' ? 'TRADE_PLAN_PARAMETER_READY' : 'TRADE_PLAN_REFERENCE_UNAVAILABLE');
        if ($status === 'materialized') {
            $this->add($codes, $warnings, $statusCode);
        } else {
            $this->add($codes, $blockers, $statusCode);
        }
        $this->add($codes,$warnings,'TRADE_PLAN_REFERENCE_ONLY');$this->add($codes,$blockers,'TRADE_PLAN_NON_EXECUTABLE');$this->add($codes,$blockers,'TRADE_PLAN_EXECUTION_NOT_IMPLEMENTED');$this->add($codes,$warnings,'TRADE_PLAN_HOLDING_NOT_IMPLEMENTED');$this->add($codes,$warnings,'TRADE_PLAN_REENTRY_NOT_IMPLEMENTED');$this->add($codes,$blockers,'TRADE_PLAN_POSITION_SIZING_NOT_IMPLEMENTED');$this->add($codes,$blockers,'TRADE_PLAN_POSITION_MANAGEMENT_NOT_IMPLEMENTED');
        $gates[]=$this->gate('reference_price_materialization',$baseReady,$baseReady?$materialized:null,$materialized?'passed':'blocking',$materialized?'TRADE_PLAN_REFERENCE_MATERIALIZED':'TRADE_PLAN_ENTRY_REFERENCE_REQUIRED');
        $gates[]=$this->gate('execution_capability',true,false,'blocking','TRADE_PLAN_EXECUTION_NOT_IMPLEMENTED');

        $plan=$this->emptyPlan($status,$eligibility,$candidate,$codes,$warnings,$blockers,$gates,$decisionAt);
        if($baseReady){$plan['take_profit']['status']='parameter_ready';$plan['take_profit']['parameter_type']='percentage';$plan['take_profit']['percentage']=$metrics['take_profit_pct'];$plan['take_profit']['source_artifact']=$parameters['take_profit']['source_artifact'];$plan['stop_loss']['status']='parameter_ready';$plan['stop_loss']['parameter_type']='percentage';$plan['stop_loss']['percentage']=$metrics['stop_loss_pct'];$plan['stop_loss']['source_artifact']=$parameters['stop_loss']['source_artifact'];$plan['risk_geometry']=array_intersect_key($metrics,$plan['risk_geometry']);}
        if($materialized){$plan['entry']=['status'=>'reference_only','reference_price'=>(float)$entry['price'],'price_type'=>$entry['price_type']??null,'observed_at'=>$entry['observed_at'],'source'=>$entry['source']];$plan['take_profit']['status']='reference_only';$plan['take_profit']['reference_price']=$metrics['take_profit_price'];$plan['stop_loss']['status']='reference_only';$plan['stop_loss']['reference_price']=$metrics['stop_loss_price'];$plan['execution']['status']='not_executable';}
        $plan['metadata']=['selected_parameter_schema'=>$parameters['schema_version']??null,'action_risk_schema'=>$risk['schema_version']??null,'risk_calculation_method'=>$risk['calculation']['method']??null,'entry_reference_schema'=>$entry['schema_version']??null,'entry_reference_source'=>$entry['source']??null,'non_executable'=>true,'synthetic_test_only'=>(bool)($parameters['synthetic_test_only']??false)];
        $this->validateReferencePlan($plan);
        return $plan;
    }

    protected function emptyPlan(string $status,string $eligibility,?array $candidate,array $codes,array $warnings,array $blockers,array $gates,?string $decisionAt): array
    { return ['schema_version'=>$this->config['reference_plan_schema_version'],'status'=>$status,'candidate_id'=>$candidate['candidate_id']??null,'candidate_intent'=>$candidate['intent']??null,'plan_scope'=>'reference_non_executable','eligibility'=>$eligibility,'entry'=>['status'=>'unavailable','reference_price'=>null,'price_type'=>null,'observed_at'=>null,'source'=>null],'take_profit'=>['status'=>'unavailable','parameter_type'=>null,'percentage'=>null,'reference_price'=>null,'source_artifact'=>null],'stop_loss'=>['status'=>'unavailable','parameter_type'=>null,'percentage'=>null,'reference_price'=>null,'source_artifact'=>null],'risk_geometry'=>['gross_upside_pct'=>null,'gross_downside_pct'=>null,'gross_reward_risk_ratio'=>null,'gross_profit_per_unit'=>null,'gross_loss_per_unit'=>null],'holding'=>['status'=>'not_implemented','expected_days'=>null,'maximum_days'=>null],'reentry'=>['status'=>'not_implemented','enabled'=>false,'trigger'=>null,'maximum_reentries'=>0],'invalidation'=>['status'=>'contract_only','conditions'=>[]],'execution'=>['status'=>'not_executable','executable'=>false,'order_type'=>null,'quantity'=>null,'time_in_force'=>null,'broker_instruction'=>null,'client_order_id'=>null],'reason_codes'=>$this->ordered($codes),'warnings'=>$this->ordered($warnings),'blockers'=>$this->ordered($blockers),'gates'=>$this->sortGates($gates),'calculation'=>['method'=>'trade_plan_materialization_v1','calculated_at'=>$decisionAt],'metadata'=>[]]; }

    public function validateReferencePlan(array $plan): void
    { if(($plan['schema_version']??null)!==$this->config['reference_plan_schema_version'])throw new \InvalidArgumentException('invalid reference plan schema'); if(!in_array($plan['status']??null,['unavailable','blocked','parameter_ready','materialized','invalid'],true))throw new \InvalidArgumentException('invalid reference plan status'); if(($plan['execution']['executable']??null)!==false)throw new \InvalidArgumentException('reference plan must be non executable'); foreach(['order_type','quantity','time_in_force','broker_instruction','client_order_id'] as $k) if(($plan['execution'][$k]??null)!==null) throw new \InvalidArgumentException('execution fields must be null'); if(($plan['status']??null)==='unavailable'&&(($plan['entry']['reference_price']??null)!==null||($plan['take_profit']['reference_price']??null)!==null||($plan['stop_loss']['reference_price']??null)!==null)) throw new \InvalidArgumentException('unavailable plan numeric must be null'); if(($plan['status']??null)==='materialized'&&(($plan['entry']['reference_price']??0)<=0||($plan['take_profit']['reference_price']??0)<=0||($plan['stop_loss']['reference_price']??0)<=0)) throw new \InvalidArgumentException('materialized plan requires reference prices'); if(count($plan['reason_codes'])!==count(array_unique($plan['reason_codes']))) throw new \InvalidArgumentException('duplicate plan reason'); }
    protected function sourcesOk(?array $p, callable $fn): bool { if(!is_array($p))return false; return $fn($p['take_profit']['source_artifact']??[])&&$fn($p['stop_loss']['source_artifact']??[]); }
    protected function entryFresh(?array $e, ?string $decisionAt): bool { if(!is_array($e)||empty($e['observed_at'])||!$decisionAt)return false; try{$obs=Carbon::parse($e['observed_at']);$dec=Carbon::parse($decisionAt);}catch(\Throwable){return false;} return $obs->lessThanOrEqualTo($dec)&&$obs->greaterThanOrEqualTo($dec->copy()->subMinutes($this->config['entry_reference_freshness_minutes'])); }
    protected function eligibility(?array $c, ?array $p, ?array $r): string { if(!is_array($c))return 'candidate_not_available'; if(($c['status']??null)!=='candidate_ready')return 'candidate_not_ready'; if(!is_array($p))return 'selected_parameters_unavailable'; if(!is_array($r))return 'action_risk_unavailable'; if(($r['status']??null)!=='evaluated')return 'action_risk_not_evaluated'; return 'integrity_blocked'; }
    protected function gate(string $gate,bool $evaluated,?bool $passed,string $severity,string $code,array $details=[]): array { return compact('gate','evaluated','passed','severity','code','details'); }
    protected function add(array &$codes,array &$target,string $code): void { $codes[]=$code;$target[]=$code; }
    protected function sortGates(array $gates): array { $order=array_flip($this->config['materialization_gate_order']); usort($gates,fn($a,$b)=>($order[$a['gate']]??999)<=>($order[$b['gate']]??999)); return $gates; }
    protected function ordered(array $codes): array { $codes=array_values(array_unique($codes)); sort($codes); return $codes; }
}
