"""
Avatar Video Generator - Generate videos from avatar images.

This module provides functionality to generate animated videos from static avatar images
using LLM APIs or fallback to ffmpeg-based placeholder videos.
"""

import os
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from utils.logger_helper import logger_helper as logger

# ==================== Video Generation Settings ====================
# Control avatar video generation behavior

# Enable/disable automatic video generation when uploading images
# False = Skip video generation (recommended, fast performance)
# True = Generate video from uploaded images (requires ffmpeg)
ENABLE_AVATAR_VIDEO_GENERATION = False


class AvatarVideoGenerator:
    """Generate avatar videos from images using LLM APIs"""
    
    def __init__(self, llm=None):
        """
        Initialize video generator
        
        Args:
            llm: LLM instance from MainWindow (created by pick_llm)
        """
        self.llm = llm
        
    async def generate_video_from_avatar(
        self,
        image_path: str,
        org_name: str = None,
        output_dir: str = None,
        duration: float = 5.0
    ) -> Dict:
        """
        Generate a 5-second video from avatar image
        
        Args:
            image_path: Path to the avatar image
            org_name: Organization name for context (e.g., "Finance", "R&D")
            output_dir: Output directory for generated video
            duration: Video duration in seconds (default: 5.0)
            
        Returns:
            Dict with success status and file paths:
            {
                "success": True,
                "mp4_path": "/path/to/video.mp4",
                "webm_path": "/path/to/video.webm",
                "duration": 5.0,
                "prompt": "Generated prompt"
            }
        """
        try:
            logger.info(f"[VideoGenerator] Starting video generation for: {image_path}")
            
            # Validate image path
            if not os.path.exists(image_path):
                return {
                    "success": False,
                    "error": f"Image file not found: {image_path}"
                }
            
            # Generate video prompt based on organization
            prompt = self._build_video_prompt(org_name)
            logger.info(f"[VideoGenerator] Generated prompt: {prompt}")
            
            # Call LLM API to generate video
            mp4_path = await self._generate_video_with_llm(
                image_path=image_path,
                prompt=prompt,
                output_dir=output_dir,
                duration=duration
            )
            
            if not mp4_path:
                return {
                    "success": False,
                    "error": "Failed to generate MP4 video"
                }
            
            # Convert MP4 to WebM format
            webm_path = await self._convert_to_webm(mp4_path)
            
            if not webm_path:
                logger.warning("[VideoGenerator] Failed to convert to WebM, but MP4 is available")
            
            logger.info(f"[VideoGenerator] ✅ Video generation completed: {mp4_path}")
            
            return {
                "success": True,
                "mp4_path": mp4_path,
                "webm_path": webm_path,
                "duration": duration,
                "prompt": prompt
            }
            
        except Exception as e:
            logger.error(f"[VideoGenerator] ❌ Video generation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_video_prompt(self, org_name: str = None) -> str:
        """
        Build video generation prompt based on organization context
        
        Reference system avatar video style in resource/avatars/system:
        - Clean office scene, focus on character
        - Natural micro-movements: slight nod, blink, smile
        - Soft lighting and professional atmosphere
        - Blurred background, highlight character
        
        Args:
            org_name: Organization name (e.g., "Finance", "R&D", "Customer Service")
            
        Returns:
            Video generation prompt string
        """
        # Base prompt - reference system avatar video style
        base_prompt = (
            "Create a 5-second professional avatar video in the style of system avatars. "
            "Style: Clean, professional portrait with soft lighting and subtle animations. "
            "The character should be centered in frame with a blurred office background. "
        )
        
        # Default office worker description
        default_description = "Professional office worker focused on daily tasks"
        
        # Add organization-specific work context (simplified, closer to system video style)
        if org_name:
            org_contexts = {
                "Finance": "Finance professional reviewing financial data on screen",
                "Accounting": "Accountant working with accounting software",
                "Customer Service": "Customer service representative in a friendly, helpful pose",
                "Sales": "Sales professional with confident, engaging demeanor",
                "Marketing": "Marketing specialist reviewing campaign materials",
                "R&D": "Developer focused on coding and technical work",
                "Development": "Developer focused on coding and technical work",
                "Legal": "Legal professional reviewing documents",
                "HR": "HR specialist managing employee information",
                "Human Resources": "HR specialist managing employee information",
                "Admin": "Administrative staff organizing office tasks",
                "IT": "IT specialist monitoring systems",
                # Chinese organization names
                "财务": "Finance professional reviewing financial data on screen",
                "会计": "Accountant working with accounting software",
                "客服": "Customer service representative in a friendly, helpful pose",
                "销售": "Sales professional with confident, engaging demeanor",
                "市场": "Marketing specialist reviewing campaign materials",
                "研发": "Developer focused on coding and technical work",
                "法务": "Legal professional reviewing documents",
                "人力": "HR specialist managing employee information",
                "行政": "Administrative staff organizing office tasks",
            }
            
            # Find matching context
            work_context = None
            for key, context in org_contexts.items():
                if key in org_name:
                    work_context = context
                    break
            
            if work_context:
                base_prompt += f"Character: {work_context}. "
            else:
                # Use default office worker description for unmatched organizations
                base_prompt += f"Character: {default_description}. "
            
            # Add organization context
            base_prompt += f"Role: {org_name} team member. "
        else:
            # No organization specified, use default description
            base_prompt += f"Character: {default_description} in a neutral, friendly pose. "
        
        # Add animation requirements - reference system video micro-movement style
        base_prompt += (
            "Animation: Subtle, natural micro-movements only - "
            "gentle head tilt, slight smile, soft eye blink, minimal hand gesture. "
            "Keep movements minimal and professional, similar to a professional headshot video. "
            "Lighting: Soft, even lighting with slight rim light. "
            "Background: Blurred modern office environment. "
            "Camera: Static, medium close-up shot. "
            "Mood: Professional, approachable, confident. "
            "Quality: High-definition, smooth 30fps animation."
        )
        
        return base_prompt
    
    async def _generate_video_with_llm(
        self,
        image_path: str,
        prompt: str,
        output_dir: str = None,
        duration: float = 5.0
    ) -> Optional[str]:
        """
        Call LLM API to generate video from image
        
        Args:
            image_path: Source image path
            prompt: Video generation prompt
            output_dir: Output directory
            duration: Video duration
            
        Returns:
            Path to generated MP4 file, or None if failed
        """
        try:
            # Always use ffmpeg placeholder for now
            # LLM video generation requires API integration (future feature)
            logger.info("[VideoGenerator] Generating video using ffmpeg placeholder")
            
            # Determine output path for placeholder
            if not output_dir:
                output_dir = Path(image_path).parent
            else:
                output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            image_name = Path(image_path).stem
            output_path = output_dir / f"{image_name}_video.mp4"
            
            # Generate placeholder video directly
            result = await self._generate_placeholder_video(image_path, output_path, duration)
            return str(output_path) if result else None
                
        except Exception as e:
            logger.error(f"[VideoGenerator] ❌ Error in video generation: {e}", exc_info=True)
            return None
    
    async def _generate_placeholder_video(
        self,
        image_path: str,
        output_path: str,
        duration: float
    ) -> bool:
        """
        Generate a placeholder video using ffmpeg (image loop with zoom effect)
        
        This creates a simple animated video from the static image as a fallback.
        """
        try:
            logger.info("[VideoGenerator] Generating placeholder video with ffmpeg...")
            
            # Check if ffmpeg is available
            try:
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.error("[VideoGenerator] ffmpeg not found, cannot generate placeholder video")
                return False
            
            # Create a simple zoom animation using ffmpeg
            # This creates a 5-second video with a slow zoom effect
            cmd = [
                'ffmpeg',
                '-loop', '1',
                '-i', image_path,
                '-vf', f'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,zoompan=z=\'min(zoom+0.0015,1.5)\':d={int(duration*30)}:s=1920x1080',
                '-c:v', 'libx264',
                '-t', str(duration),
                '-pix_fmt', 'yuv420p',
                '-y',  # Overwrite output file
                str(output_path)
            ]
            
            # Run ffmpeg command
            creationflags = None
            startupinfo = None
            try:
                if sys.platform == 'win32':
                    from utils.subprocess_helper import get_subprocess_creation_flags
                    creationflags, startupinfo = get_subprocess_creation_flags()
            except Exception:
                pass

            kwargs = {
                'stdout': asyncio.subprocess.PIPE,
                'stderr': asyncio.subprocess.PIPE,
            }
            if creationflags is not None:
                kwargs['creationflags'] = creationflags
            if startupinfo is not None:
                kwargs['startupinfo'] = startupinfo

            process = await asyncio.create_subprocess_exec(
                *cmd,
                **kwargs
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("[VideoGenerator] ✅ Placeholder video generated successfully")
                return True
            else:
                logger.error(f"[VideoGenerator] ❌ ffmpeg failed: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"[VideoGenerator] ❌ Error generating placeholder video: {e}")
            return False
    
    async def _convert_to_webm(self, mp4_path: str) -> Optional[str]:
        """
        Convert MP4 video to WebM format
        
        Args:
            mp4_path: Path to source MP4 file
            
        Returns:
            Path to converted WebM file, or None if failed
        """
        try:
            webm_path = Path(mp4_path).with_suffix('.webm')
            
            logger.info(f"[VideoGenerator] Converting to WebM: {webm_path}")
            
            # Check if ffmpeg is available
            try:
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.error("[VideoGenerator] ffmpeg not found, cannot convert to WebM")
                return None
            
            # Convert to WebM using ffmpeg
            cmd = [
                'ffmpeg',
                '-i', str(mp4_path),
                '-c:v', 'libvpx-vp9',
                '-crf', '30',
                '-b:v', '0',
                '-y',  # Overwrite output file
                str(webm_path)
            ]
            
            # Run ffmpeg command
            creationflags = None
            startupinfo = None
            try:
                if sys.platform == 'win32':
                    from utils.subprocess_helper import get_subprocess_creation_flags
                    creationflags, startupinfo = get_subprocess_creation_flags()
            except Exception:
                pass

            _kwargs = {
                'stdout': asyncio.subprocess.PIPE,
                'stderr': asyncio.subprocess.PIPE,
            }
            if creationflags is not None:
                _kwargs['creationflags'] = creationflags
            if startupinfo is not None:
                _kwargs['startupinfo'] = startupinfo

            process = await asyncio.create_subprocess_exec(
                *cmd,
                **_kwargs
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(webm_path):
                logger.info(f"[VideoGenerator] ✅ WebM conversion successful: {webm_path}")
                return str(webm_path)
            else:
                logger.error(f"[VideoGenerator] ❌ WebM conversion failed: {stderr.decode()}")
                return None
                
        except Exception as e:
            logger.error(f"[VideoGenerator] ❌ Error converting to WebM: {e}")
            return None


# Convenience function for easy access
async def generate_avatar_video(
    image_path: str,
    org_name: str = None,
    llm=None,
    output_dir: str = None,
    duration: float = 5.0
) -> Dict:
    """
    Generate avatar video from image
    
    Args:
        image_path: Path to avatar image
        org_name: Organization name for context
        llm: LLM instance (from MainWindow)
        output_dir: Output directory
        duration: Video duration in seconds
        
    Returns:
        Result dictionary with video paths
    """
    generator = AvatarVideoGenerator(llm=llm)
    return await generator.generate_video_from_avatar(
        image_path=image_path,
        org_name=org_name,
        output_dir=output_dir,
        duration=duration
    )
