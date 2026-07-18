"""
CLI regression tests — exit codes must be driven by ``exit_code_for`` for ANY
exception, not only ``ChromeCDPReaderError``.

Round-2 blocker fix: both ``read`` and ``screenshot`` previously did
``exit_code_for(e) if isinstance(e, ChromeCDPReaderError) else 1``,
which collapsed every unexpected error to exit 1. Now they call
``sys.exit(exit_code_for(e))`` directly, so an unknown internal error
(here: a raw ``RuntimeError``) maps to 70.
"""
import pytest
from click.testing import CliRunner

from chrome_cdp_reader.cli import cli


def _patch_core(monkeypatch, command, exc):
    """Make the bridge call used by ``command`` raise ``exc``."""
    import chrome_cdp_reader.bridge as bridge

    if command == "read":
        monkeypatch.setattr(bridge.ChromeReader, "is_connected",
                            lambda self: True)
        monkeypatch.setattr(bridge.ChromeReader, "read",
                            lambda self, *a, **k: (_ for _ in ()).throw(exc))
    else:  # screenshot
        monkeypatch.setattr(bridge.ChromeReader, "is_connected",
                            lambda self: True)
        monkeypatch.setattr(bridge.ChromeReader, "screenshot",
                            lambda self, *a, **k: (_ for _ in ()).throw(exc))


@pytest.mark.parametrize("command,args", [
    ("read", ["https://example.com"]),
    ("screenshot", ["https://example.com", "-o", "out.png"]),
])
def test_unknown_exception_exits_70(monkeypatch, command, args):
    """A raw RuntimeError is NOT a ChromeCDPReaderError but must still exit 70."""
    _patch_core(monkeypatch, command, RuntimeError("boom"))
    runner = CliRunner()
    result = runner.invoke(cli, [command, *args])
    assert result.exit_code == 70, (
        f"{command} exit={result.exit_code}, expected 70; "
        f"exc={result.exception!r}"
    )


@pytest.mark.parametrize("command,args", [
    ("read", ["https://example.com"]),
    ("screenshot", ["https://example.com", "-o", "out.png"]),
])
def test_typed_error_exits_typed_code(monkeypatch, command, args):
    from chrome_cdp_reader.errors import InvalidInputError
    _patch_core(monkeypatch, command, InvalidInputError("bad url"))
    runner = CliRunner()
    result = runner.invoke(cli, [command, *args])
    assert result.exit_code == 2, (
        f"{command} exit={result.exit_code}, expected 2 (InvalidInputError)"
    )
