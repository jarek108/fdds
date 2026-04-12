import os
import sys
import argparse
import subprocess

def stop_server(port):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
    pid_file_path = os.path.join(project_root, f'data/run/server_{port}.pid')
    
    if not os.path.exists(pid_file_path):
        print(f"No PID file found for port {port}. Server might not be running via tools.")
        return

    with open(pid_file_path, 'r') as f:
        pid = int(f.read().strip())

    print(f"Stopping server (PID: {pid}) on port {port}...")
    
    try:
        # Use taskkill on Windows for reliable termination
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], check=True, capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"Server stopped successfully.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if os.path.exists(pid_file_path):
            os.remove(pid_file_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stop FDDS Server")
    parser.add_argument("port", type=int, nargs='?', default=8000, help="Port to stop (default: 8000)")
    args = parser.parse_args()
    
    stop_server(args.port)
