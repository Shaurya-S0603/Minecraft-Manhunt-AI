"""Toy, *non-Minecraft* rollout generator for exercising RL policy fitting.

Inspired by parkour-specific episodic training in Minecraft-RL-env. Uses a
transparent ballistic approximation and synthetic randomized conditions.
Checkpoints from here are NEVER trusted by the live Carpet movement policy.
"""
from __future__ import annotations
import json
import math
import random
from pathlib import Path
from .movement_policy import OFFSETS


def toy_episode(gap: int, speed: float, takeoff_offset: float,
                rng: random.Random) -> bool:
    """Approximate jump in 20 TPS; NOT calibrated Minecraft physics.

    Vertical velocity/gravity and drift are toy approximations for testing
    the optimizer's learning loop, not evidence of an executable jump.
    """
    if gap not in (1,2,3): raise ValueError('Unsupported toy obstacle')
    x=.5 + takeoff_offset
    y=0.
    vy=.42
    vx=speed/20.0 * rng.uniform(.94,1.04)
    for tick in range(22):
        vx*=.992
        x+=vx
        y+=vy
        vy=(vy-.08)*.98
        if y<=0 and tick>2:
            # Landing must be on the platform beyond all missing cells.
            return (gap+1 <= x <= gap+2 and tick<21)
    return False


def train_toy_policy(episodes: int=12000,seed: int=7404) -> dict:
    """Tabular epsilon-greedy contextual bandit fitted to synthetic rollouts."""
    if episodes<100: raise ValueError('Not enough training episodes')
    rng=random.Random(seed)
    state_actions={(gap,cls): {o:[0.,0] for o in OFFSETS}
                   for gap in (1,2,3) for cls in ('slow','fast')}
    for i in range(episodes):
        gap=rng.choice((1,2,3))
        cls=rng.choice(('slow','fast'))
        speed=(rng.uniform(3.3,4.3) if cls=='slow' else rng.uniform(4.8,6.0))
        state=state_actions[(gap,cls)]
        epsilon=.35*(1-i/episodes)+.07
        if rng.random()<epsilon:
            offset=rng.choice(OFFSETS)
        else:
            offset=max(OFFSETS,key=lambda o:(state[o][0],-o))
        reward=1. if toy_episode(gap,speed,offset,rng) else -1.
        q,n=state[offset]
        # Sample average incremental return, stable and deterministic by seed.
        state[offset]=[q+(reward-q)/(n+1),n+1]
    learned={f'{gap}:{cls}':max(OFFSETS,key=lambda o:state_actions[(gap,cls)][o][0])
             for gap in (1,2,3) for cls in ('slow','fast')}
    def evaluate(policy, eval_seed):
        test_rng=random.Random(eval_seed)
        total=0;won=0
        by_gap={g:[0,0] for g in (1,2,3)}
        for i in range(3000):
            gap=(i%3)+1
            cls='slow' if i%2 else 'fast'
            speed=test_rng.uniform(3.3,4.3) if cls=='slow' else test_rng.uniform(4.8,6.0)
            offset=policy(gap,cls,test_rng)
            result=toy_episode(gap,speed,offset,test_rng)
            won+=int(result);total+=1
            by_gap[gap][0]+=int(result);by_gap[gap][1]+=1
        return {'successes':won,'episodes':total,'success_rate':round(won/total,4),
                'by_gap':{str(g):round(w/n,4) for g,(w,n) in by_gap.items()}}
    learned_eval=evaluate(lambda g,c,r:learned[f'{g}:{c}'],seed+1)
    # Baseline runs are independent test samples, not paired comparisons.
    baseline_eval=evaluate(lambda g,c,r:.12,seed+2)
    return {'schema':1,'source':'toy_simulation_ONLY_NOT_LIVE',
            'algorithm':'tabular_epsilon_greedy_bandit',
            'train_episodes':episodes,'seed':seed,
            'action_offsets':list(OFFSETS),'policy':learned,
            'evaluation':learned_eval,'constant_offset_baseline':baseline_eval,
            'disclaimer':'No real Minecraft physics, checkpoints, or recorded attempts were used. Do NOT deploy as real movement evidence.'}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--episodes',type=int,default=12000)
    parser.add_argument('--seed',type=int,default=7404)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'runtime'/'toy_experiments'/'toy_simulated_policy.json')
    args=parser.parse_args(argv)
    result=train_toy_policy(args.episodes,args.seed)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print('[TOY RL] Episodes:',result['train_episodes'])
    print('[TOY RL] Held-out simulation accuracy:',result['evaluation']['success_rate'])
    print('[TOY RL] Constant offset simulation baseline:',result['constant_offset_baseline']['success_rate'])
    print('[TOY RL] Saved NON-DEPLOYABLE checkpoint:',args.output)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
