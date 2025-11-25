"""
LightRAG Configuration Utilities
Shared utilities for managing LightRAG configuration file paths
"""
import os
from pathlib import Path
from typing import Optional
from utils.logger_helper import logger_helper as logger


def get_user_env_path() -> Optional[Path]:
    """
    Get user-specific env file path from MainWindow.my_ecb_data_homepath
    
    Returns:
        Path to user's lightrag.env file, or None if unable to determine
    """
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if main_window and hasattr(main_window, 'my_ecb_data_homepath'):
            user_data_dir = Path(main_window.my_ecb_data_homepath)
            return user_data_dir / "resource" / "data" / "lightrag.env"
        else:
            logger.warning("Failed to get main_window or my_ecb_data_homepath")
            return None
    except Exception as e:
        logger.warning(f"Failed to get user env path: {e}")
        return None


def get_template_env_path() -> Optional[Path]:
    """
    Get template env file path from app home directory
    
    Returns:
        Path to lightrag_template.env file, or None if unable to determine
    """
    try:
        from config.app_info import app_info
        app_home_dir = Path(app_info.apphomepath)
        return app_home_dir / "resource" / "data" / "lightrag_template.env"
    except Exception as e:
        logger.warning(f"Failed to get template env path from app_info: {e}")
        # Fallback to script directory for development
        try:
            script_dir = Path(__file__).parent
            project_root = script_dir.parent
            return project_root / "resource" / "data" / "lightrag_template.env"
        except Exception as fallback_error:
            logger.error(f"Fallback template path also failed: {fallback_error}")
            return None


def ensure_user_env_file() -> Optional[Path]:
    """
    Ensure user env file exists, copy from template if not
    
    Returns:
        Path to user's lightrag.env file, or None if unable to create/access
    """
    user_env_path = get_user_env_path()
    if not user_env_path:
        logger.error("Failed to get user env path")
        return None
    
    # If user env file already exists, return it
    if user_env_path.exists():
        return user_env_path
    
    # Get template path
    template_path = get_template_env_path()
    if not template_path:
        logger.warning("Failed to get template env path")
        return user_env_path  # Return user path anyway, will be created on save
    
    if not template_path.exists():
        logger.warning(f"Template env file not found at: {template_path}")
        return user_env_path  # Return user path anyway, will be created on save
    
    # Copy template to user directory
    try:
        import shutil
        user_env_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_path, user_env_path)
        logger.info(f"Copied template env from {template_path} to {user_env_path}")
        
        # Set default directory paths and provider settings based on user's configuration
        try:
            from app_context import AppContext
            from config.app_info import app_info
            
            main_window = AppContext.get_main_window()
            if main_window and hasattr(main_window, 'my_ecb_data_homepath'):
                lightrag_root = os.path.join(main_window.my_ecb_data_homepath, 'lightrag')
                
                # Read the copied file
                with open(user_env_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 1. Directory paths configuration
                # LOG_DIR uses app_info.appdata_path/runlogs (same as main app logs)
                dir_configs = {
                    'INPUT_DIR': os.path.join(lightrag_root, 'inputs'),
                    'WORKING_DIR': os.path.join(lightrag_root, 'rag_storage'),
                    'TIKTOKEN_CACHE_DIR': os.path.join(lightrag_root, 'tiktoken'),
                    'LOG_DIR': os.path.join(app_info.appdata_path, 'runlogs')
                }
                
                # 2. Get default provider settings from config_manager and managers
                provider_configs = {}
                try:
                    if hasattr(main_window, 'config_manager') and main_window.config_manager:
                        general_settings = main_window.config_manager.general_settings
                        
                        # Get LLM provider settings
                        default_llm_provider = general_settings.default_llm
                        default_llm_model = general_settings.default_llm_model
                        
                        if default_llm_provider:
                            provider_configs['LLM_BINDING'] = default_llm_provider
                            if default_llm_model:
                                provider_configs['LLM_MODEL'] = default_llm_model
                            
                            # Get provider details from llm_manager (should be initialized by now)
                            if hasattr(main_window.config_manager, 'llm_manager') and main_window.config_manager.llm_manager:
                                provider_info = main_window.config_manager.llm_manager.get_provider(default_llm_provider)
                                if provider_info:
                                    base_url = provider_info.get('base_url')
                                    if base_url and base_url.strip():
                                        provider_configs['LLM_BINDING_HOST'] = base_url
                                        logger.info(f"[LightRAG] Set LLM_BINDING_HOST: {base_url}")
                            
                            logger.info(f"[LightRAG] Using default LLM: {default_llm_provider} / {default_llm_model}")
                        
                        # Get Embedding provider settings
                        default_embed_provider = general_settings.default_embedding
                        default_embed_model = general_settings.default_embedding_model
                        if default_embed_provider:
                            provider_configs['EMBEDDING_BINDING'] = default_embed_provider
                            if default_embed_model:
                                provider_configs['EMBEDDING_MODEL'] = default_embed_model
                            
                            # Get provider details from embedding_manager (should be initialized by now)
                            if hasattr(main_window.config_manager, 'embedding_manager') and main_window.config_manager.embedding_manager:
                                embed_info = main_window.config_manager.embedding_manager.get_provider(default_embed_provider)
                                if embed_info:
                                    base_url = embed_info.get('base_url')
                                    if base_url and base_url.strip():
                                        provider_configs['EMBEDDING_BINDING_HOST'] = base_url
                                        logger.info(f"[LightRAG] Set EMBEDDING_BINDING_HOST: {base_url}")
                                    
                                    # Get model-specific dimensions
                                    if default_embed_model and embed_info.get('supported_models'):
                                        for model in embed_info['supported_models']:
                                            if model.get('name') == default_embed_model or model.get('model_id') == default_embed_model:
                                                dimensions = model.get('dimensions')
                                                if dimensions:
                                                    provider_configs['EMBEDDING_DIM'] = str(dimensions)
                                                    logger.info(f"[LightRAG] Set EMBEDDING_DIM: {dimensions}")
                                                break
                            
                            logger.info(f"[LightRAG] Using default Embedding: {default_embed_provider} / {default_embed_model}")
                except Exception as provider_error:
                    logger.warning(f"Failed to get default providers: {provider_error}")
                
                # Merge all configs
                all_configs = {**dir_configs, **provider_configs}
                
                # First pass: identify uncommented config lines
                uncommented_keys = set()
                for line in lines:
                    line_stripped = line.strip()
                    if '=' in line_stripped and not line_stripped.startswith('#'):
                        key = line_stripped.split('=')[0].strip()
                        if key in all_configs:
                            uncommented_keys.add(key)
                
                # Second pass: replace lines
                updated_lines = []
                keys_found = set()
                
                for line in lines:
                    line_stripped = line.strip()
                    replaced = False
                    
                    # Process lines with '='
                    if '=' in line_stripped:
                        is_commented = line_stripped.startswith('#')
                        
                        # Extract key
                        if is_commented:
                            clean_line = line_stripped.lstrip('#').lstrip()
                        else:
                            clean_line = line_stripped
                        
                        if '=' in clean_line:
                            key = clean_line.split('=')[0].strip()
                            
                            # Replace if:
                            # 1. Key is in our configs
                            # 2. We haven't replaced it yet
                            # 3. Either: it's uncommented, OR it's commented but no uncommented version exists
                            if key in all_configs and key not in keys_found:
                                should_replace = (not is_commented) or (key not in uncommented_keys)
                                if should_replace:
                                    updated_lines.append(f"{key}={all_configs[key]}\n")
                                    keys_found.add(key)
                                    replaced = True
                    
                    if not replaced:
                        updated_lines.append(line)
                
                # Add missing keys at the end
                for key, value in all_configs.items():
                    if key not in keys_found:
                        updated_lines.append(f"\n{key}={value}\n")
                
                # Write back
                with open(user_env_path, 'w', encoding='utf-8') as f:
                    f.writelines(updated_lines)
                
                logger.info(f"Set default configurations in {user_env_path}:")
                logger.info(f"  - Directories: {dir_configs}")
                if provider_configs:
                    logger.info(f"  - Providers: {provider_configs}")
        except Exception as dir_error:
            logger.warning(f"Failed to set default directories: {dir_error}")
        
        return user_env_path
    except Exception as e:
        logger.error(f"Failed to copy template env file: {e}")
        return user_env_path  # Return user path anyway, will be created on save
