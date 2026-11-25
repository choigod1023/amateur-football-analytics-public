"""The pure time arithmetic of the replay page (web/replay-time.js), run with node. Skipped when node is not installed."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / 'web'
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(not NODE, reason='node is not installed')


def run(expression):
    script = "const T=require(%s);console.log(JSON.stringify(%s))" % (json.dumps(str(WEB / 'replay-time.js')), expression)
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=20, check=True).stdout
    return json.loads(out)


PIECES = 'P=[{offset:0,duration:600,start:1000},{offset:600,duration:600,start:1600},{offset:1200,duration:300,start:2400},{offset:1500,duration:120.5,start:2705}]'


def test_locate_boundaries_and_ends():
    r = run("(()=>{const %s;return [T.locate(P,0),T.locate(P,599.9),T.locate(P,600),T.locate(P,1499.99),T.locate(P,1500),T.locate(P,-5),T.locate(P,99999)]})()" % PIECES)
    assert r[0] == {'index': 0, 'local': 0}
    assert r[1]['index'] == 0 and abs(r[1]['local'] - 599.9) < 1e-9
    assert r[2] == {'index': 1, 'local': 0}                      # exactly on a boundary: the next piece
    assert r[3]['index'] == 2
    assert r[4] == {'index': 3, 'local': 0}
    assert r[5] == {'index': 0, 'local': 0}                      # before the start
    assert r[6]['index'] == 3 and abs(r[6]['local'] - 120.0) < 1e-9   # after the end: 0.5 s before it, in the last piece


def test_to_global_is_the_inverse_and_the_written_piece_is_not_cut():
    r = run("(()=>{const %s;return [T.toGlobal(P,1,30),T.toGlobal(P,0,700),T.toGlobal(P,3,130),T.toGlobal(P,9,5),T.toGlobal([],0,5)]})()" % PIECES)
    assert r == [630, 600, 1630, 1505, 0]                       # a finished piece is cut at its length, the last (still written) one is not
    for t in (0, 12.5, 599, 600, 1300, 1600):
        again = run("(()=>{const %s;const l=T.locate(P,%s);return T.toGlobal(P,l.index,l.local)})()" % (PIECES, t))
        assert abs(again - t) < 1e-9


def test_gaps_only_for_real_holes():
    r = run("(()=>{const %s;return T.gaps(P)})()" % PIECES)
    assert r == [{'at': 1200, 'seconds': 200}, {'at': 1500, 'seconds': 5}]   # piece 0->1 touches (1000+600=1600): no gap
    overlap = run("T.gaps([{offset:0,duration:600,start:0},{offset:600,duration:5,start:599.2}])")
    assert overlap == []                                         # a small overlap or a hole under 3 s is not a break
    assert run("T.gaps([])") == [] and run("T.gaps([{offset:0,duration:5,start:0}])") == []


def test_step_crosses_a_boundary_and_stops_at_the_ends():
    r = run("(()=>{const %s;return [T.step(P,595,10),T.step(P,5,-10),T.step(P,1615,10),T.total(P)]})()" % PIECES)
    assert r == [605, 0, 1620, 1620.5]
    assert run("(()=>{const %s;return T.locate(P,605)})()" % PIECES) == {'index': 1, 'local': 5}
