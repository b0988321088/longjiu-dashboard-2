import subprocess, sys, os

CRON_WORKDIR = "C:/Users/bot/Desktop/longjiu_system"
TARGET_SCRIPT = "memory_archiver.py"

target_full_path = os.path.join(CRON_WORKDIR, TARGET_SCRIPT)

if not os.path.exists(target_full_path):
    sys.stderr.write(f"ERROR: Target script not found: {target_full_path}\n")
    sys.exit(1)

try:
    r = subprocess.run([sys.executable, target_full_path] + sys.argv[1:], cwd=CRON_WORKDIR, capture_output=True, text=True, timeout=300)
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write("SUBPROCESS STDERR:\n")
        sys.stderr.write(r.stderr)
    sys.exit(r.returncode)
except Exception as e:
    sys.stderr.write(f"ERROR: Subprocess execution failed: {e}\n")
    sys.exit(1)
