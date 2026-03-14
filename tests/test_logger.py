import pytest
import re
from utils.logger import (
    log,
    type_color,
    severity_color,
    color_special_messages,
    recolor_special,
)
from colorama import Fore

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
