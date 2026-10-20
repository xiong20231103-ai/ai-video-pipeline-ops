"""Explicit future launch wrapper. Import has no app/process/config side effects.

Claude must first inspect every Dashboard startup/watchdog path and arrange an
idle deployment. This turn never invokes main or restarts the home Dashboard.
"""
def main():
    import argparse,sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    parser=argparse.ArgumentParser();parser.add_argument('--fence-root',required=True,type=Path);args=parser.parse_args()
    from agent.core.ordinary_fence import OrdinaryFence
    from agent.core.ordinary_ingress import FencedDashboard
    fence=OrdinaryFence(args.fence_root);fence.status() # Fail before importing app if unprepared.
    import app,uvicorn
    uvicorn.run(FencedDashboard(app.app,fence),host=str(app.CONFIG['listen_host']),port=int(app.CONFIG['listen_port']),reload=False,access_log=False)
if __name__=='__main__':main()
