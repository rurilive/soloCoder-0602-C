import sqlite3
import sys
from pathlib import Path

db_path = Path(__file__).parent / "asset_management.db"


def migrate():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(approval_chain_nodes)")
        columns = [col[1] for col in cursor.fetchall()]

        if "sub_process_chain_id" not in columns:
            print("Adding sub_process_chain_id to approval_chain_nodes...")
            cursor.execute("""
                ALTER TABLE approval_chain_nodes
                ADD COLUMN sub_process_chain_id INTEGER REFERENCES approval_chains(id)
            """)
            print("✓ sub_process_chain_id added")
        else:
            print("sub_process_chain_id already exists in approval_chain_nodes")

        cursor.execute("PRAGMA table_info(approval_node_records)")
        columns = [col[1] for col in cursor.fetchall()]

        columns_to_add = [
            ("sub_process_id", "INTEGER REFERENCES approvals(id)"),
            ("sub_process_nesting_level", "INTEGER NOT NULL DEFAULT 0"),
            ("parent_record_id", "INTEGER REFERENCES approval_node_records(id)"),
            ("node_type", "VARCHAR(50)"),
            ("sub_process_chain_id", "INTEGER REFERENCES approval_chains(id)"),
        ]

        for col_name, col_def in columns_to_add:
            if col_name not in columns:
                print(f"Adding {col_name} to approval_node_records...")
                cursor.execute(f"""
                    ALTER TABLE approval_node_records
                    ADD COLUMN {col_name} {col_def}
                """)
                print(f"✓ {col_name} added")
            else:
                print(f"{col_name} already exists in approval_node_records")

        conn.commit()
        print("\n✓ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
