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
    hasher = sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

# ---------- List all files recursively in a folder ----------
def list_files(folder):
    return [f for f in Path(folder).rglob("*") if f.is_file()]

# ---------- Initialize SQLite database ----------
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

# ---------- Get common roots for all monitored folders (handles multiple drives) ----------
def get_common_roots(folders):
    """
    Returns a dict mapping each drive/root to a list of folders on that drive/root.
    Example: {'C:\\': [...], 'D:\\': [...]}
    """
    roots = {}
    for folder in folders:
        p = Path(folder).resolve()
        try:
            drive = p.drive if p.drive else p.anchor
        except Exception:
            drive = str(p)
        roots.setdefault(drive, []).append(str(p))
    return roots

# ---------- Get relative path based on common root ----------
def get_relative_path(file_path, common_root):
    return Path(file_path).resolve().relative_to(common_root)

# ---------- Storage Backend Abstraction ----------
class LocalStorageBackend:
    def list_files(self, folder):
        return [f for f in Path(folder).rglob("*") if f.is_file()]
    def list_dirs(self, folder):
        return [d for d in Path(folder).rglob("*") if d.is_dir()]
    def mkdir(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)
    def rmdir(self, path):
        Path(path).rmdir()
    def copy2(self, src, dst):
        shutil.copy2(src, dst)
    def unlink(self, path):
        Path(path).unlink(missing_ok=True)

# ---------- Mirror a file into the backup folder, preserving relative path ----------
def backup_and_record_file(file_path, common_root, backup_root, conn, storage: LocalStorageBackend):
    file_hash = get_file_hash(file_path)
    modified_time = datetime.fromtimestamp(Path(file_path).stat().st_mtime).isoformat()
    relative_path = get_relative_path(file_path, common_root)
    backup_path = Path(backup_root) / relative_path
    storage.mkdir(backup_path.parent)
    storage.copy2(file_path, backup_path)
    log.info(f"Backed up file: {file_path} -> {backup_path}")
    conn.execute("""
        INSERT INTO files (original_path, backup_path, last_modified, file_hash)
        VALUES (?, ?, ?, ?)
    """, (str(file_path), str(backup_path), modified_time, file_hash))
    conn.commit()

# ---------- Clean up empty directories in backup ----------
def cleanup_empty_dirs(backup_root, valid_dirs, storage: LocalStorageBackend):
    removed = True
    while removed:
        removed = False
        for root, dirs, files in os.walk(backup_root, topdown=False):
            if not dirs and not files and str(Path(root).resolve()) not in valid_dirs:
                storage.rmdir(root)
                log.info(f"Removed empty backup directory: {root}")
                removed = True

# ---------- Main sync logic ----------
def sync_files(monitored_folders, backup_root):
    """
    Synchronize files and folders:
    - Keep mirrored structure in backup.
    - Track new, modified, moved, or deleted files.
    - Clean up backup to match current structure.
    Handles multiple drives by syncing each group separately.
    """
    conn = create_database()
    storage = LocalStorageBackend()
    roots_map = get_common_roots(monitored_folders)
    for root, folders_on_root in roots_map.items():
        # If only one folder, use its parent as common root
        if len(folders_on_root) == 1:
            common_root = str(Path(folders_on_root[0]).parent)
        else:
            common_root = os.path.commonpath(folders_on_root)
        cursor = conn.cursor()
        db_records = {
            row[0]: {"backup_path": row[1], "hash": row[2], "modified": row[3]}
            for row in cursor.execute("SELECT original_path, backup_path, file_hash, last_modified FROM files")
        }
        current_paths = set()
        # --- Mirror all folders (including empty ones) ---
        all_dirs = set()
        for folder in folders_on_root:
            for dirpath, dirnames, filenames in os.walk(folder):
                rel_dir = Path(dirpath).resolve().relative_to(common_root)
                backup_dir = Path(backup_root) / rel_dir
                all_dirs.add(str(backup_dir.resolve()))
                if not Path(backup_dir).exists():
                    storage.mkdir(backup_dir)
                    log.info(f"Created backup folder: {backup_dir}")
        # --- Scan all files in monitored folders ---
        for folder in folders_on_root:
            for file in storage.list_files(folder):
                file_str = str(Path(file).resolve())
                current_paths.add(file_str)
                file_hash = get_file_hash(file)
                modified_time = datetime.fromtimestamp(Path(file).stat().st_mtime).isoformat()
                # New file
                if file_str not in db_records:
                    backup_and_record_file(file, common_root, backup_root, conn, storage)
                # Modified file
                elif db_records[file_str]["hash"] != file_hash:
                    log.info(f"File modified: {file_str}")
                    cursor.execute("DELETE FROM files WHERE original_path = ?", (file_str,))
                    backup_and_record_file(file, common_root, backup_root, conn, storage)
        # --- Handle deleted or moved files/folders ---
        for db_path in list(db_records.keys()):
            if db_path not in current_paths:
                log.info(f"File or folder deleted/moved: {db_path}")
                backup_file = db_records[db_path]["backup_path"]
                try:
                    storage.unlink(backup_file)
                    log.info(f"Removed backup: {backup_file}")
                except FileNotFoundError:
                    log.warning(f"Backup already missing: {backup_file}")
                cursor.execute("DELETE FROM files WHERE original_path = ?", (db_path,))
        # --- Clean up empty directories in backup that no longer exist in source ---
        cleanup_empty_dirs(backup_root, all_dirs, storage)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    config = load_config()
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
