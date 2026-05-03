"""Routing tests — make sure messages go to the right buffers."""

from cpr_pilot.captains import Captain
from cpr_pilot.game.routing import deliver_open_channel, deliver_private


def _caps():
    return [
        Captain(name="A", boat="X", port="P", breakeven_total=60),
        Captain(name="B", boat="Y", port="P", breakeven_total=80),
        Captain(name="C", boat="Z", port="P", breakeven_total=60),
    ]


def test_open_channel_excludes_speaker():
    caps = _caps()
    deliver_open_channel(caps, "A", "hello all")
    assert len(caps[0].messages) == 0
    assert len(caps[1].messages) == 1
    assert len(caps[2].messages) == 1
    assert "hello all" in caps[1].messages[0]["content"]


def test_private_to_one():
    caps = _caps()
    deliver_private(caps, "A", "B", "secret")
    assert len(caps[0].messages) == 0
    assert len(caps[1].messages) == 1
    assert "secret" in caps[1].messages[0]["content"]
    assert len(caps[2].messages) == 0
