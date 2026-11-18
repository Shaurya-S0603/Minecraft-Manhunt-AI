from manhunt_ai.core.action import Action
from manhunt_ai.navigation.astar import AStarPlanner
from manhunt_supervisor.match_state import MatchPhase, MatchState
from manhunt_supervisor.role_selection import assign_roles
from manhunt_seeds.seed_scorer import score_seed


def test_astar_finds_short_path():
    grid = [
        [1, 1, 1],
        [1, 1, 1],
        [1, 1, 1],
    ]
    path = AStarPlanner(grid).find_path((0, 0), (2, 2))
    assert path[0] == (0, 0)
    assert path[-1] == (2, 2)
    assert len(path) <= 5


def test_match_state_transitions():
    state = MatchState()
    state.transition_to(MatchPhase.WORLD_READY)
    state.transition_to(MatchPhase.HEAD_START)
    state.transition_to(MatchPhase.ACTIVE)
    assert state.phase == MatchPhase.ACTIVE


def test_role_selection_rejects_duplicate_roles():
    assignment = assign_roles("runner", "hunter")
    assert assignment.resolved["ai"] == "hunter"
    try:
        assign_roles("runner", "runner")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected duplicate role assignment to be rejected")


def test_seed_scoring_requires_all_dimensions():
    score = score_seed(
        {
            "spawn_safety": 1.0,
            "resource_access": 0.8,
            "terrain_diversity": 0.9,
            "structure_quality": 0.7,
            "navigation": 0.85,
            "objective_access": 0.75,
        }
    )
    assert score.total > 0.8


def test_action_carries_request_id():
    action = Action("move-to", target=(1, 2, 3), duration=2.0)
    assert action.status == "pending"
    assert action.request_id
    assert action.as_dict()["name"] == "move-to"
