from pisetup.system import CommandFailed, System


def test_real_runner(tmp_path):
    sys = System(tmp_path)
    assert sys.run("sh", "-c", "echo hi", capture=True).stdout == "hi\n"
    assert sys.run("no-such-command-here", check=False).returncode == 127
    assert not sys.has_command("no-such-command-here")
    try:
        sys.run("false")
    except CommandFailed as e:
        assert "false" in str(e)
    else:
        raise AssertionError("expected CommandFailed")


def test_files(tmp_path):
    sys = System(tmp_path)
    assert sys.write("/etc/x.conf", "a", mode=0o600)
    assert not sys.write("/etc/x.conf", "a")
    assert (tmp_path / "etc/x.conf").read_text() == "a"
    assert sys.read("/missing", "d") == "d"
