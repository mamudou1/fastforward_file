# test_sync.py
import shutil
from pathlib import Path
from main import sync_files, Logger  # Importing the sync logic and custom Logger class

def assert_dir_structure_equal(src: Path, backup: Path):
    """
    Recursively assert that the directory structure and files in src and backup are identical.
    This helps ensure the backup mirrors the original source exactly.
    """
    # Get all relative paths of files and folders in both source and backup
    src_items = {p.relative_to(src) for p in src.rglob('*')}
    backup_items = {p.relative_to(backup) for p in backup.rglob('*')}
    
    # Compare the structures — they must be identical
    assert src_items == backup_items, f"Source and backup differ: {src_items ^ backup_items}"

def test_folder_move(tmp_path):
    # Setup temporary source and backup directories using pytest's tmp_path
    src = tmp_path / "src"
    backup = tmp_path / "backup"
    src.mkdir()
    backup.mkdir()

    # Create a folder inside the source with a file
    (src / "folder1").mkdir()
    (src / "folder1" / "file.txt").write_text("hello")

    # Initialize logger and run first sync
    logger = Logger().get_logger()
    sync_files([str(src)], str(backup), logger)

    # Move folder1 into a new folder2
    (src / "folder2").mkdir()
    shutil.move(str(src / "folder1"), str(src / "folder2" / "folder1"))

    # Run sync again after the move
    sync_files([str(src)], str(backup), logger)

    # Verify: file exists in new location in backup
    assert (backup / "folder2" / "folder1" / "file.txt").exists()
    # Verify: old folder path in backup is gone
    assert not (backup / "folder1").exists()
    # Confirm full directory structure match
    assert_dir_structure_equal(src, backup)

def test_empty_folder_move(tmp_path):
    # Setup temporary source and backup folders
    src = tmp_path / "src"
    backup = tmp_path / "backup"
    src.mkdir()
    backup.mkdir()

    # Create an empty folder in source
    (src / "empty1").mkdir()

    # Initialize logger and run first sync
    logger = Logger().get_logger()
    sync_files([str(src)], str(backup), logger)

    # Move empty1 into a new folder empty2
    (src / "empty2").mkdir()
    shutil.move(str(src / "empty1"), str(src / "empty2" / "empty1"))

    # Run sync again after move
    sync_files([str(src)], str(backup), logger)

    # Check: new location exists in backup
    assert (backup / "empty2" / "empty1").exists()
    # Check: old folder no longer exists in backup
    assert not (backup / "empty1").exists()
    # Confirm directory structure match
    assert_dir_structure_equal(src, backup)
