"""Task entry point; maintenance blocks imports and credential reads."""
import os
from pathlib import Path
import sys

if __name__=='__main__':
    state=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'OpsAgent'
    if (state/'maintenance.json').exists() or (state/'stop-request.json').exists():
        raise SystemExit(0)
    try:
        from agent.readonly import main
        main()
    except KeyboardInterrupt: pass
    except Exception:
        sys.stderr.write('Read-only agent stopped after a runtime error; no credential values logged.\n')
        raise SystemExit(1) from None
