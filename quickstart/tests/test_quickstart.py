import json
import socket
import struct
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock

from quickstart.rcon import RconClient, RconError
from quickstart.observations import Position, Observer, parse_player_list, parse_position, validate_name
from quickstart.match import ManhuntMatch
from quickstart import install


class RconFixture:
    """Tiny mock RCON server tests packet framing and real local socket I/O."""
    def __init__(self, password='local-test'):
        self.password = password
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1',0))
        self.sock.listen(1)
        self.port=self.sock.getsockname()[1]
        self.commands=[]
        self.worker=threading.Thread(target=self.serve,daemon=True)
        self.worker.start()

    def serve(self):
        conn,_=self.sock.accept()
        with conn:
            while True:
                header=self.read(conn,4)
                if not header:return
                (length,)=struct.unpack('<i',header)
                data=self.read(conn,length)
                if not data:return
                req,kind=struct.unpack('<ii',data[:8])
                value=data[8:-2].decode()
                if kind==3:
                    self.send(conn,req if value==self.password else -1,2,'')
                    if value!=self.password:return
                elif kind==2:
                    self.commands.append(value)
                    self.send(conn,req,0,'Test response: '+value)

    @staticmethod
    def read(conn,n):
        data=b''
        while len(data)<n:
            p=conn.recv(n-len(data))
            if not p:return b''
            data+=p
        return data

    @staticmethod
    def send(conn,req,kind,text):
        body=struct.pack('<ii',req,kind)+text.encode()+b'\0\0'
        conn.sendall(struct.pack('<i',len(body))+body)

    def close(self):
        self.sock.close()


class RconTests(unittest.TestCase):
    def test_real_loopback_rcon_login_and_command(self):
        fixture=RconFixture()
        try:
            with RconClient('127.0.0.1',fixture.port,'local-test') as c:
                self.assertEqual(c.command('list'),'Test response: list')
                self.assertEqual(c.command('say Hello'),'Test response: say Hello')
            self.assertEqual(fixture.commands,['list','say Hello'])
        finally: fixture.close()

    def test_rejects_nonlocal(self):
        with self.assertRaises(ValueError):
            RconClient('192.0.2.4',25575,'x')


class ObservationTests(unittest.TestCase):
    def test_direct_position(self):
        self.assertEqual(parse_position('Steve has the following entity data: [23.5d, 64.0d, -2.1d]'),(23.5,64.,-2.1))

    def test_player_list(self):
        self.assertEqual(parse_player_list('There are 2 of a max of 8 players online: Alex, ManhuntBot'),['Alex','ManhuntBot'])
        self.assertEqual(parse_player_list('There are 0 of a max of 8 players online:'),[])

    def test_name_validated(self):
        with self.assertRaises(ValueError):validate_name('foo; kill @a')

    def test_marker_fallback(self):
        remote=Mock()
        responses=["Can't access player data",'Summoned new Marker','Marker has the following entity data: [-2.0d, 65.5d, 3.0d]','Killed 1 entities']
        remote.command.side_effect=responses
        self.assertEqual(Observer(remote).position('Alex'), Position(-2,65.5,3))
        self.assertEqual(remote.command.call_count,4)


class MatchTests(unittest.TestCase):
    def test_role_config_and_retreat_direction(self):
        remote=Mock()
        run=ManhuntMatch(remote,'hunter',5,60)
        self.assertEqual(run.ai_role,'runner')
        bot=Position(10,70,10)
        human=Position(0,70,10)
        escape=run.escape_target(bot,human)
        self.assertGreater(escape.x,bot.x)

    def test_invalid_head_start(self):
        with self.assertRaises(ValueError):ManhuntMatch(Mock(),'hunter',-1,60)

    def test_hunter_uses_actual_python_policy(self):
        game = ManhuntMatch(Mock(),'runner',0,60)
        game.player = 'Alex'
        game.observer.position = lambda name: Position(0,64,0) if name=='Alex' else Position(10,64,0)
        game.look_and_move = Mock()
        self.assertIsNone(game.step())
        self.assertEqual(game.brain.context.last_known_position, (0,64,0))
        game.look_and_move.assert_not_called()  # Unknown terrain must not be treated as clear.

    def test_runner_retreats_away_from_human(self):
        game = ManhuntMatch(Mock(),'hunter',0,60)
        game.player='Alex'
        game.observer.position = lambda name: Position(0,64,0) if name=='Alex' else Position(8,64,0)
        game.look_and_move=Mock()
        self.assertIsNone(game.step())
        self.assertIsNotNone(game.target)
        self.assertGreater(game.target.x,8)
        game.look_and_move.assert_not_called()


class SetupTests(unittest.TestCase):
    def test_world_reset_archives_and_selects_seed(self):
        from quickstart import launch
        with TemporaryDirectory() as d:
            root=Path(d)/'server-data'
            (root/'world').mkdir(parents=True)
            (root/'world'/'level.dat').write_bytes(b'old-world')
            with patch.object(install,'SERVER',root), patch.object(launch,'SERVER',root), \
                    patch.object(launch,'local_port_open',return_value=False), \
                    patch('builtins.input',return_value='1234567'):
                launch.reset_world()
            self.assertFalse((root/'world').exists())
            backups=list((root.parent/'backups').glob('world_*'))
            self.assertEqual(len(backups),1)
            self.assertEqual((backups[0]/'level.dat').read_bytes(),b'old-world')
            self.assertIn('level-seed=1234567',(root/'server.properties').read_text())
            self.assertIn('online-mode=true',(root/'server.properties').read_text())

    def test_mod_metadata_hash_and_install(self):
        with TemporaryDirectory() as d:
            with patch.object(install, 'SERVER',Path(d)):
                v=[dict(version_type='release',date_published='2026-01-01T00:00:00Z',version_number='1.4',files=[dict(primary=True,filename='carpet-test.jar',url='https://cdn.modrinth.com/a.jar',hashes={})])]
                with patch.object(install,'json_get',return_value=v), patch.object(install,'fetch',return_value=b'fake-jar-data'):
                    install.install_mod('carpet','Carpet')
                self.assertEqual((Path(d)/'mods'/'carpet-test.jar').read_bytes(),b'fake-jar-data')


if __name__=='__main__':unittest.main()
