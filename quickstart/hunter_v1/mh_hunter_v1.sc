// Private, operator-only app. The Python controller supplies allowlisted recipes.
__config() -> {'scope' -> 'global'};

mh_api() -> 1;

mh_state(name) -> (
    p = player(name);
    if(p == null, return('missing'));
    join('|', [p~'dimension', p~'gamemode', p~'hunger', p~'health', p~'on_ground', str(p~'pos')])
);

_mh_record(e) -> (
    item = e~'item';
    (e~'type') + '|' + if(item != null, item:0, '') + '|' + str(e~'pos')
);

mh_entities() -> (
    drops = entity_selector('@e[type=minecraft:item,distance=..7,sort=nearest,limit=8]');
    animals = filter(entity_selector('@e[type=!minecraft:player,distance=..7,sort=nearest,limit=30]'),
        (_~'type') == 'cow' || (_~'type') == 'pig' || (_~'type') == 'chicken' || (_~'type') == 'sheep');
    join(';', map(drops, _mh_record(_))) + ';' + join(';', map(animals, _mh_record(_)))
);

mh_swap(name, from_slot, to_slot, expected) -> (
    p = player(name);
    if(p == null || from_slot < 9 || from_slot >= 36 || to_slot < 0 || to_slot > 8,
        return('blocked'));
    a = inventory_get(p, from_slot);
    b = inventory_get(p, to_slot);
    if(a == null || a:0 != expected, return('blocked'));
    inventory_set(p, to_slot, a:1, a:0, a:2);
    if(b == null, inventory_set(p, from_slot, 0),
        inventory_set(p, from_slot, b:1, b:0, b:2));
    'ok'
);

_mh_input_ok(p, row) -> (
    slot = row:0;
    stack = inventory_get(p, slot);
    slot >= 0 && slot < 36 && stack != null && stack:0 == row:1 && stack:1 >= row:2 && row:2 > 0
);

_mh_far(pos, station) -> (
    dx = pos:0 - station:0 - 0.5;
    dy = pos:1 - station:1 - 0.5;
    dz = pos:2 - station:2 - 0.5;
    dx*dx + dy*dy + dz*dz > 12.25
);

mh_craft(name, inputs, dst, output, count, station) -> (
    p = player(name);
    if(p == null || dst < 0 || dst >= 36 || count <= 0 || count > 4 ||
        inventory_get(p, dst) != null, return('blocked'));
    if(station != null && (str(block(station)) != 'crafting_table' ||
        _mh_far(p~'pos', station)), return('blocked'));
    if(length(filter(inputs, _mh_input_ok(p, _))) != length(inputs) ||
        length(filter(inputs, _:0 == dst)) != 0, return('blocked'));
    for(inputs, (
        slot = _:0;
        old = inventory_get(p, slot);
        inventory_set(p, slot, old:1 - _:2)
    ));
    inventory_set(p, dst, count, output);
    'ok'
);

global_pickups = {};
__on_player_picks_up_item(p, item) -> (
    if((p~'name') == 'ManhuntBot',
        name = item:0;
        put(global_pickups, name, if(has(global_pickups, name), global_pickups:name, 0) + item:1)
    )
);
mh_pickups() -> join('|', map(keys(global_pickups), _ + '=' + global_pickups:_));
mh_armor() -> (
    p = player('ManhuntBot');
    join('|', map(range(36,40), stack = inventory_get(p,_); if(stack == null,'-',stack:0)))
);

global_deaths = {};
__on_player_dies(p) -> (
    name = p~'name';
    put(global_deaths, name, if(has(global_deaths, name), global_deaths:name, 0) + 1)
);
mh_deaths(name) -> if(has(global_deaths, name), global_deaths:name, 0);

// Quantity changes are owned by Minecraft. Drop callbacks record requests,
// which can fire even if there is no item to drop.
global_drop_requests = 0;
global_stack_drop_requests = 0;
global_transfer_count = 0;
global_verified_drops = 0;
__on_player_drops_item(p) -> (
    if((p~'name') == 'ManhuntBot', global_drop_requests += 1)
);
__on_player_drops_stack(p) -> (
    if((p~'name') == 'ManhuntBot', global_stack_drop_requests += 1)
);
mh_inventory_events() -> join('|', [global_drop_requests, global_stack_drop_requests, global_transfer_count, global_verified_drops]);

_mh_audit_slot(p, i) -> (
    item = inventory_get(p, i);
    if(item == null, '', join('|', [i, item:0, item:1, stack_limit(item:0)]))
);

mh_inventory(name, start, end) -> (
    p = player(name);
    if(p == null, return('missing'));
    join(';', map(range(start, end), _mh_audit_slot(p, _)))
);

// A separate operator action, never called by the pursuit policy.
// Verify the receiver and capacity before moving any item; only empty slots
// are supported so there is no component-merging ambiguity.
mh_transfer(sender, recipient, src, dst, count) -> (
    a = player(sender);
    b = player(recipient);
    if(a == null || b == null || a == b || (a~'dimension') != (b~'dimension') ||
        src < 0 || src >= 36 || dst < 0 || dst >= 36 || count < 1 || count > 64 ||
        inventory_get(b, dst) != null, return('blocked'));
    p = a~'pos';
    q = b~'pos';
    dx = p:0 - q:0; dy = p:1 - q:1; dz = p:2 - q:2;
    if(dx*dx + dy*dy + dz*dz > 9, return('blocked'));
    old = inventory_get(a, src);
    if(old == null || count > old:1, return('blocked'));
    inventory_set(b, dst, count, old:0, old:2);
    received = inventory_get(b, dst);
    if(received == null || received:0 != old:0 || received:1 != count,
        inventory_set(b, dst, 0); return('blocked'));
    inventory_set(a, src, old:1 - count);
    remainder = inventory_get(a, src);
    if((count == old:1 && remainder != null) ||
        (count < old:1 && (remainder == null || remainder:0 != old:0 || remainder:1 != old:1 - count)),
        inventory_set(a, src, old:1, old:0, old:2);
        inventory_set(b, dst, 0); return('blocked'));
    if(sender == 'ManhuntBot' || recipient == 'ManhuntBot', global_transfer_count += count);
    old:0 + '|' + str(count)
);

// Use the native item toss, and keep its confirmed quantity separate from input requests.
mh_drop(name, slot, count) -> (
    p = player(name);
    if(p == null || name != 'ManhuntBot' || slot < 0 || slot >= 36 || count < 1 || count > 64,
        return('blocked'));
    stack = inventory_get(p, slot);
    if(stack == null || count > stack:1, return('blocked'));
    dropped = drop_item(p, slot, count);
    if(dropped != count, return('blocked'));
    global_verified_drops += dropped;
    stack:0 + '|' + str(dropped)
);
