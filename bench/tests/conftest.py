import pytest


@pytest.fixture(autouse=True)
def no_real_keychain():
    """The tagger's API route reads a key saved in the computer's keychain; no bench test may touch a real one."""
    import closet_bench  # noqa: F401  (puts backend/ on the import path)
    from closet import apikey
    apikey.use_store(apikey.NoKeychain())
    yield
    apikey.use_store(None)
