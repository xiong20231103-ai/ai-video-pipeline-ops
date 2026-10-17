"""Task entry point: never send configuration or credential-bearing exceptions to logs."""
import sys
from agent.readonly import main

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: pass
    except Exception:
        sys.stderr.write('Read-only agent stopped after a runtime error; no credential values logged.\n')
        raise SystemExit(1) from None
