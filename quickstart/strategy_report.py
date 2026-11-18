"""Inspect local online tactics (not a pretrained completion model)."""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import json
from .strategy import StrategyAdvisor


def report(root: Path):
    print('=== Manhunt Tactical Strategy ===')
    for role in ('hunter','runner'):
        advisor=StrategyAdvisor(role,root)
        data=advisor.status()
        if advisor.legacy_path.is_file():
            print('  Legacy v1 policy preserved on disk but ignored: no bot-movement verification.')
        print(f'{role.upper()}: {data["trials"]} observed tactical windows')
        for name,scores in data['actions'].items():
            count=scores['success']+scores['failure']-2  # beta prior, not real trials
            if count:
                estimate=(scores['success']-1)/count
                print(f'  {name}: {estimate:.1%} improving-separation windows ({count} observations)')
            else:
                print(f'  {name}: no live feedback; beta prior only')
    records=root/'mine_ai_tools.jsonl'
    if not records.is_file():
        print('Mine AI MCP trace: not imported (optional research reference).')
    else:
        counts=Counter()
        with records.open(encoding='utf-8') as handle:
            for line in handle:
                try:
                    item=json.loads(line)
                    if item.get('schema')==1 and item.get('source')=='aibengineering/beat-the-game-minecraft':
                        counts[item.get('category','other')]+=1
                except (ValueError,TypeError,AttributeError):
                    continue
        print('Mine AI MCP tool-use records (NOT Manhunt training):',sum(counts.values()))
        for key,value in counts.most_common():
            print(f'  {key}: {value}')
    print('Important: tactical success here means separation improved, not proven win rate.')
    print('Gemini Argon provided published planning principles, not downloadable training weights.')


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path('runtime/strategy'))
    args=parser.parse_args(argv)
    report(args.root)

if __name__=='__main__':main()
