# Takes in log type, severity, and message and logs it neatly to the console

import datetime
from colorama import Fore, Back, Style
import re
import json
import aiohttp
import os


async def log(type, message, severity=""):
    try:
        # Date and time (am/pm)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S%p")
    except:
        timestamp = "00:00:00"
    timestamp = f"{Fore.LIGHTBLACK_EX}{timestamp}{Fore.WHITE}"
    type = await type_color(type.upper())
    severity = await severity_color(severity.upper())
    message = await color_special_messages(message.replace("\n", ""))

    if severity == "":
        log = f"{timestamp} [{type}] {message}"
    else:
        log = f"{timestamp} [{type} - {severity}] {message}"
    print(log)


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
        