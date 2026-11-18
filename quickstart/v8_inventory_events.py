"""Optional Scarpet event counters. Inventory NBT remains the source of item counts."""
from __future__ import annotations
from pathlib import Path
from .observations import validate_name

OBJECTIVES = ('mh_v8_pick', 'mh_v8_drop', 'mh_v8_stack')
SCRIPT = 'mh_v8_inv'


class InventoryEventBridge:
    """Install one global Scarpet listener for the current fake player.

    Events give precise pickup and drop *triggers*. A requested drop is not
    proof that another player received the item, so transfers still require
    inventory delta verification. Failure to install this optional listener
    never grants items or stops the match.
    """
    def __init__(self, rcon, world_dir: Path, bot: str):
        self.rcon, self.world_dir = rcon, Path(world_dir)
        self.bot = validate_name(bot)
        self.ready = False

    def script(self) -> str:
        return f'''// Manhunter v8 inventory event counters. No items granted or rewritten.
__config() -> {{'scope' -> 'global'}};
__on_player_picks_up_item(player, item) -> (
    if (player~'name' == '{self.bot}',
        scoreboard('mh_v8_pick', '#BOT', scoreboard('mh_v8_pick', '#BOT') + 1)
    )
);
__on_player_drops_item(player) -> (
    if (player~'name' == '{self.bot}',
        scoreboard('mh_v8_drop', '#BOT', scoreboard('mh_v8_drop', '#BOT') + 1)
    )
);
__on_player_drops_stack(player) -> (
    if (player~'name' == '{self.bot}',
        scoreboard('mh_v8_stack', '#BOT', scoreboard('mh_v8_stack', '#BOT') + 1)
    )
);
'''

    def setup(self) -> bool:
        script_dir = self.world_dir / 'scripts'
        if self.world_dir.is_symlink() or script_dir.is_symlink():
            raise ValueError('Refusing symlinked Scarpet directory')
        script_dir.mkdir(parents=True, exist_ok=True)
        script_file = script_dir / f'{SCRIPT}.sc'
        if script_file.is_symlink():
            raise ValueError('Refusing symlinked Scarpet app')
        script_file.write_text(self.script(), encoding='utf-8')
        for name in OBJECTIVES:
            r = self.rcon.command(f'scoreboard objectives add {name} dummy')
            if 'unknown command' in str(r).lower():
                return False
            self.rcon.command(f'scoreboard players set #BOT {name} 0')
        response = self.rcon.command(f'script load {SCRIPT}')
        if any(x in str(response).lower() for x in ('error', 'exception', 'unknown', 'failed', 'could not')):
            print('[INVENTORY] Scarpet event listener unavailable; using inventory diffs only.')
            return False
        self.ready = True
        return True
