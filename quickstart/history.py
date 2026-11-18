"""Minimal local match journal; does not persist player/account names."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .results import RoundResult


class MatchHistory:
    def __init__(self, logfile: Path):
        self.logfile = Path(logfile)
        self.total = 0
        self.human_wins = 0
        self.ai_wins = 0

    def record(self, result: RoundResult):
        self.total += 1
        if result.is_victory:
            self.human_wins += 1
        else:
            self.ai_wins += 1
        self.logfile.parent.mkdir(parents=True,exist_ok=True)
        data={
            'timestamp_utc':datetime.now(timezone.utc).isoformat(),
            'human_role':result.human_role,
            'winner_role':result.winner,
            'victory':result.is_victory,
            'reason':result.reason,
            'elapsed_seconds':round(result.elapsed_seconds,1),
        }
        with self.logfile.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(data,separators=(',',':'))+'\n')

    def summary(self):
        return f'You {self.human_wins} | AI {self.ai_wins} | Rounds {self.total}'
