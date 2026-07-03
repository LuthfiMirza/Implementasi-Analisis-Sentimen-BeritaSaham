<?php
namespace App\Services\Trading;

class PositionManagementActionPolicyService
{
    public function __construct(protected ?array $config = null) { $this->config ??= config('trading_position_management_plan'); }

    public function evaluate(array $ctx): array
    {
        $candidate = $ctx['management_candidate'] ?? null; $risk = $ctx['management_risk'] ?? null; $review = $ctx['review_plan'] ?? null; $policy = $ctx['management_action_policy'] ?? ($ctx['action_policy'] ?? null);
        $codes=[]; $warnings=[]; $blockers=[]; $matched=null; $status='unavailable'; $elig='action_policy_unavailable';
        if (($ctx['decision_scope'] ?? null) !== 'position_management') $this->add($codes,'POSITION_MANAGEMENT_ACTION_POLICY_UNAVAILABLE',$blockers);
        if (!is_array($candidate) || ($candidate['status'] ?? null) !== 'policy_hypothesis') { $this->add($codes,'POSITION_MANAGEMENT_ACTION_PLAN_CANDIDATE_REQUIRED',$blockers); $candidate=null; }
        if (!is_array($risk) || !in_array($risk['status'] ?? null, ['evaluated_reference','condition_risk_observed'], true)) $this->add($codes,'POSITION_MANAGEMENT_ACTION_PLAN_RISK_REQUIRED',$blockers);
        if (!is_array($review) || ($review['status'] ?? null) !== 'review_context_ready') $this->add($codes,'POSITION_MANAGEMENT_ACTION_PLAN_REVIEW_REQUIRED',$blockers);
        if (!is_array($policy)) $this->add($codes,'POSITION_MANAGEMENT_ACTION_POLICY_UNAVAILABLE',$blockers);
        elseif (($policy['schema_version'] ?? null) !== $this->config['action_policy_schema_version']) { $status='invalid'; $elig='action_policy_invalid'; $this->add($codes,'POSITION_MANAGEMENT_ACTION_POLICY_INVALID',$blockers); }
        else {
            $invalid=$this->policyInvalid($policy,$codes,$blockers);
            if ($invalid) { $status='invalid'; $elig='action_policy_invalid'; }
            elseif (!$candidate || ($policy['position_id']??null)!==($candidate['position_id']??null) || ($policy['ticker']??null)!==($candidate['ticker']??null) || ($policy['management_candidate_id']??null)!==($candidate['candidate_id']??null)) { $status='blocked'; $elig='identity_mismatch'; $this->add($codes,'POSITION_MANAGEMENT_ACTION_POLICY_IDENTITY_MISMATCH',$blockers); }
            else {
                $rules=array_values(array_filter($policy['rules']??[], fn($r)=>($r['enabled']??false)===true && ($r['candidate_type']??null)===($candidate['candidate_type']??null)));
                usort($rules, fn($a,$b)=>($b['priority']??0)<=>($a['priority']??0) ?: strcmp($a['rule_id']??'', $b['rule_id']??''));
                if (!$rules) { $status='no_matching_rule'; $elig='no_matching_rule'; $this->add($codes,'POSITION_MANAGEMENT_ACTION_POLICY_NO_MATCHING_RULE',$blockers); }
                elseif (count($rules)>1 && ($rules[0]['priority']??null)===($rules[1]['priority']??null)) { $status='invalid'; $elig='action_policy_invalid'; $this->add($codes,'POSITION_MANAGEMENT_ACTION_POLICY_INVALID',$blockers); }
                else { $matched=$rules[0]; $status='matched_reference_rule'; $elig='eligible_reference_only'; $this->add($codes,'POSITION_MANAGEMENT_ACTION_POLICY_RULE_MATCHED'); $this->add($codes,'POSITION_MANAGEMENT_ACTION_POLICY_REFERENCE_ONLY'); }
            }
        }
        foreach(['POSITION_MANAGEMENT_ACTION_POLICY_SELECTION_NOT_APPROVED','POSITION_MANAGEMENT_ACTION_POLICY_MUTATION_NOT_APPROVED','POSITION_MANAGEMENT_ACTION_POLICY_EXECUTION_NOT_APPROVED'] as $c) $this->add($codes,$c,$blockers);
        $r=['schema_version'=>$this->config['action_policy_evaluation_schema_version'],'status'=>$status,'position_id'=>$candidate['position_id']??($policy['position_id']??null),'management_candidate_id'=>$candidate['candidate_id']??($policy['management_candidate_id']??null),'policy_id'=>$policy['policy_id']??null,'policy_version'=>$policy['policy_version']??null,'matched_rule'=>$matched,'proposed_action'=>$matched['proposed_action']??null,'quantity_mode'=>$matched['quantity_mode']??null,'eligibility'=>$elig,'reason_codes'=>$this->ordered($codes),'warnings'=>$this->ordered($warnings),'blockers'=>$this->ordered($blockers),'metadata'=>['approved_for_selection'=>false,'approved_for_portfolio_mutation'=>false,'approved_for_execution'=>false]];
        $this->validateEvaluation($r); return $r;
    }
    protected function policyInvalid(array $p,array &$codes,array &$blockers): bool { $bad=false; foreach(['policy_id','policy_version','position_id','ticker','management_candidate_id','supported_side','source'] as $k) if(empty($p[$k])) $bad=true; if(($p['status']??null)!=='reference_only') $bad=true; if(($p['approved_for_selection']??false)||($p['approved_for_portfolio_mutation']??false)||($p['approved_for_execution']??false)) $bad=true; $ids=[]; $prio=[]; foreach($p['rules']??[] as $r){$id=$r['rule_id']??''; if(!$id||isset($ids[$id]))$bad=true; $ids[$id]=1; if(($r['enabled']??false)){ $pk=($r['candidate_type']??'').'|'.($r['priority']??''); if(isset($prio[$pk]))$bad=true; $prio[$pk]=1; } if(!in_array($r['proposed_action']??null,$this->config['supported_proposed_action_types'],true)||!in_array($r['quantity_mode']??null,$this->config['supported_quantity_modes'],true))$bad=true; if(($r['proposed_action']??null)==='exit_position'&&($r['quantity_mode']??null)!=='full_position')$bad=true; if(($r['proposed_action']??null)==='reduce_position'&&($r['quantity_mode']??null)==='full_position')$bad=true; if(($r['quantity_mode']??null)==='full_position'&&(($r['explicit_units']??null)!==null||($r['explicit_fraction']??null)!==null))$bad=true; } if($bad)$this->add($codes,'POSITION_MANAGEMENT_ACTION_POLICY_INVALID',$blockers); return $bad; }
    public function validateEvaluation(array $r): void { if(($r['schema_version']??null)!==$this->config['action_policy_evaluation_schema_version']) throw new \InvalidArgumentException('bad action policy eval schema'); if(!in_array($r['status'],['unavailable','no_matching_rule','matched_reference_rule','blocked','invalid'],true)) throw new \InvalidArgumentException('bad action policy eval status'); }
    protected function add(&$c,$code,&$target=null):void{if(!in_array($code,$c,true))$c[]=$code;if(is_array($target)&&!in_array($code,$target,true))$target[]=$code;} protected function ordered($c):array{sort($c);return array_values(array_unique($c));}
}
