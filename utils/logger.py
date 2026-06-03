import datetime
from colorama import Fore
import re
import os

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rolm.log")

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None



async def log(type, message, severity=""):
    try:
        # Date and time (am/pm)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S%p")
    except:
        timestamp = "00:00:00"
    timestamp_str = f"{Fore.LIGHTBLACK_EX}{timestamp}{Fore.WHITE}"
    type_str = await type_color(type.upper())
    severity_str = await severity_color(severity.upper())
    message_str = await color_special_messages(message.replace("\n", ""))

    if severity == "":
        log_line = f"{timestamp} [{type.upper()}] {message}"
        colored = f"{timestamp_str} [{type_str}] {message_str}"
    else:
        log_line = f"{timestamp} [{type.upper()} - {severity.upper()}] {message}"
        colored = f"{timestamp_str} [{type_str} - {severity_str}] {message_str}"
    print(colored)
    # Append to file
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception:
        pass


async def type_color(type):
    if type == "INFO":
        return f"{Fore.GREEN}{type}{Fore.WHITE}"
    elif type == "ERROR":
        return f"{Fore.RED}{type}{Fore.WHITE}"
    elif type == "WARNING":
        return f"{Fore.YELLOW}{type}{Fore.WHITE}"
    elif type == "DEBUG":
        return f"{Fore.BLUE}{type}{Fore.WHITE}"
    else:
        return type
    

async def severity_color(severity):
    if severity == "LOW":
        return f"{Fore.GREEN}{severity}{Fore.WHITE}"
    elif severity == "MEDIUM":
        return f"{Fore.YELLOW}{severity}{Fore.WHITE}"
    elif severity == "HIGH":
        return f"{Fore.RED}{severity}{Fore.WHITE}"
    else:
        return severity
    
    
async def color_special_messages(message):
    if "[Image Prompt] " in message:
        message = await recolor_special(message, "[Image Prompt] ")
    if "[Activity] " in message:
        message = await recolor_special(message, "[Activity] ")
    if "[Sending] " in message:
        message = await recolor_special(message, "[Sending] ")
    pattern = r"\[Rolling 1d\d+ -> \d+\]"
    match = re.search(pattern, message)
    if match:
        matched_string = match.group(0)
        message = await recolor_special(message, matched_string)
    if "[Slash Command] " in message:
        message = await recolor_special(message, "[Slash Command] ")
    if "[Quote] " in message:
        message = await recolor_special(message, "[Quote] ")
    return message


async def recolor_special(message, keyword):
    return message.replace(keyword, f"{Fore.MAGENTA}{keyword}{Fore.WHITE}")
        