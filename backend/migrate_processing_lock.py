"""
数据库迁移脚本：为审批超时并发锁机制添加数据库结构。
独立于应用启动执行，可在部署前运行。

执行方式：
    cd backend && python3 migrate_processing_lock.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "asset_management.db")


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"[迁移] 数据库文件不存在: {DB_PATH}，跳过迁移（应用首次启动会自动建表）")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_locks'")
        if cursor.fetchone() is None:
            cursor.execute(
                "CREATE TABLE task_locks ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "task_name VARCHAR(128) UNIQUE NOT NULL, "
                "locked_by VARCHAR(128), "
                "locked_at DATETIME, "
                "expires_at DATETIME, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_task_locks_task_name ON task_locks(task_name)")
            print("[迁移] 已创建 task_locks 表")
        else:
            print("[迁移] task_locks 表已存在，跳过")

        cursor.execute("PRAGMA table_info(approvals)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "processing_lock" not in existing_cols:
            cursor.execute("ALTER TABLE approvals ADD COLUMN processing_lock VARCHAR(128)")
            print("[迁移] approvals 表已新增 processing_lock 列")
        else:
            print("[迁移] approvals.processing_lock 已存在，跳过")

        cursor.execute("PRAGMA table_info(approvals)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "processing_locked_at" not in existing_cols:
            cursor.execute("ALTER TABLE approvals ADD COLUMN processing_locked_at DATETIME")
            print("[迁移] approvals 表已新增 processing_locked_at 列")
        else:
            print("[迁移] approvals.processing_locked_at 已存在，跳过")

        conn.commit()
        print("[迁移] 全部迁移完成 ✓")

    except Exception as e:
        conn.rollback()
        print(f"[迁移] 迁移失败: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
