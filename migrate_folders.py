#!/usr/bin/env python3
import os
import shutil
import sys
from pathlib import Path

def get_unique_filename(target_dir, filename):
    """Generate unique filename if file already exists"""
    target_path = target_dir / filename
    if not target_path.exists():
        return filename
    
    name, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_filename = f"{name}_{counter}{ext}"
        if not (target_dir / new_filename).exists():
            return new_filename
        counter += 1

def migrate_anonymous_to_authorized(anonymous_folder, authorized_uid):
    """Migrate files from anonymous folder to authorized folder and create symlink"""
    videos_dir = Path("videos")
    anonymous_path = videos_dir / anonymous_folder
    authorized_path = videos_dir / authorized_uid
    
    # Check if anonymous folder is already a symlink
    if anonymous_path.is_symlink():
        print(f"✓ {anonymous_folder} is already symlinked")
        return
    
    # Check if anonymous folder exists and has files
    if not anonymous_path.exists():
        print(f"✗ Anonymous folder {anonymous_folder} doesn't exist")
        return
    
    # Create authorized folder if it doesn't exist
    authorized_path.mkdir(exist_ok=True)
    
    # Move files from anonymous to authorized folder
    files_moved = 0
    for item in anonymous_path.iterdir():
        if item.is_file():
            unique_filename = get_unique_filename(authorized_path, item.name)
            target_path = authorized_path / unique_filename
            shutil.move(str(item), str(target_path))
            print(f"Moved: {item.name} → {unique_filename}")
            files_moved += 1
    
    # Remove empty anonymous folder
    if anonymous_path.exists() and not any(anonymous_path.iterdir()):
        anonymous_path.rmdir()
        print(f"Removed empty folder: {anonymous_folder}")
    
    # Create symlink from anonymous folder to authorized folder
    os.symlink(authorized_uid, str(anonymous_path))
    print(f"Created symlink: {anonymous_folder} → {authorized_uid}")
    print(f"✓ Migration complete: {files_moved} files moved")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python migrate_folders.py <anonymous_folder> <authorized_uid>")
        print("Example: python migrate_folders.py browser-82qkf390e ZhnkRd3vxITWzM1qpDI9rlnqjQ62")
        sys.exit(1)
    
    anonymous_folder = sys.argv[1]
    authorized_uid = sys.argv[2]
    
    migrate_anonymous_to_authorized(anonymous_folder, authorized_uid)
