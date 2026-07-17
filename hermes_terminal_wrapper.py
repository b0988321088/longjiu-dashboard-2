#!/usr/bin/env python3
"""hermes_terminal_wrapper.py - retry + timeout hardened terminal wrapper"""

import subprocess
import sys
import time

DEFAULT_TIMEOUT = 180
MAX_RETRIES = 3
RETRY_ON = [
    "timed out",
    "timeout",
    "ConnectionError",
    "HTTPSConnectionPool",
    "Read timed out",
]


def run(cmd, timeout=DEFAULT_TIMEOUT, retries=MAX_RETRIES):
    attempt = 0
    last_err = None
    while attempt < retries:
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = res.stdout or ""
            err = res.stderr or ""
            if res.returncode == 0:
                return out
            combined = out + ("\n[stderr] " + err if err else "")
            if any(t.lower() in combined.lower() for t in RETRY_ON):
                last_err = combined
                attempt += 1
                time.sleep(2 ** attempt)
                continue
            return combined
        except subprocess.TimeoutExpired:
            last_err = "timeout"
            attempt += 1
            time.sleep(2 ** attempt)
        except Exception as e:
            return "wrapper_error: " + str(e)
    return "[retry_exhausted after {} attempts]\n{}".format(retries, last_err)


if __name__ == "__main__":
    cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "pwd"
    print(run(cmd))
