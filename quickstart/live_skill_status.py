"""Read-only status of policies eligible for *normal Manhunt* movement."""
from __future__ import annotations
import argparse
from pathlib import Path
from .movement_training import DATA_ROOT
from .skill_policy import load_skill_policy
from .live_skill_policy import LiveSkillPolicy
from .curriculum_v4 import load_v4


def main(argv=None):
    parser=argparse.ArgumentParser(description='Show real training checkpoint and live movement eligibility')
    parser.add_argument('--data',type=Path,default=DATA_ROOT)
    args=parser.parse_args(argv)
    path=args.data/'skill_policy.json'
    policy=load_skill_policy(path)
    live=LiveSkillPolicy(path)
    v4=load_v4(args.data/'curriculum_policy_v4.json')
    print('[LIVE SKILLS] Checkpoint:', path)
    if not policy and v4 is None:
        print('[LIVE SKILLS] No complete policy checkpoint yet. Ordinary controls will be used.')
        return 0
    if policy:
        print('[LIVE SKILLS] Recorded Minecraft episodes (lifetime archive):',policy.get('episodes',0))
    if v4 is not None:
        print('[LIVE SKILLS] V4 current-generation evidence:',v4.get('current_episodes',0),
              '; historical comparable:',v4.get('historical_comparable_episodes',0))
        for name,group in sorted(v4.get('groups',{}).items()):
            print(f'[LIVE SKILLS] V4 {name}: {group.get("status","unknown")}; '
                  f'current training={group.get("current_train_trials",0)}, '
                  f'held-out={group.get("current_validation_trials",0)}')
        print('[LIVE SKILLS] Legacy policies cannot override an uncertified V4 setting.')
    for skill in ('swim','climb'):
        group=(policy or {}).get('groups',{}).get(skill,{})
        choice=group.get('selected_parameter')
        option=(group.get('options') or {}).get(str(choice),{})
        status=('ENABLED' if live.value(skill) is not None else 'STANDARD CONTROLS')
        print(f'[LIVE SKILLS] {skill}: {status}, selected={choice}, '
              f'wins={option.get("wins",0)}, trials={option.get("trials",0)}')
    print('[LIVE SKILLS] Swim transfer: only horizontal travel with healthy air; never emergency ascent.')
    print('[LIVE SKILLS] Climb transfer: ladders only; vines still use standard aiming.')
    print('[LIVE SKILLS] No trained policy is edited by ordinary Manhunt.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
