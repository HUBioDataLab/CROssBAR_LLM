"""Suite-wide pytest configuration for the Paperclip tests."""


def pytest_configure(config):
    """Reassert pytest-asyncio's auto mode, which this suite requires.

    `asyncio_mode = auto` lives in this directory's pytest.ini, but pytest only
    honours that file when the suite is the sole command-line argument. Name it
    alongside another directory and their common ancestor wins instead, leaving
    every async test here in strict mode and unmarked, so all of them error.
    Setting it here keeps the requirement with the package rather than with how
    pytest happened to be invoked.
    """
    if config.getoption("asyncio_mode", None) != "auto":
        config.option.asyncio_mode = "auto"
    config.addinivalue_line(
        "markers", "live: hits the real upstream service; needs credentials"
    )
