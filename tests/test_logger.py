import pytest
import re
from unittest.mock import MagicMock, patch

import pytest
from colorama import Fore

from utils.logger import (
    log,
    type_color,
    severity_color,
    color_special_messages,
    recolor_special,
)

# Helper to strip ANSI codes for easier assertions where needed
def strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


@pytest.mark.asyncio
async def test_type_color_known_and_unknown():
    # Known types
    info = await type_color("INFO")
    assert info.startswith(Fore.GREEN) and "INFO" in info and info.endswith(Fore.WHITE)

    error = await type_color("ERROR")
    assert error.startswith(Fore.RED) and "ERROR" in error and error.endswith(Fore.WHITE)

    warning = await type_color("WARNING")
    assert warning.startswith(Fore.YELLOW) and "WARNING" in warning and warning.endswith(Fore.WHITE)

    debug = await type_color("DEBUG")
    assert debug.startswith(Fore.BLUE) and "DEBUG" in debug and debug.endswith(Fore.WHITE)

    # Unknown type should be returned unchanged
    custom = await type_color("CUSTOM")
    assert custom == "CUSTOM"

@pytest.mark.asyncio
async def test_severity_color_known_and_unknown():
    low = await severity_color("LOW")
    assert low.startswith(Fore.GREEN) and "LOW" in low and low.endswith(Fore.WHITE)

    medium = await severity_color("MEDIUM")
    assert medium.startswith(Fore.YELLOW) and "MEDIUM" in medium and medium.endswith(Fore.WHITE)

    high = await severity_color("HIGH")
    assert high.startswith(Fore.RED) and "HIGH" in high and high.endswith(Fore.WHITE)

    # Unknown severity should be returned unchanged
    unknown = await severity_color("CRITICAL")
    assert unknown == "CRITICAL"

@pytest.mark.asyncio
async def test_recolor_special():
    keyword = "[Image Prompt] "
    message = f"Start {keyword}end"
    result = await recolor_special(message, keyword)
    # The keyword should be wrapped in magenta color codes
    expected = f"Start {Fore.MAGENTA}{keyword}{Fore.WHITE}end"
    assert result == expected

@pytest.mark.asyncio
async def test_color_special_messages_multiple_keywords():
    msg = (
        "[Image Prompt] foo "
        "[Activity] bar "
        "[Sending] baz "
        "[Slash Command] qux "
        "[Quote] quux "
    )
    result = await color_special_messages(msg)
    # Ensure each keyword is colored magenta
    for kw in ["[Image Prompt] ", "[Activity] ", "[Sending] ", "[Slash Command] ", "[Quote] "]:
        assert f"{Fore.MAGENTA}{kw}{Fore.WHITE}" in result

@pytest.mark.asyncio
async def test_color_special_messages_rolling_pattern():
    msg = "Result: [Rolling 1d20 -> 15] completed"
    result = await color_special_messages(msg)
    # The bracketed pattern should be colored magenta
    assert f"{Fore.MAGENTA}[Rolling 1d20 -> 15]{Fore.WHITE}" in result

@pytest.mark.asyncio
async def test_log_output(capsys):
    # Use known values for type and severity to make assertions easy
    await log("info", "Test message", "low")
    captured = capsys.readouterr()
    output = captured.out.strip()
    # Strip ANSI codes for readability in checks
    plain = strip_ansi(output)
    assert "INFO" in plain
    assert "LOW" in plain
    assert "Test message" in plain
    # Ensure the formatted log includes brackets
    assert "[INFO - LOW]" in plain or "[INFO]" in plain


@pytest.mark.asyncio
async def test_log_handles_datetime_now_exception(capsys):
    # datetime.now() raising is caught and falls back to "00:00:00"
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.side_effect = RuntimeError("clock broken")
        await log("info", "Test message", "low")
    captured = capsys.readouterr()
    plain = strip_ansi(captured.out)
    assert "00:00:00" in plain
    assert "Test message" in plain


@pytest.mark.asyncio
async def test_log_swallows_file_write_error(capsys, monkeypatch):
    # File-write failures (e.g. read-only filesystem) must not crash.
    # We patch builtins.open to raise PermissionError specifically when
    # the logger tries to write to its LOG_FILE.
    import builtins as _builtins
    from utils.logger import LOG_FILE

    real_open = _builtins.open

    def fail_on_log_file(path, *args, **kwargs):
        if str(path) == str(LOG_FILE):
            raise PermissionError("read-only filesystem")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(_builtins, "open", fail_on_log_file)
    await log("info", "Test message", "low")
    captured = capsys.readouterr()
    plain = strip_ansi(captured.out)
    # stdout path still ran
    assert "Test message" in plain


@pytest.mark.asyncio
async def test_log_appends_to_log_file(tmp_path, monkeypatch):
    # On the happy path, log() must append each line to LOG_FILE with
    # the no-color formatted form (timestamp + bracketed type/severity).
    log_file = tmp_path / "test.log"
    monkeypatch.setattr("utils.logger.LOG_FILE", str(log_file))

    await log("info", "First message", "low")
    await log("error", "Second message", "high")

    contents = log_file.read_text()
    assert "First message" in contents
    assert "Second message" in contents
    assert "[INFO - LOW]" in contents
    assert "[ERROR - HIGH]" in contents