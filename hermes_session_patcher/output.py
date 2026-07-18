"""安全输出，避免编码问题"""
import sys

def safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(msg.encode(encoding, errors="replace").decode(encoding))
