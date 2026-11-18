"""Read-only, fail-closed bridge from arena-learned parameters to live Manhunt.

The trainer owns skill_policy.json. A Manhunt process reads a snapshot at
match startup, never changes it, and uses built-in controls when no option has
sufficient real-game evidence. An option can be disabled for the current round
if the bot stalls. Swimming is applied only to horizontal travel; climb settings
are applied only to the ladder type used in the basic arena.
"""
from __future__ import annotations
from pathlib import Path
import os
from .skill_policy import OPTIONS, load_skill_policy
from .curriculum_v3 import load_v3
from .curriculum_v4 import load_v4, validated_candidate

class LiveSkillPolicy:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.selected: dict[str, float] = {}
        self.disabled: set[str] = set()
        self.reload()

    def reload(self):
        """Snapshot the latest COMPLETED checkpoint; do not touch trainer logs."""
        self.selected.clear()
        self.disabled.clear()
        # Manual emergency fallback: set MANHUNT_LIVE_SKILLS=0 before launch.
        if os.environ.get('MANHUNT_LIVE_SKILLS', '1') == '0':
            return
        data=load_skill_policy(self.path)
        groups=(data.get('groups',{}) if isinstance(data,dict) and
                data.get('model')=='per_skill_beta_smoothed_bandit' else {})
        if not isinstance(groups,dict):groups={}
        for skill, opts in OPTIONS.items():
            group=groups.get(skill)
            if not isinstance(group,dict) or group.get('validated_for_live') is not True:
                continue
            param=group.get('selected_parameter')
            if type(param) not in (int,float) or float(param) not in opts:
                continue
            arms=group.get('options')
            if not isinstance(arms,dict):
                continue
            counts=arms.get(str(float(param)))
            if not isinstance(counts,dict):
                continue
            wins,trials=counts.get('wins'),counts.get('trials')
            if not (type(wins) is int and type(trials) is int and
                    8<=trials<=10_000_000 and 6<=wins<=trials and wins/trials>=0.75):
                continue
            self.selected[skill]=float(param)
        # Once V4 exists, historical policies must NOT bypass its independent
        # recent held-out gates. No valid V4 checkpoint -> use safe defaults.
        v4=load_v4(self.path.parent/'curriculum_policy_v4.json')
        if v4 is not None:
            self.selected.clear()
            for skill, opts in OPTIONS.items():
                group=v4.get('groups',{}).get(f'{skill}:0',{})
                chosen=group.get('selected')
                if group.get('validated_for_live') is not True or not isinstance(chosen,dict):
                    continue
                value=chosen.get('offset_or_parameter')
                if type(value) not in (int,float) or float(value) not in opts:
                    continue
                candidate=next((c for c in group.get('candidates',[]) if
                                c.get('offset_or_parameter')==value and
                                c.get('brake_after') is None),None)
                if validated_candidate(candidate):
                    self.selected[skill]=float(value)
            return
        # A V3 policy can override the older training-only bandit after
        # genuine separate-variant validation. A missing or unproven V3 policy
        # leaves the prior live behavior intact.
        v3=load_v3(self.path.parent/'curriculum_policy_v3.json')
        if v3:
            for skill,opts in OPTIONS.items():
                group=v3.get('groups',{}).get(f'{skill}:0',{})
                selected=group.get('selected')
                if group.get('validated_for_live') is not True or not isinstance(selected,dict):
                    continue
                param=selected.get('offset_or_parameter')
                if type(param) not in (int,float) or float(param) not in opts:continue
                candidate=next((c for c in group.get('candidates',[]) if
                                c.get('offset_or_parameter')==param and c.get('brake_after') is None),None)
                if not isinstance(candidate,dict):continue
                # Re-evaluate from raw counts on reading; do not trust a
                # forged "validated" string in a copied policy JSON.
                n,w=candidate.get('train_trials'),candidate.get('train_wins')
                vn,vw=candidate.get('validation_trials'),candidate.get('validation_wins')
                if all(type(x) is int for x in (n,w,vn,vw)) and n>=16 and w>=12 and 0<=w<=n and \
                   vn>=12 and 0<=vw<=vn and vw/vn>=.75 and candidate.get('train_lower_95',0)>=.62:
                    self.selected[skill]=float(param)

    def value(self,skill:str) -> float|None:
        return self.selected.get(skill) if skill not in self.disabled else None

    def disable(self,skill:str,reason:str) -> bool:
        if self.value(skill) is None:
            return False
        self.disabled.add(skill)
        print(f'[SKILL WARNING] Learned {skill} parameter disabled for this round: {reason}. '
              'Using standard controls.')
        return True

    def status(self) -> str:
        enabled=', '.join(f'{k}={v:+.2f}' for k,v in sorted(self.selected.items()))
        return enabled or 'No validated swim/climb checkpoint yet; standard controls active'
