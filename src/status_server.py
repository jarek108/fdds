import os
import sys
import argparse
import subprocess

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from src.utils.config import PATHS

def check_status(port):
    pid_file_path = os.path.join(PATHS['run_dir'], f'server_{port}.pid')
    
    if not os.path.exists(pid_file_path):
        print(f"Status: Server on port {port} is NOT running (no PID file at {pid_file_path}).")
        return

    with open(pid_file_path, 'r') as f:
        pid = f.read().strip()

    # On Windows, check if PID exists using tasklist
    try:
        result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
        if pid in result.stdout:
            print(f"Status: Server on port {port} is RUNNING (PID: {pid}).")
            log_file = os.path.join(PATHS['server_logs_dir'], f'server_{port}.log')
            if os.path.exists(log_file):
                print(f"Logs: {log_file}")
        else:
            print(f"Status: Server on port {port} is STALE (PID file exists but process {pid} is dead).")
    except Exception as e:
        print(f"Error checking status: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check FDDS Server Status")
    parser.add_argument("port", type=int, nargs='?', default=8000, help="Port to check (default: 8000)")
    args = parser.parse_args()
    check_status(args.port)
