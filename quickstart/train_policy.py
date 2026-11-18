"""Offline model-fitting command: python -m quickstart.train_policy

Reads actual Minecraft trial JSONL, not fabricated or copyrighted videos.
No source code or records are uploaded to GitHub or an external service.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from .movement_policy import train_from_log,save_policy
from .movement_training import DATA_ROOT
from .skill_policy import train_skill_policy,save_skill_policy
from .curriculum_v3 import fit_v3,save_v3,read_research_profile
from .curriculum_v4 import fit_v4,save_v4


def main(argv=None):
    parser=argparse.ArgumentParser(description='Train movement policy on logged REAL Minecraft attempts')
    parser.add_argument('--data',type=Path,default=DATA_ROOT/'trials.jsonl')
    parser.add_argument('--output',type=Path,default=DATA_ROOT/'policy.json')
    parser.add_argument('--v4-only',action='store_true',help='Refit only V4; preserve all older checkpoint files')
    args=parser.parse_args(argv)
    research=read_research_profile(args.data.parent.parent/'strategy'/'mine_ai_tools.jsonl')
    v4=fit_v4(args.data.parent/'arena_episodes.jsonl',research_profile=research)
    if v4['current_episodes']:
        save_v4(v4,args.data.parent/'curriculum_policy_v4.json')
        certified=[key for key,g in v4['groups'].items() if g['validated_for_live']]
        print('[MODEL V4] Current-generation episodes:',v4['current_episodes'],
              '; archived comparable:',v4['historical_comparable_episodes'],
              '; held-out certified:',certified)
    else:
        print('[MODEL V4] No V4 sessions yet: history preserved; no new V4 certification.')
    if args.v4_only:
        print('[MODEL V4] Old policies and episode logs were not rewritten.')
        return 0
    v3=fit_v3(args.data.parent/'arena_episodes.jsonl',research_profile=research)
    if v3['episodes']:
        save_v3(v3,args.data.parent/'curriculum_policy_v3.json')
        print('[MODEL V3] Fitted:',v3['episodes'],'real local episodes; research metadata=',research['records'])
        print('[MODEL V3] Selected actions require held-out validation, not research pseudo-rewards.')
    policy=train_from_log(args.data)
    if not policy['records']:
        print('[MODEL] No verified real Minecraft jump trials found. No policy written.')
        print('[MODEL] Run training/launchers/TRAIN_ADAPTIVE_V4.bat to record physical movement first.')
        # Still train swim/climb even with no successful jump attempts.
        extra=train_skill_policy(args.data.parent/'arena_episodes.jsonl')
        if extra['episodes']:
            save_skill_policy(extra,args.output.parent/'skill_policy.json')
            print('[MODEL] Updated swim/climb policy from',extra['episodes'],'observed episodes.')
        return 0
    save_policy(policy,args.output)
    print('[MODEL] Trained contextual bandit on',policy['records'],'observed jump trials.')
    for gap,summary in policy['groups'].items():
        print('[MODEL] Gap',gap,'trials=',summary['trials'],
              'eligible learned threshold=',summary['selected_offset'])
    extra=train_skill_policy(args.data.parent/'arena_episodes.jsonl')
    if extra['episodes']:
        save_skill_policy(extra,args.output.parent/'skill_policy.json')
        print('[MODEL] Saved multi-skill policy from',extra['episodes'],'observed episodes.')
    print('[MODEL] Saved:',args.output)
    print('[MODEL] This checkpoint adjusts timing only; it cannot override proven-gap safety gating.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
