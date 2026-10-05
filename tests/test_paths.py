import pytest

from omr import paths


def test_default_is_the_repository_corpus_folder(monkeypatch):
    monkeypatch.delenv(paths.ENV_VAR, raising=False)
    assert paths.corpus_dir() == paths.REPO_ROOT / "corpus"


def test_environment_variable_overrides_the_default(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_VAR, str(tmp_path))
    assert paths.corpus_dir() == tmp_path
    assert paths.require_corpus_dir() == tmp_path


def test_missing_configured_folder_is_an_error_and_is_not_created(monkeypatch, tmp_path):
    missing = tmp_path / "unplugged"
    monkeypatch.setenv(paths.ENV_VAR, str(missing))
    with pytest.raises(paths.CorpusDirError, match="Is the drive connected"):
        paths.require_corpus_dir()
    assert not missing.exists()


def test_free_space_check_passes_and_fails(tmp_path):
    assert paths.check_free_space(tmp_path, min_free_gb=0) >= 0
    with pytest.raises(paths.CorpusDirError, match="GB free"):
        paths.check_free_space(tmp_path, min_free_gb=10**9)
