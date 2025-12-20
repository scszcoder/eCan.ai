# Avatar Video Utils - Video processing utilities for avatars

import os
import subprocess
import asyncio
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
import io

from utils.logger_helper import logger_helper as logger


async def extract_first_frame(video_path: str, output_path: str = None) -> Optional[str]:
    """
    Extract the first frame from a video file as an image.
    
    NOTE: This is an optional feature. If ffmpeg is not available, returns None.
    The application should gracefully handle None and use videoUrl directly.
    
    Args:
        video_path: Path to video file (mp4, webm, etc.)
        output_path: Optional output path for the extracted image.
                    If None, will use same directory and name as video with _frame.png suffix.
    
    Returns:
        Path to extracted image file, or None if ffmpeg not available or extraction failed
    """
    try:
        video_path = Path(video_path)
        
        if not video_path.exists():
            logger.warning(f"[VideoUtils] Video file not found: {video_path}")
            return None
        
        # Determine output path
        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}_frame.png"
        else:
            output_path = Path(output_path)
        
        # Check if ffmpeg is available (optional dependency)
        try:
            try:
                from utils.subprocess_helper import get_subprocess_kwargs
                _kwargs = get_subprocess_kwargs({'capture_output': True, 'check': True})
            except Exception:
                _kwargs = {'capture_output': True, 'check': True}
            subprocess.run(['ffmpeg', '-version'], **_kwargs)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.info("[VideoUtils] ffmpeg not available, skipping frame extraction (this is optional)")
            return None
        
        # Extract first frame using ffmpeg
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-vframes', '1',  # Extract only 1 frame
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2',  # Scale to 512x512
            '-y',  # Overwrite output file
            str(output_path)
        ]
        
        logger.info(f"[VideoUtils] Extracting first frame from: {video_path}")
        
        # Run ffmpeg command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and output_path.exists():
            logger.info(f"[VideoUtils] ✅ First frame extracted: {output_path}")
            return str(output_path)
        else:
            logger.error(f"[VideoUtils] ❌ Failed to extract frame: {stderr.decode()}")
            return None
    
    except Exception as e:
        logger.error(f"[VideoUtils] Error extracting first frame: {e}", exc_info=True)
        return None


def validate_video(file_data: bytes, filename: str, max_size: int = 50 * 1024 * 1024) -> dict:
    """
    Validate video file.
    
    Args:
        file_data: Video file bytes
        filename: Original filename
        max_size: Maximum file size in bytes (default: 50MB)
    
    Returns:
        {
            "success": bool,
            "error": str (if failed),
            "format": str (if successful),
            "size": int (if successful)
        }
    """
    try:
        # Check file size
        file_size = len(file_data)
        if file_size > max_size:
            return {
                "success": False,
                "error": f"Video file too large: {file_size / 1024 / 1024:.1f}MB (max: {max_size / 1024 / 1024}MB)"
            }
        
        if file_size == 0:
            return {
                "success": False,
                "error": "Video file is empty"
            }
        
        # Check format by extension
        ext = Path(filename).suffix.lower().lstrip('.')
        supported_formats = ['mp4', 'webm', 'mov', 'avi']
        
        if ext not in supported_formats:
            return {
                "success": False,
                "error": f"Unsupported video format: {ext}. Supported formats: {', '.join(supported_formats)}"
            }
        
        # Additional validation: check video file signature (magic bytes)
        # WebM: 0x1A45DFA3
        # MP4: 'ftyp' at bytes 4-8
        if len(file_data) < 12:
            return {
                "success": False,
                "error": "Video file is too small or corrupted"
            }
        
        # Check WebM signature
        if ext == 'webm':
            if file_data[0:4] != b'\x1a\x45\xdf\xa3':
                logger.warning("[VideoUtils] WebM file signature mismatch, but proceeding")
        
        # Check MP4 signature
        elif ext == 'mp4':
            if b'ftyp' not in file_data[4:12]:
                logger.warning("[VideoUtils] MP4 file signature mismatch, but proceeding")
        
        return {
            "success": True,
            "format": ext,
            "size": file_size
        }
    
    except Exception as e:
        logger.error(f"[VideoUtils] Video validation error: {e}")
        return {
            "success": False,
            "error": f"Video validation failed: {str(e)}"
        }


def get_video_info(file_path: str) -> Optional[dict]:
    """
    Get video information using ffprobe.
    
    Args:
        file_path: Path to video file
    
    Returns:
        Dictionary with video info:
        {
            "duration": float,  # in seconds
            "width": int,
            "height": int,
            "codec": str,
            "fps": float
        }
        Or None if failed
    """
    try:
        # Check if ffprobe is available
        try:
            subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("[VideoUtils] ffprobe not found, cannot get video info")
            return None
        
        # Get video info using ffprobe
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,codec_name,r_frame_rate,duration',
            '-of', 'json',
            str(file_path)
        ]
        
        try:
            from utils.subprocess_helper import get_subprocess_kwargs
            _kwargs = get_subprocess_kwargs({'capture_output': True, 'text': True, 'check': True})
        except Exception:
            _kwargs = {'capture_output': True, 'text': True, 'check': True}
        result = subprocess.run(cmd, **_kwargs)
        
        import json
        data = json.loads(result.stdout)
        
        if 'streams' in data and len(data['streams']) > 0:
            stream = data['streams'][0]
            
            # Parse frame rate
            fps_str = stream.get('r_frame_rate', '0/1')
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 0
            
            return {
                "duration": float(stream.get('duration', 0)),
                "width": int(stream.get('width', 0)),
                "height": int(stream.get('height', 0)),
                "codec": stream.get('codec_name', 'unknown'),
                "fps": fps
            }
        
        return None
    
    except Exception as e:
        logger.error(f"[VideoUtils] Error getting video info: {e}")
        return None

