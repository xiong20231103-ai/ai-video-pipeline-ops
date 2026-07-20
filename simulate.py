from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATUS_FILE = DATA_DIR / "simulation.status.json"
OFFLINE_FLAG = DATA_DIR / "offline.flag"
DB_PATH = DATA_DIR / "ops.db"

SCENARIOS = {
    "running": ("RecognizingCaptions", "识别字幕", ""),
    "exporting": ("Exporting", "2K导出", ""),
    "completed": ("Completed", "剪辑完成", ""),
    "failed": ("Failed", "剪辑失败", "模拟：CapCut导出窗口超时"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="OPS Dashboard 状态模拟器")
    parser.add_argument(
        "scenario",
        choices=[*SCENARIOS, "offline", "reset"],
        help="running/exporting/completed/failed/offline/reset",
    )
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.scenario == "reset":
        STATUS_FILE.unlink(missing_ok=True)
        OFFLINE_FLAG.unlink(missing_ok=True)
        if DB_PATH.exists():
            with sqlite3.connect(DB_PATH) as db:
                db.execute("DELETE FROM tasks WHERE task_id='ops-demo-task-001'")
                db.execute("DELETE FROM task_history WHERE task_id='ops-demo-task-001'")
        print("模拟状态已清除。")
        return
    if args.scenario == "offline":
        OFFLINE_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
        print("已模拟机器离线。使用 reset 恢复。")
        return

    OFFLINE_FLAG.unlink(missing_ok=True)
    state, text, error = SCENARIOS[args.scenario]
    payload = {
        "schemaVersion": 1,
        "batchId": "OPS-DEMO-001",
        "date": "演示",
        "updatedAt": datetime.now().astimezone().isoformat(),
        "running": state not in {"Completed", "Failed"},
        "paused": False,
        "total": 1,
        "completed": 1 if state == "Completed" else 0,
        "failed": 1 if state == "Failed" else 0,
        "tasks": [{
            "taskId": "ops-demo-task-001",
            "state": state,
            "stateText": text,
            "project": "云手机",
            "material": "碳岩板",
            "language": "西班牙语",
            "number": "003",
            "sequence": 1,
            "videoPath": "E:\\生成视频\\演示\\云手机\\演示视频.mp4",
            "audioPath": "E:\\音频\\演示\\演示音频.mp3",
            "outputPath": "E:\\演示\\云手机\\演示成片.mp4",
            "error": error,
        }],
    }
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入模拟状态：{text}")


if __name__ == "__main__":
    main()
