from cfo.core import profile as core
from cfo.util import paths


def test_load_missing_returns_none(tmp_data_dir):
    assert core.load() is None


def test_save_and_load(tmp_data_dir):
    core.save("# Jack\n\nAge: 28\n")
    assert core.load() == "# Jack\n\nAge: 28\n"
    # file actually written
    assert paths.profile_md().exists()
