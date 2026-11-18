"""Safely extract anonymized, structured tool evidence from Mine AI MCP trace.

Run from the project root:
  python -m quickstart.strategy_import --input transcript.jsonl

Source: https://huggingface.co/datasets/aibengineering/beat-the-game-minecraft
Data licensed CC BY 4.0. The output is *observational research data* and
never loaded as executable code or directly treated as Manhunt success labels.
No external model weight or model training is performed by this conversion.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

PREFIXES=('mcp__minecraft__','minecraft__')
CATEGORIES={
    'navigation': ('navigate','travel','move','path','locate','explore','approach','follow'),
    'world_observation': ('view','inspect','status','observe','scan','nearby','frontier'),
    'combat': ('attack','combat','defend','survival','fight'),
    'resource_planning': ('mine','craft','smelt','gather','barter','trade','inventory','build','place'),
    'memory': ('note','memory','remember'),
}


def classify(name: str) -> str:
    # Accept only the explicitly published Minecraft MCP tool family.
    if not isinstance(name,str) or not name.startswith(PREFIXES) or len(name)>130:
        return ''
    suffix=name.split('__')[-1].lower()
    if not suffix.replace('_','').isalnum():
        return ''
    for cat,terms in CATEGORIES.items():
        if any(term in suffix for term in terms):
            return cat
    return 'other_minecraft_action'


def import_transcript(source: Path, output: Path, max_bytes: int = 32_000_000) -> dict:
    if source.stat().st_size > max_bytes:
        raise ValueError('Transcript too large for bounded importer')
    pending={}
    observed=[]
    counts=Counter()
    with source.open(encoding='utf-8') as handle:
        for index,raw in enumerate(handle):
            if index > 100_000 or len(raw)>500_000:
                raise ValueError('Exceeded bounded source size or row count')
            try:
                entry=json.loads(raw)
            except json.JSONDecodeError:
                counts['invalid_json']+=1
                continue
            if not isinstance(entry,dict):
                continue
            message=entry.get('message')
            if not isinstance(message,dict):
                continue
            blocks=message.get('content')
            if not isinstance(blocks,list):
                continue
            for block in blocks:
                if not isinstance(block,dict):
                    continue
                kind=block.get('type')
                if entry.get('type')=='assistant' and kind=='tool_use':
                    name=block.get('name','')
                    category=classify(name)
                    ident=block.get('id','')
                    if category and isinstance(ident,str) and len(ident)<=128:
                        # No raw arguments, reasoning, prompts, or world coords.
                        pending[ident]=(category, name.split('__')[-1])
                        counts['requests']+=1
                elif entry.get('type')=='user' and kind=='tool_result':
                    ident=block.get('tool_use_id','')
                    if ident not in pending:
                        continue
                    category,action=pending.pop(ident)
                    # An error flag is unambiguous. Other responses have many
                    # formats: do NOT infer success from arbitrary prose.
                    status='error' if block.get('is_error') is True else 'unverified_result'
                    item={'schema':1,'source':'aibengineering/beat-the-game-minecraft',
                          'license':'CC-BY-4.0','category':category,'action':action,
                          'result_status':status,'id_hash':hashlib.sha256(ident.encode()).hexdigest()[:16],
                          'evidence_level':'tool_result_present_not_world_verified'}
                    observed.append(item)
                    counts[status]+=1
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8') as f:
        for record in observed:
            f.write(json.dumps(record,sort_keys=True)+'\n')
    counts['examples']=len(observed)
    counts['unpaired_requests']=len(pending)
    return dict(counts)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Import safe Mine AI MCP tool-use metadata')
    parser.add_argument('--input',required=True,type=Path,help='Downloaded published transcript.jsonl')
    parser.add_argument('--output',type=Path,default=Path('runtime/strategy/mine_ai_tools.jsonl'))
    args=parser.parse_args(argv)
    counts=import_transcript(args.input,args.output)
    print('[RESEARCH] Extracted evidence records:',counts)
    print('[RESEARCH] Saved',args.output)
    print('[RESEARCH] Observational metadata only. No model weights fitted; no code executed.')

if __name__=='__main__':
    main()
