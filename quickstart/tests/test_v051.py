"""v0.5.1 regression tests: passable ground decorations and lowered collision tops."""
import unittest

from quickstart.observations import Position
from quickstart.pathfinding3d import BoundedAStar
from quickstart.safe_spawn import SafeSpawnFinder
from quickstart.terrain import TerrainSensor, TerrainUnavailable, terrain_type
from quickstart.tests.test_navigation import FakeScarpet


class DecorationClassificationTests(unittest.TestCase):
    def test_natural_12111_decorations_can_be_crossed(self):
        for name in (
            'leaf_litter', 'wildflowers', 'pink_petals', 'bush', 'firefly_bush',
            'short_dry_grass', 'tall_dry_grass', 'pale_hanging_moss',
            'moss_carpet', 'pale_moss_carpet', 'white_carpet', 'red_carpet',
            'lilac', 'peony', 'rose_bush', 'sunflower', 'torchflower',
            'pitcher_plant', 'wheat', 'carrots', 'potatoes', 'beetroots',
        ):
            with self.subTest(name=name):
                self.assertEqual(terrain_type(name), 'air')

    def test_scarpet_namespaced_and_blockstate_names(self):
        self.assertEqual(terrain_type('minecraft:leaf_litter[segment_amount=4,facing=north]'), 'air')
        self.assertEqual(terrain_type('minecraft:wildflowers[flower_amount=2]'), 'air')
        self.assertEqual(terrain_type('minecraft:white_carpet'), 'air')

    def test_hazards_and_unknowns_still_rejected(self):
        for name in ('lava', 'magma_block', 'cactus', 'wither_rose',
                     'pointed_dripstone', 'sweet_berry_bush', 'powder_snow'):
            with self.subTest(name=name):
                self.assertEqual(terrain_type(name), 'hazard')
        for name in ('oak_leaves', 'oak_log', 'cobweb', 'oak_fence',
                     'stone', 'unknown_modded_block'):
            with self.subTest(name=name):
                self.assertEqual(terrain_type(name), 'solid')


class DecorationNavigationTests(unittest.TestCase):
    def test_walks_through_leaf_litter_curtain(self):
        world = FakeScarpet()
        # Litter all the way across the local window: the route cannot dodge
        # sideways out of the sample window and must cross it directly.
        for z in range(-6, 7):
            world.set(1, 64, z, 'leaf_litter')
            world.set(2, 64, z, 'short_dry_grass')
            world.set(3, 64, z, 'wildflowers')
        route = BoundedAStar(TerrainSensor(world)).plan(
            Position(.5, 64, .5), Position(5.5, 64, .5))
        self.assertTrue(route.reached_goal)
        self.assertTrue(any(step.destination.x > 3 for step in route.steps))

    def test_unknown_curtain_stays_blocked(self):
        world = FakeScarpet()
        for z in range(-6, 7):
            world.set(1, 64, z, 'unknown_modded_block')
            world.set(1, 65, z, 'unknown_modded_block')
            world.set(1, 66, z, 'unknown_modded_block')
        route = BoundedAStar(TerrainSensor(world)).plan(
            Position(.5, 64, .5), Position(5.5, 64, .5))
        self.assertFalse(route.reached_goal)

    def test_walks_from_and_toward_lowered_ground(self):
        for support, height in (('dirt_path', 63.9375),
                                ('farmland', 63.9375), ('mud', 63.875),
                                ('soul_sand', 63.875)):
            with self.subTest(support=support):
                world = FakeScarpet()
                for x in range(-6, 7):
                    for z in range(-6, 7):
                        world.set(x, 63, z, support)
                route = BoundedAStar(TerrainSensor(world)).plan(
                    Position(.5, height, .5), Position(4.5, height, .5))
                self.assertTrue(route.reached_goal)
                self.assertTrue(route.steps)
                self.assertEqual(route.steps[0].destination.y, 64)

    def test_unsafe_source_inside_solid_wall_is_not_snapped(self):
        world = FakeScarpet()
        for y in (64,65):
            world.set(0, y, 0, 'stone')
        with self.assertRaises(TerrainUnavailable):
            BoundedAStar(TerrainSensor(world)).plan(
                Position(.5, 64.9375, .5), Position(5.5, 65, .5))


class DecoratedSpawnTests(unittest.TestCase):
    def test_leaf_litter_does_not_block_open_spawn(self):
        world = FakeScarpet()
        for x in range(-15, 16):
            for z in range(-15, 16):
                world.set(x, 64, z, 'leaf_litter')
        sensor = TerrainSensor(world)
        spawn = SafeSpawnFinder(sensor).find(Position(.5, 64, .5))
        self.assertTrue(SafeSpawnFinder(sensor).verify(spawn.position))

    def test_spawn_verification_allows_dirt_path_physics_offset(self):
        for support, height in (('dirt_path', 63.9375),
                                ('farmland', 63.9375), ('mud', 63.875),
                                ('soul_sand', 63.875)):
            with self.subTest(support=support):
                world = FakeScarpet()
                world.set(0,63,0,support)
                self.assertTrue(SafeSpawnFinder(TerrainSensor(world)).verify(
                    Position(.5, height, .5)))

    def test_spawn_verification_never_excuses_stone_intersection(self):
        world = FakeScarpet()
        world.set(0, 63, 0, 'stone')
        self.assertFalse(SafeSpawnFinder(TerrainSensor(world)).verify(
            Position(.5, 63.9375, .5)))

    def test_spawn_not_inside_leaves_or_lava(self):
        world = FakeScarpet()
        world.set(0, 64, 0, 'oak_leaves')
        self.assertFalse(SafeSpawnFinder(TerrainSensor(world)).verify(
            Position(.5,64,.5)))
        world.set(0,64,0,'lava')
        self.assertFalse(SafeSpawnFinder(TerrainSensor(world)).verify(
            Position(.5,64,.5)))


if __name__ == '__main__':
    unittest.main()
