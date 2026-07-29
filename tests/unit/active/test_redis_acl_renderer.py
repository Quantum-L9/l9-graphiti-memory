import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).parents[3] / "tools/assurance/render_active_memory_redis_acl.py"
spec = importlib.util.spec_from_file_location("acl_renderer", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def arguments(**kw):
    class A:
        pass

    a = A()
    a.username = "active-memory"
    a.key_prefix = "l9gm:active"
    a.channel_prefix = None
    a.deployment_hash = "0" * 16
    a.password_hash = "a" * 64
    a.allow_nopass_development = False
    a.format = "acl-file"
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def manifest():
    return mod.load(
        Path(__file__).parents[3]
        / "src/l9_graphite_memory/resources/active_memory_redis_capabilities.yaml"
    )


def test_secure_acl_is_reset_first_and_restricted():
    out = mod.render(arguments(), manifest())
    assert " reset on #" in out
    assert " resetkeys " in out
    assert " resetchannels " in out
    assert " -@all " in out
    assert "+@" not in out
    assert " nopass " not in out


def test_nopass_rejected_without_explicit_dev_flag():
    with pytest.raises(ValueError):
        mod.render(arguments(password_hash=None), manifest())


def test_explicit_development_nopass():
    assert " nopass " in mod.render(
        arguments(password_hash=None, allow_nopass_development=True), manifest()
    )


def test_psubscribe_not_granted():
    assert "+psubscribe" not in mod.render(arguments(), manifest())
