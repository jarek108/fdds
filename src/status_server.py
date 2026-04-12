import os
import argparse
import subprocess

def check_status(port):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
    pid_file_path = os.path.join(project_root, f'data/run/server_{port}.pid')
    
    if not os.path.exists(pid_file_path):
        print(f"Status: Server on port {port} is NOT running (no PID file).")
        return

    with open(pid_file_path, 'r') as f:
        pid = f.read().strip()

    # On Windows, check if PID exists using tasklist
    try:
        result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
        if pid in result.stdout:
            print(f"Status: Server on port {port} is RUNNING (PID: {pid}).")
            log_file = os.path.join(project_root, f'logs/server_{port}.log')
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
