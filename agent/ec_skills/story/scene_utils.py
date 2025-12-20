from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from urllib.parse import quote


def update_scene(
    agent_id: str,
    scenes: list[dict],
    play_label: str | None = None,
    play_clip: str | None = None,
) -> bool:
    """
    Send an update_screens IPC request to the frontend to update available scenes
    for an agent and optionally start playback of a desired scene.

    Args:
        agent_id: The target agent id in the GUI.
        scenes: A list of scene dicts, each with keys compatible with the GUI schema (duration omitted; frontend should use natural media length):
            {
              'clip': str,           # media url/path
              'n_repeat': int,       # number of repeats
              'captions': list[str], # optional captions
              'label': str,          # unique label
              'trigger_events': list[str], # optional triggers
              'priority': int        # 1..5 (maps to ScenePriority enum)
            }
        play_label: Optional label of a scene to start playing immediately.
        play_clip: Optional clip url to select a scene when label isn't provided.

    Returns:
        True if the request was emitted without raising; False otherwise.
    """
    try:
        # Lazy import to avoid circular deps at module import time
        from gui.ipc.api import IPCAPI

        if not isinstance(scenes, list) or not scenes:
            logger.warning("[scene_utils.update_scene] 'scenes' must be a non-empty list")
            return False

        # Minimal validation and normalization of scene entries (no duration; let frontend use natural media length)
        norm_scenes: list[dict] = []
        for s in scenes:
            if not isinstance(s, dict):
                continue
            clip = s.get('clip')
            label = s.get('label')
            if not clip or not label:
                continue
            norm_scenes.append({
                'clip': clip,
                'n_repeat': int(s.get('n_repeat', 1)),
                'captions': s.get('captions') or [],
                'label': label,
                'trigger_events': s.get('trigger_events') or [],
                'priority': int(s.get('priority', 3)),  # default NORMAL
            })

        if not norm_scenes:
            logger.warning("[scene_utils.update_scene] No valid scenes to send after normalization")
            return False

        payload = {
            'agents': {
                agent_id: {
                    'scenes': norm_scenes
                }
            }
        }

        # Provide a desired scene to auto-play on the frontend if specified
        if play_label or play_clip:
            payload['agents'][agent_id]['play'] = {}
            if play_label:
                payload['agents'][agent_id]['play']['label'] = play_label
            if play_clip:
                payload['agents'][agent_id]['play']['clip'] = play_clip

        ipc = IPCAPI.get_instance()
        ipc.update_screens(payload)
        logger.info(
            f"[scene_utils.update_scene] Sent update_screens for agent='{agent_id}', "
            f"scenes={len(norm_scenes)}, play_label='{play_label}'"
        )
        return True
    except Exception as e:
        try:
            logger.error(f"[scene_utils.update_scene] Failed to send update_screens: {e}\n{get_traceback()}")
        except Exception:
            pass
        return False




def quick_celebrate():
    """Handler for Help > Test: simple test dialog"""
    try:
        # Lazy imports to avoid heavy deps
        from PySide6.QtWidgets import QInputDialog
        from agent.ec_skills.story.scene_utils import update_scene

        # Ask for agent id (prefilled)
        # agent_id, ok = QInputDialog.getText(self.main_window, "Update Scene Test", "Agent ID:", text="a1")
        # if not ok or not agent_id.strip():
        #     return
        # agent_id = agent_id.strip()
        agent_id = "6d5ea546c995bbdf679ca88dbe83371c"

        # Demo scenes (use natural media length; no duration field)
        # Use public asset path served by gui_v2
        abs_path = r"C:\Users\songc\PycharmProjects\eCan.ai\resource\avatars\system\agent3_celebrate0.webm"
        clip_url = f"http://localhost:4668/api/avatar?path={quote(abs_path)}"

        demo_scenes = [
            {
                "label": "celebrate",
                "clip": clip_url,
                "n_repeat": 1,
                "priority": 5,
                "captions": ["Local celebrate clip"]
            }
        ]
        logger.debug("update_scene..............")
        sent = update_scene(agent_id=agent_id, scenes=demo_scenes, play_label="celebrate")
        if sent:
            logger.debug(f"update_scene sent for agent '{agent_id}'.")
        else:
            logger.debug(f"Failed to send update_scene for agent '{agent_id}'. See logs.")

    except Exception as e:
        logger.error(f"ErrorQuickTest: {e}")
