"""Comprehensive, reproducible skill reports from observed Minecraft trials.

Writes Markdown, CSV and JSON under reports/generated. Reports are descriptive:
no fabricated live success, no optimistic model claims, no training-data leakage.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean, median

from .movement_training import DATA_ROOT, MovementTrainer
from .skill_policy import read_episodes, load_skill_policy
from .movement_policy import load_policy
from .jump_training_v2 import load_v2, fit_v2
from .curriculum_v3 import load_v3, read_research_profile
from .curriculum_v4 import current_episode, comparable, load_v4

OUTPUT=Path(__file__).resolve().parents[1]/'reports'/'generated'


def wilson(wins:int, trials:int) -> tuple[float,float]:
    if trials == 0: return 0.,1.
    z=1.96; p=wins/trials
    denom=1+z*z/trials
    center=(p+z*z/(2*trials))/denom
    spread=z*math.sqrt(p*(1-p)/trials+z*z/(4*trials*trials))/denom
    return max(0.,center-spread), min(1.,center+spread)


def _summary(rows:list[dict]) -> dict:
    n=len(rows); wins=sum(r['success'] for r in rows)
    rates=wilson(wins,n)
    elapsed=[float(r['duration_s']) for r in rows]
    return {'attempts':n,'successes':wins,'success_pct':round(100*wins/n,2) if n else None,
            'confidence_95_pct':[round(100*x,2) for x in rates] if n else None,
            'mean_seconds':round(mean(elapsed),3) if elapsed else None,
            'median_seconds':round(median(elapsed),3) if elapsed else None,
            'reasons':dict(Counter(str(r.get('reason','unknown')) for r in rows))}


def _progress(rows:list[dict]) -> dict:
    n=len(rows)
    q=max(1,n//4)
    earlier=_summary(rows[:q]); recent=_summary(rows[-q:])
    delta=round((recent['success_pct'] or 0)-(earlier['success_pct'] or 0),2) if n>=8 else None
    return {'first_quarter':earlier,'last_quarter':recent,'change_percentage_points':delta,
            'sufficient_for_comparison':n>=20}


def _suggest(stage:str,skill:str,summary:dict,progress:dict) -> list[str]:
    n=summary['attempts'];success=summary['success_pct']
    if not n: return ['Run the first authenticated server trials; the model has no real observations yet.']
    r=summary['reasons'];notes=[]
    if n<30:notes.append('Collect at least 30 trials before interpreting progress as meaningful.')
    if r.get('overshoot',0)/n>=.12:
        notes.append('Landing overshoot dominates: compare midair brake_after settings at 0.6 and 1.5 blocks after platform entry.')
    if r.get('undershoot',0)/n>=.12:
        notes.append('Landing undershoot dominates: inspect measured run-up speed, actual launch offset, and takeoff support.')
    if r.get('fell_below_platform',0)/n>=.12:
        notes.append('The bot repeatedly fell below the platform: examine ascent timing, landing clearance and sprint retention.')
    if r.get('unsafe_or_missed_takeoff',0)/n>=.20:
        notes.append('Jump approach fails frequently: verify runway length, speed threshold, and the measured takeoff window.')
    if r.get('jump_timeout',0)/n>=.10 or r.get('missed_or_timed_out',0)/n>=.20:
        notes.append('Improve landing/takeoff timing and check the 50 ms control loop, physics alignment, and platform support.')
    if r.get('left_water',0)/n>=.15:
        notes.append('Swim trials leave water: adjust depth/pitch control and keep water blocks along the entire route.')
    if skill=='climb' and success is not None and success<70:
        notes.append('Check ladder-facing alignment, forward contact, jump hold, and upper exit clearance.')
    if skill=='swim' and success is not None and success<70:
        notes.append('Compare pitch-bias variants and observed depth trajectories; test that air checks are not forcing unnecessary ascent.')
    if progress['sufficient_for_comparison'] and progress['change_percentage_points'] is not None:
        d=progress['change_percentage_points']
        if d < -10:notes.append(f'Recent success is {abs(d):g} percentage points below initial trials: check drift, damage to the arena, or a poor policy preference.')
        elif d > 10:notes.append(f'Recent success improved by {d:g} percentage points; validate on a different seed/course before trusting generalization.')
        else:notes.append('Success is roughly flat; test more distinct control settings rather than adding identical episodes.')
    if n>=50 and (success or 0)<50:
        notes.append('Pause high-volume training and inspect a failed trajectory; repeating one bad route 1000 times is not useful.')
    if not notes:notes.append('Continue controlled tests on held-out courses; current evidence is promising but not proof of transfer.')
    return notes


def build_report(log:Path, jump_policy:Path|None=None, skill_policy:Path|None=None) -> dict:
    all_rows=list(read_episodes(log,include_validation=True))
    rows=[r for r in all_rows if r.get('split','train')=='train']
    heldout=[r for r in all_rows if r.get('split')=='validation' and r.get('scheduler_version')==3]
    groups=defaultdict(list)
    byskill=defaultdict(list)
    for row in rows:
        groups[(row['stage'],row['skill'])].append(row)
        byskill[row['skill']].append(row)
    stages={}
    for (stage,skill),data in sorted(groups.items()):
        stats=_summary(data);trend=_progress(data)
        stages[stage]={'skill':skill,**stats,'progress':trend,
                       'recommendations':_suggest(stage,skill,stats,trend)}
    skills={skill:{**_summary(data),'progress':_progress(data)} for skill,data in sorted(byskill.items())}
    jp=load_policy(jump_policy) if jump_policy else None
    sp=load_skill_policy(skill_policy) if skill_policy else None
    # Different scorer versions are not apples-to-apples. Always report
    # legacy and corrected jump labels separately before trend comparisons.
    jump_legacy=[r for r in rows if r['skill']=='sprint_jump' and r.get('scorer_version')!=2]
    jump_v2=[r for r in rows if r['skill']=='sprint_jump' and r.get('scorer_version')==2]
    v2_file=log.parent/'jump_policy_v2.json'
    v2=load_v2(v2_file)
    if v2 is None and (log.parent/'trials.jsonl').exists():
        v2=fit_v2(log.parent/'trials.jsonl')
    corrected_reasons=dict(Counter(r.get('reason','unknown') for r in jump_v2))
    jump_diagnostics={
        'legacy_episodes':len(jump_legacy),
        'corrected_episodes':len(jump_v2),
        'legacy':_summary(jump_legacy),
        'corrected':_summary(jump_v2),
        'corrected_failure_reasons':corrected_reasons,
        'corrected_progress':_progress(jump_v2) if jump_v2 else None,
        'corrected_policy':{gap:{'trials':grp['trials'],'selected':grp['selected'],
                                  'eligible_candidates':sum(c['eligible'] for c in grp['candidates'])}
                            for gap,grp in v2['groups'].items()} if v2 else None,
        'interpretation':('Legacy point-target results may undercount valid landings. '
            'No valid comparison of success percentage between scorer versions is possible '
            'without replaying the same observed trajectories and block support checks. '
            'Train and certify on new corrected Minecraft trials.')
    }
    v3=load_v3(log.parent/'curriculum_policy_v3.json')
    research=read_research_profile(log.parent.parent/'strategy'/'mine_ai_tools.jsonl')
    validation_groups=defaultdict(list)
    for row in heldout:
        validation_groups[row.get('base_stage',row['stage'])].append(row)
    validation={name:_summary(v) for name,v in sorted(validation_groups.items())}
    # Headline performance must never blend the old point-target jump scorer
    # with the corrected platform scorer. When V4 sessions exist, show their
    # own current figures first; otherwise show version-comparable recent data.
    comparable_by_stage=defaultdict(list)
    new_by_stage=defaultdict(list)
    historical_by_version=Counter()
    new_sessions=[]
    for row in all_rows:
        if current_episode(row):
            if row['session_id'] not in new_sessions:
                new_sessions.append(row['session_id'])
            historical_by_version['generation_4_'+row.get('split','train')]+=1
        elif row['skill']=='sprint_jump' and row.get('scorer_version')!=2:
            historical_by_version['legacy_point_target_jumps']+=1
        else:
            historical_by_version['pre_v4_comparable_'+row.get('split','train')]+=1
        if row.get('split','train')=='train' and comparable(row):
            comparable_by_stage[row.get('base_stage',row['stage'])].append(row)
            if current_episode(row):
                new_by_stage[row.get('base_stage',row['stage'])].append(row)
    latest_session=new_sessions[-1] if new_sessions else None
    session_rows=[r for r in all_rows if latest_session and r.get('session_id')==latest_session and current_episode(r)]
    sessions_stages=defaultdict(list)
    session_validations=defaultdict(list)
    for row in session_rows:
        stage=row.get('base_stage',row['stage'])
        if row.get('split','train')=='validation':
            session_validations[stage].append(row)
        else:
            sessions_stages[stage].append(row)
    # Each stage's headline is exclusively V4 if present, or corrected-scoring
    # compatible history. Historical rows are NEVER silently assigned to a V4 session.
    current_windows={}
    for stage in sorted(set(comparable_by_stage) | {name for name,_skill in groups}):
        history=comparable_by_stage.get(stage,[])
        active=new_by_stage.get(stage) or history
        current_windows[stage]={
            'basis':('v4_generation' if new_by_stage.get(stage) else
                     ('comparable_history_pre_v4' if history else 'no_comparable_trials')),
            'comparable_training_episodes':len(history),
            'v4_training_episodes':len(new_by_stage.get(stage,[])),
            'rolling_100':_summary(active[-100:]),
            'rolling_500':_summary(active[-500:]),
            'latest_session_train':_summary(sessions_stages.get(stage,[])),
            'latest_session_validation':_summary(session_validations.get(stage,[])),
            'top_recent_failure':next(iter(Counter(str(r.get('reason','unknown')) for r in active[-100:] if not r['success']).most_common(1)),None),
        }
    v4=load_v4(log.parent/'curriculum_policy_v4.json')
    return {'schema':1,'generated_utc':datetime.now(timezone.utc).isoformat(),
            'source':'observed_minecraft_trials','total_episodes':len(rows),
            'heldout_episodes':len(heldout),'validation':validation,'v3_policy':v3,'v4_policy':v4,'mine_ai_research':research,
            'current_windows':current_windows,'latest_session_id':latest_session,
            'latest_session_total':len(session_rows),'historical_version_counts':dict(historical_by_version),
            'stages':stages,'skills':skills,
            'jump_diagnostics':jump_diagnostics,
            'jump_policy':{'records':jp['records'],'selected_offsets':{k:v['selected_offset'] for k,v in jp['groups'].items()}} if jp else None,
            'skill_policy':sp,'limitations':["Only completed real Minecraft episodes are counted. Simulation results are excluded.",
               "Early/late split is observational, not a causal experiment; difficult stages may have different conditions.",
               "Legacy point-target and verified platform jump labels must never be combined in current comparisons.",
               "V4 current windows exclude old generations once new stage results exist; historical data is still preserved in lifetime totals.",
               "V4 validation is a different lane/run-up within the same generated arena; an unseen map remains the transfer test.",
               "Legacy scheduler: 1000 physical trials per stage; V3 adaptive scheduler: one total budget shared across stages.",
               "V3 held-out attempts use alternate positions in the same basic arena; only a separate test map establishes true transfer.",
               "Imported Mine AI tool results are unverified metadata; none are counted as Minecraft movement success labels.",
               "Policy-selected horizontal swim and ladder settings can be used during Manhunt only after the real-trial validation threshold; standard controls remain the fallback and transfer still needs held-out verification."]}


def export_report(data:dict, output:Path):
    output.mkdir(parents=True,exist_ok=True)
    (output/'training_report.json').write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    with (output/'training_summary.csv').open('w',encoding='utf-8',newline='') as fp:
        writer=csv.writer(fp)
        writer.writerow(['stage','skill','attempts','successes','success_pct','early_pct','recent_pct','change_pp','mean_seconds','top_failure','undershoot','overshoot','fell_below_platform','unsafe_takeoff'])
        for stage,s in data['stages'].items():
            r=s['reasons'];failure=max(((v,k) for k,v in r.items() if k not in ('landed','arrived_underwater','climbed_to_height')),default=(0,''))[1]
            p=s['progress']
            writer.writerow([stage,s['skill'],s['attempts'],s['successes'],s['success_pct'],
                             p['first_quarter']['success_pct'],p['last_quarter']['success_pct'],
                             p['change_percentage_points'],s['mean_seconds'],failure,
                             r.get('undershoot',0),r.get('overshoot',0),r.get('fell_below_platform',0),
                             r.get('unsafe_or_missed_takeoff',0)])
    # New compact CSV: stage-specific recent comparable metrics. Old summary
    # CSV is kept for backward compatibility and explicitly labeled lifetime.
    with (output/'training_current_summary.csv').open('w',encoding='utf-8',newline='') as fp:
        writer=csv.writer(fp)
        writer.writerow(['stage','basis','comparable_history_train','v4_training','last_100_attempts',
                         'last_100_success_pct','last_500_attempts','last_500_success_pct',
                         'latest_session_train','latest_session_train_pct',
                         'latest_session_validation','latest_session_validation_pct',
                         'top_recent_failure'])
        for stage,w in data['current_windows'].items():
            writer.writerow([stage,w['basis'],w['comparable_training_episodes'],w['v4_training_episodes'],
                             w['rolling_100']['attempts'],w['rolling_100']['success_pct'],
                             w['rolling_500']['attempts'],w['rolling_500']['success_pct'],
                             w['latest_session_train']['attempts'],w['latest_session_train']['success_pct'],
                             w['latest_session_validation']['attempts'],w['latest_session_validation']['success_pct'],
                             w['top_recent_failure'][0] if w['top_recent_failure'] else ''])
    lines=['# Autonomous Minecraft Movement Training Report','',
           f'Generated UTC: {data["generated_utc"]}',
           f'Cumulative training-split episodes (historical archive): **{data["total_episodes"]}**','',
           '## Current comparable performance (priority)','',
           f'Latest V4 session: **{data["latest_session_id"] or "none yet"}**; '
           f'its recorded train + validation attempts: **{data["latest_session_total"]}**.','',
           'The rolling windows use **only platform-scored jumps**; when a stage has V4 data, '
           'its headline uses **V4 data only**. The full historical archive remains unchanged.','',
           '| Stage | Data basis | Last 100 | Last 500 | Latest session train | Latest session held-out |',
           '|---|---|---:|---:|---:|---:|']
    for stage,w in data['current_windows'].items():
        def fmt(v):
            return f'{v["success_pct"]}% ({v["attempts"]})' if v['attempts'] else 'no trials'
        lines.append(f'| {stage} | {w["basis"]} | {fmt(w["rolling_100"])} | '
                     f'{fmt(w["rolling_500"])} | {fmt(w["latest_session_train"])} | '
                     f'{fmt(w["latest_session_validation"])} |')
    lines+=['','Versioned history (retained, not treated as equally relevant): '
            +str(data['historical_version_counts']),'',
            '## Lifetime performance (historical archive, mixed jump scoring)','',
           '## Per-skill performance','',
           '| Skill | Attempts | Success | 95% interval | Early → recent | Change (pp) |',
           '|---|---:|---:|---|---|---:|']
    for skill,s in data['skills'].items():
        pr=s['progress']; ci=s['confidence_95_pct']
        lines.append(f'| {skill} | {s["attempts"]} | {s["success_pct"]}% | {ci[0]}–{ci[1]}% | '
                     f'{pr["first_quarter"]["success_pct"]}% → {pr["last_quarter"]["success_pct"]}% | '
                     f'{pr["change_percentage_points"] if pr["sufficient_for_comparison"] else "Insufficient data"} |')
    lines+=['','## Stage-level diagnostics','']
    for stage,s in data['stages'].items():
        lines += [f'### {stage} ({s["skill"]})','',
                  f'- Success: **{s["successes"]}/{s["attempts"]} ({s["success_pct"]}%)**; mean {s["mean_seconds"]} seconds.',
                  f'- Early vs recent: {s["progress"]["first_quarter"]["success_pct"]}% → {s["progress"]["last_quarter"]["success_pct"]}%'+
                  (f' (Δ {s["progress"]["change_percentage_points"]:+g} pp)' if s['progress']['sufficient_for_comparison'] else ' (not yet enough data)'),
                  '- Outcomes: '+', '.join(f'{k}: {v}' for k,v in sorted(s['reasons'].items(),key=lambda item:-item[1])),
                  '- Suggested next changes:']
        lines += [f'  - {note}' for note in s['recommendations']]
        lines.append('')
    diagnostics=data['jump_diagnostics']
    lines+=['## Jump scoring audit: legacy versus verified platform scoring','',
            f'- Legacy point-target records: **{diagnostics["legacy_episodes"]}**; labels may be biased.',
            f'- Corrected v2 platform records: **{diagnostics["corrected_episodes"]}**.',
            '- Legacy and corrected success percentages are not directly comparable.',
            '- Corrected jump failures: '+str(diagnostics['corrected_failure_reasons']),
            '- Interpretation: '+diagnostics['interpretation'],'']
    if diagnostics['corrected_policy']:
        for gap,group in diagnostics['corrected_policy'].items():
            lines.append(f'- Gap {gap}: {group["trials"]} corrected attempts, '
                         f'selected={group["selected"]}, '
                         f'{group["eligible_candidates"]} eligible timing/braking candidates.')
    lines+=['','## Learned policy status','']
    jp=data['jump_policy'];sp=data['skill_policy']
    lines.append('- Jump timing: '+(f'{jp["records"]} verified jump attempts; selected timing offsets {jp["selected_offsets"]}.' if jp else 'No real-trial jump checkpoint yet.'))
    if sp:
        lines.append(f'- Swimming/climbing bandit: {sp["episodes"]} total observed episodes.')
        for skill,group in sp['groups'].items():
            lines.append(f'  - {skill}: selected={group["selected_parameter"]}, live-validated={group["validated_for_live"]}, option details={group["options"]}')
    else:lines.append('- Swimming/climbing: no observed-trial policy checkpoint yet.')
    lines+=['','## Adaptive curriculum V3 validation','',
            f'- Training-split episodes: {data["total_episodes"]}; independent held-out split: {data.get("heldout_episodes",0)}.',
            '- Held-out attempts use alternate run-ups/lanes in the same generated arena; they are not Parkour School transfer scores.']
    for stage,stat in data.get('validation',{}).items():
        lines.append(f'- {stage}: {stat["successes"]}/{stat["attempts"]} held-out successes ({stat["success_pct"]}%).')
    v3=data.get('v3_policy')
    if v3:
        lines.append('')
        lines.append('### V3 learned control weights')
        lines.append('')
        for name,group in v3['groups'].items():
            option=group.get('selected')
            top=max(group['candidates'],key=lambda c:(c['score'],c['train_trials']))
            status=('validated for live control' if option else 'not certified; safety fallback')
            lines.append(f'- {name}: {status}. Top training candidate={top["offset_or_parameter"]}, '
                         f'brake={top["brake_after"]}, empirical train {top["train_wins"]}/{top["train_trials"]}, '
                         f'held-out {top["validation_wins"]}/{top["validation_trials"]}.')
    v4=data.get('v4_policy')
    lines+=['','## V4: candidate-specific recent validation gates','']
    if v4:
        lines.append(f'- V4 current episodes: {v4["current_episodes"]}; '
                     f'historical comparable observations: {v4["historical_comparable_episodes"]}; '
                     f'sessions: {v4["sessions"]}.')
        for name,group in v4['groups'].items():
            chosen=group.get('training_candidate')
            status=group['status']
            if chosen is None:
                lines.append(f'- {name}: **{status}**; no training candidate has enough current evidence.')
                continue
            candidate=next((c for c in group['candidates'] if
                            c['offset_or_parameter']==chosen['offset_or_parameter'] and
                            c['brake_after']==chosen['brake_after']),None)
            if candidate:
                lines.append(f'- {name}: **{status}**; best TRAIN-only candidate {chosen}; '
                             f'current train {candidate["current_train_wins"]}/{candidate["current_train_trials"]}; '
                             f'current held-out {candidate["current_validation_wins"]}/{candidate["current_validation_trials"]}.')
    else:
        lines.append('- No V4 model checkpoint yet. Old data is archived; new V4 trials are required to certify any skill.')
    lines+=['','## Mine AI MCP research evidence','']
    research=data.get('mine_ai_research',{})
    lines.append(f'- Imported observations: {research.get("records",0)}; tool-result errors: {research.get("errors",0)}.')
    lines.append('- Categories: '+str(research.get('categories',{})))
    lines.append('- Explicit tool errors by category: '+str(research.get('category_errors',{})))
    lines.append('- Frequent tools: '+str(research.get('top_tools',{})))
    lines.append('- Use: bounded curriculum-priority hints only; no external trace is a movement reward or certified model weight.')
    lines+=['','## Interpretation and limits','']+[f'- {s}' for s in data['limitations']]
    (output/'training_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return [output/f for f in ('training_report.md','training_report.json','training_summary.csv','training_current_summary.csv')]


def main(argv=None):
    parser=argparse.ArgumentParser(description='Create markdown, CSV and JSON diagnostics from real Minecraft training')
    parser.add_argument('--data',type=Path,default=DATA_ROOT)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args(argv)
    data=build_report(args.data/'arena_episodes.jsonl',args.data/'policy.json',args.data/'skill_policy.json')
    generated=export_report(data,args.output)
    trainer=MovementTrainer(args.data)
    print('[REPORT] Training-split Minecraft episodes (lifetime archive):',data['total_episodes'])
    print('[REPORT] Latest V4 session:',data['latest_session_id'] or 'none')
    for name,w in data['current_windows'].items():
        print(f'  [CURRENT] {name}: rolling100={w["rolling_100"]["success_pct"]}% '
              f'({w["rolling_100"]["attempts"]} comparable trials); '
              f'V4={w["v4_training_episodes"]} training episodes; source={w["basis"]}')
    print('[REPORT] Held-out Minecraft episodes:',data.get('heldout_episodes',0))
    print('[REPORT] Mine AI tool observations:',data.get('mine_ai_research',{}).get('records',0))
    print('[REPORT] Certified ordinary-match gap:',trainer.max_trained_gap)
    print('[REPORT] Jump label audit: legacy=',data['jump_diagnostics']['legacy_episodes'],
          'platform-v2=',data['jump_diagnostics']['corrected_episodes'])
    for stage,s in data['stages'].items():
        print(f'  {stage}: {s["successes"]}/{s["attempts"]} ({s["success_pct"]}%), trend={s["progress"]["change_percentage_points"]} pp')
        print('    Next:',s['recommendations'][0])
    for file in generated:print('[REPORT] Saved:',file)
    return 0

if __name__=='__main__':raise SystemExit(main())
