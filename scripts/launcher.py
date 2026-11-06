"""Launch local server then open dashboard in the default browser."""
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

root=Path(__file__).resolve().parent.parent
args=[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8765']
process=subprocess.Popen(args,cwd=root)
url='http://127.0.0.1:8765/'
try:
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError('Server exited unexpectedly. Check console logs.')
        try:
            with urllib.request.urlopen(url+'api/health',timeout=1) as response:
                if response.status==200:break
        except Exception:
            time.sleep(.25)
    else:raise RuntimeError('Server did not start in time.')
    print('AI Fanpage Company:',url)
    webbrowser.open(url)
    process.wait()
except KeyboardInterrupt:
    process.terminate()
    process.wait(timeout=10)
except Exception as exc:
    print('Launch error:',exc)
    process.terminate()
    sys.exit(1)
