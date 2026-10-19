"""Server terminal entry point: hidden secrets; no URLs/keys/provider errors printed."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud.notification_setup import main
if __name__=='__main__':main()
