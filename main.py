import os
import shutil
import sqlite3
import yaml
from pathlib import Path
from hashlib import sha256
from datetime import datetime
import log  # Use your custom log module

# ---------- Load configuration from YAML ----------
def load_config(config_path="config.yaml"):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

# ---------- Compute a SHA256 hash of a file ----------
def get_file_hash(file_path):
    # Create SHA256 hasher
    hasher = sha256()
    # Read file in chunks to compute hash
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

# ---------- List all files recursively in a folder ----------
def list_files(folder):
    # Return all files (not folders) in directory and subdirectories
    return [f for f in Path(folder).rglob("*") if f.is_file()]

# ---------- Initialize SQLite database ----------
def create_database():
    # Connect to SQLite database (creates if not exists)
    conn = sqlite3.connect("db.sqlite3")
    cursor = conn.cursor()
    # Create table if not already present
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

# ---------- Get common root of monitored folders ----------
def get_common_root(folders):
    """
    Find the common root directory shared among all monitored folders.
    Useful for reconstructing accurate relative paths for backup.
    """
    paths = [Path(f).resolve() for f in folders]
    return os.path.commonpath(paths)

# ---------- Get relative path based on common root ----------
def get_relative_path(file_path, common_root):
    """
    Compute the path of a file relative to the common root.
    This helps recreate the folder structure in the backup location.
    """
    return Path(file_path).resolve().relative_to(common_root)

# ---------- Mirror a file into the backup folder, preserving relative path ----------
def backup_and_record_file(file_path, common_root, backup_root, conn):
    """
    Back up a single file and record its info in the database.
    Keeps directory structure same as source.
    """
    file_hash = get_file_hash(file_path)
    modified_time = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
    relative_path = get_relative_path(file_path, common_root)
    backup_path = Path(backup_root) / relative_path

    # Make sure backup subfolders exist
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy file to the backup location
    shutil.copy2(file_path, backup_path)

    # Add a new record to the database
    conn.execute("""
        INSERT INTO files (original_path, backup_path, last_modified, file_hash)
        VALUES (?, ?, ?, ?)
    """, (str(file_path), str(backup_path), modified_time, file_hash))
    conn.commit()

# ---------- Main sync logic ----------
def sync_files(monitored_folders, backup_root):
    """
    Synchronize files and folders:
    - Keep mirrored structure in backup.
    - Track new, modified, moved, or deleted files.
    - Clean up backup to match current structure.
    """
    # Logging is now handled globally via log.py
    conn = create_database()
    cursor = conn.cursor()
    db_records = {
        row[0]: {"backup_path": row[1], "hash": row[2], "modified": row[3]}
        for row in cursor.execute("SELECT original_path, backup_path, file_hash, last_modified FROM files")
    }
    current_paths = set()
    common_root = get_common_root(monitored_folders)

    # --- Mirror all folders (including empty ones) ---
    all_dirs = set()
    for folder in monitored_folders:
        for dirpath, dirnames, filenames in os.walk(folder):
            rel_dir = Path(dirpath).resolve().relative_to(common_root)
            backup_dir = Path(backup_root) / rel_dir
            all_dirs.add(str(backup_dir.resolve()))
            if not backup_dir.exists():
                backup_dir.mkdir(parents=True, exist_ok=True)
                log.info(f"Created backup folder: {backup_dir}")

    # --- Scan all files in monitored folders ---
    for folder in monitored_folders:
        folder = Path(folder).resolve()
        for file in list_files(folder):
            file_str = str(file.resolve())
            current_paths.add(file_str)
            file_hash = get_file_hash(file)
            modified_time = datetime.fromtimestamp(file.stat().st_mtime).isoformat()

            # New file
            if file_str not in db_records:
                backup_and_record_file(file, common_root, backup_root, conn)
                log.info(f"Backed up file: {file} → {Path(backup_root) / get_relative_path(file, common_root)}")

            # Modified file
            elif db_records[file_str]["hash"] != file_hash:
                log.info(f"File modified: {file_str}")
                cursor.execute("DELETE FROM files WHERE original_path = ?", (file_str,))
                backup_and_record_file(file, common_root, backup_root, conn)
                log.info(f"Updated backup for: {file_str}")

    # --- Handle deleted or moved files/folders ---
    for db_path in list(db_records.keys()):
        if db_path not in current_paths:
            log.info(f"File or folder deleted/moved: {db_path}")
            backup_file = db_records[db_path]["backup_path"]
            try:
                Path(backup_file).unlink()
                log.info(f"Removed backup: {backup_file}")
            except FileNotFoundError:
                log.warning(f"Backup already missing: {backup_file}")
            cursor.execute("DELETE FROM files WHERE original_path = ?", (db_path,))

    # --- Clean up empty directories in backup that no longer exist in source ---
    for root, dirs, files in os.walk(backup_root, topdown=False):
        if not dirs and not files and str(Path(root).resolve()) not in all_dirs:
            Path(root).rmdir()
            log.info(f"Removed empty backup directory: {root}")

    conn.commit()
    conn.close()

# ---------- Main Runner ----------
if __name__ == "__main__":
    config = load_config()
    # Map config log level string to log.Level enum
    level_map = {
        "DEBUG": log.Level.DEBUG,
        "INFO": log.Level.INFO,
        "WARNING": log.Level.WARNING,
        "ERROR": log.Level.ERROR,
        "CRITICAL": log.Level.CRITICAL,
    }
    log.init(
        verbosity=level_map.get(config.get("log_level", "INFO").upper(), log.Level.INFO),
        log_file=config.get("log_file", "sync.log"),
    )
    sync_files(
        monitored_folders=config["folders"],
        backup_root=config["backup_path"],
    )
