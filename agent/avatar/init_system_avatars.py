"""
Initialize system default avatars.

This script copies system default avatar images from the frontend assets
to the user data directory for runtime use.
"""

import os
import shutil
from pathlib import Path
from config.app_info import app_info
from utils.logger_helper import logger_helper as logger

def init_system_avatars(force: bool = False) -> bool:
    """
    Initialize system default avatars by copying them to project resource directory.
    
    System avatars are stored in the project's resource/avatars directory,
    not in user's AppData directory.
    
    Args:
        force: If True, overwrite existing files
        
    Returns:
        bool: True if successful
    """
    try:
        
        # Source: frontend assets
        project_root = Path(__file__).parent.parent.parent
        image_source_dir = project_root / "gui_v2" / "src" / "assets"
        video_source_dir = project_root / "gui_v2" / "src" / "assets" / "gifs"
        
        # Destination: project resource/avatars/system directory (system avatars)
        resource_dir = Path(app_info.app_resources_path)
        dest_dir = resource_dir / "avatars" / "system"
        
        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # System avatar files (images from assets/, videos from assets/gifs/)
        # Note: A004 is missing, agent videos map to: agent0->A001, agent1->A002, etc.
        system_avatars = [
            ("A001.png", image_source_dir, "A001.png"),
            ("A001.mp4", video_source_dir, "agent0.mp4"),
            ("A001.webm", video_source_dir, "agent0.webm"),
            ("A002.png", image_source_dir, "A002.png"),
            ("A002.mp4", video_source_dir, "agent1.mp4"),
            ("A002.webm", video_source_dir, "agent1.webm"),
            ("A003.png", image_source_dir, "A003.png"),
            ("A003.mp4", video_source_dir, "agent2.mp4"),
            ("A003.webm", video_source_dir, "agent2.webm"),
            # A004 is missing
            ("A005.png", image_source_dir, "A005.png"),
            ("A005.mp4", video_source_dir, "agent3.mp4"),
            ("A005.webm", video_source_dir, "agent3.webm"),
            ("A006.png", image_source_dir, "A006.png"),
            ("A006.mp4", video_source_dir, "agent4.mp4"),
            ("A006.webm", video_source_dir, "agent4.webm"),
            ("A007.png", image_source_dir, "A007.png"),
            ("A007.mp4", video_source_dir, "agent5.mp4"),
            ("A007.webm", video_source_dir, "agent5.webm"),
        ]
        
        copied_count = 0
        skipped_count = 0
        missing_count = 0
        
        for dest_filename, source_dir, source_filename in system_avatars:
            source_file = source_dir / source_filename
            dest_file = dest_dir / dest_filename
            
            # Check if source exists
            if not source_file.exists():
                logger.warning(f"[InitAvatars] Source file not found: {source_file}")
                missing_count += 1
                continue
            
            # Check if destination exists
            if dest_file.exists() and not force:
                logger.debug(f"[InitAvatars] File already exists, skipping: {dest_filename}")
                skipped_count += 1
                continue
            
            # Copy file
            try:
                shutil.copy2(source_file, dest_file)
                logger.info(f"[InitAvatars] Copied: {source_filename} -> {dest_filename}")
                copied_count += 1
            except Exception as e:
                logger.error(f"[InitAvatars] Failed to copy {dest_filename}: {e}")
        
        # Summary
        logger.info(
            f"[InitAvatars] Summary: "
            f"Copied={copied_count}, Skipped={skipped_count}, Missing={missing_count}"
        )
        
        if missing_count > 0:
            logger.warning(
                f"[InitAvatars] {missing_count} avatar files are missing. "
                f"Please ensure all A001-A007 images and videos are present in gui_v2/src/assets/"
            )
        
        return True
        
    except Exception as e:
        logger.error(f"[InitAvatars] Failed to initialize system avatars: {e}", exc_info=True)
        return False


def check_system_avatars() -> dict:
    """
    Check which system avatars are available.
    
    Returns:
        dict: Status of each avatar file
    """
    try:
        
        resource_dir = Path(app_info.app_resources_path)
        avatars_dir = resource_dir / "avatars" / "system"
        
        status = {}
        
        for i in range(1, 8):
            avatar_id = f"A{i:03d}"
            image_file = avatars_dir / f"{avatar_id}.png"
            video_file = avatars_dir / f"{avatar_id}.mp4"
            
            status[avatar_id] = {
                "image_exists": image_file.exists(),
                "image_path": str(image_file) if image_file.exists() else None,
                "video_exists": video_file.exists(),
                "video_path": str(video_file) if video_file.exists() else None
            }
        
        return status
        
    except Exception as e:
        logger.error(f"[InitAvatars] Failed to check system avatars: {e}")
        return {}


# if __name__ == "__main__":
#     # Setup logging
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
#     )
    
#     print("=" * 60)
#     print("System Avatar Initialization")
#     print("=" * 60)
    
#     # Initialize
#     success = init_system_avatars(force=False)
    
#     if success:
#         print("\n✅ Initialization completed")
        
#         # Check status
#         print("\nAvatar Status:")
#         print("-" * 60)
#         status = check_system_avatars()
        
#         for avatar_id, info in status.items():
#             image_status = "✅" if info["image_exists"] else "❌"
#             video_status = "✅" if info["video_exists"] else "⚠️"
#             print(f"{avatar_id}: Image {image_status}  Video {video_status}")
        
#         print("-" * 60)
        
#         # Summary
#         total_images = sum(1 for info in status.values() if info["image_exists"])
#         total_videos = sum(1 for info in status.values() if info["video_exists"])
        
#         print(f"\nTotal: {total_images}/7 images, {total_videos}/7 videos")
        
#         if total_images < 7:
#             print("\n⚠️  Warning: Some avatar images are missing!")
#             print("Please add the missing images to:")
#             print("  gui_v2/src/assets/avatars/")
#             print("Then run this script again.")
#     else:
#         print("\n❌ Initialization failed")
#         print("Check the logs for details.")
