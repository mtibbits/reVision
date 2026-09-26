import pytest

from revision_engine import __version__
from revision_engine.cli import main


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_subcommand_prints_help_and_fails(capsys):
    assert main([]) == 2
    assert "rv2" in capsys.readouterr().err
