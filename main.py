import os
import shutil
import sqlite3
import yaml
from pathlib import Path
from hashlib import sha256
from datetime import datetime

def load_config():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    return config["folders"], config["backup_path"]

def get_file_hash(file_path):
    hasher = sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def list_files(folder):
    return [f for f in Path(folder).rglob("*") if f.is_file()]

def create_database():
    conn = sqlite3.connect("db.sqlite3")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_path TEXT,
            backup_path TEXT,
            last_modified TEXT,
            file_hash TEXT
        )
    """)
    conn.commit()
    return conn

def backup_and_record_file(file_path, backup_root, conn):
    file_hash = get_file_hash(file_path)
    modified_time = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
    relative_path = file_path.relative_to(file_path.parents[1])  # Adjust depth as needed
    backup_path = Path(backup_root) / relative_path

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, backup_path)

    conn.execute("""
        INSERT INTO files (original_path, backup_path, last_modified, file_hash)
        VALUES (?, ?, ?, ?)
    """, (str(file_path), str(backup_path), modified_time, file_hash))
    conn.commit()

def sync_files(folders, backup_path):
    conn = create_database()
    cursor = conn.cursor()

    existing_files = {
        row[0]: {"hash": row[1], "modified": row[2]}
        for row in cursor.execute("SELECT original_path, file_hash, last_modified FROM files")
    }

    current_files = set()

    for folder in folders:
        for file in list_files(folder):
            file_str = str(file)
            current_files.add(file_str)
            file_hash = get_file_hash(file)
            modified_time = datetime.fromtimestamp(file.stat().st_mtime).isoformat()

            if file_str not in existing_files:
                print(f"New file found: {file_str}")
                backup_and_record_file(file, backup_path, conn)
            elif existing_files[file_str]["hash"] != file_hash:
                print(f"File modified: {file_str}")
                cursor.execute("DELETE FROM files WHERE original_path = ?", (file_str,))
                backup_and_record_file(file, backup_path, conn)

    for db_path in existing_files:
        if db_path not in current_files:
            print(f"File deleted: {db_path}")
            cursor.execute("SELECT backup_path FROM files WHERE original_path = ?", (db_path,))
            backup_file = cursor.fetchone()
            if backup_file:
                try:
                    Path(backup_file[0]).unlink()
                except FileNotFoundError:
                    pass
            cursor.execute("DELETE FROM files WHERE original_path = ?", (db_path,))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    folders, backup_path = load_config()
    sync_files(folders, backup_path)
