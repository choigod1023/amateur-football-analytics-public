"""Check the supervisor's Windows job tears down its own listeners on hard stop."""
import os, socket, subprocess, sys, time
from pathlib import Path

root=Path(__file__).resolve().parents[1]
env={**os.environ,'DEMO_BIND_IP':'127.0.0.1','DEMO_SOURCE_IP':'127.0.0.1'}
stack=subprocess.Popen([sys.executable,'-m','app.demo_supervisor'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    time.sleep(5)
    if stack.poll() is not None: raise RuntimeError('Supervisor failed to start')
finally:
    if stack.poll() is None: stack.kill(); stack.wait()
time.sleep(2)
for kind,port in ((socket.SOCK_STREAM,8000),(socket.SOCK_STREAM,8443),(socket.SOCK_STREAM,18554),(socket.SOCK_DGRAM,8890)):
    with socket.socket(socket.AF_INET,kind) as s:
        if os.name == 'nt': s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        s.bind(('127.0.0.1',port))
print('hard_stop_listeners_cleared=True')
