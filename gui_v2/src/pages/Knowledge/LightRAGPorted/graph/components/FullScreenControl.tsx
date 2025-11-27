import React, { useState, useEffect, useCallback } from 'react';
import { Maximize, Minimize } from 'lucide-react';
import { Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';

/**
 * Component that toggles full screen mode for the graph.
 * Uses IPC to control the native window fullscreen state + CSS to hide other UI elements.
 */
const FullScreenControl: React.FC = () => {
  const { t } = useTranslation();
  const [isFullScreen, setIsFullScreen] = useState(false);

  // 初始化时获取全屏状态并清理可能残留的class
  useEffect(() => {
    const initFullscreenState = async () => {
      try {
        let state = await get_ipc_api().windowGetFullscreenState();
        console.log('[FullScreenControl] Backend fullscreen state:', state);
        
        // 检查实际窗口是否全屏（通过窗口尺寸判断）
        const isActuallyFullscreen = window.innerWidth === window.screen.width && 
                                     window.innerHeight === window.screen.height;
        console.log('[FullScreenControl] Actual fullscreen check:', isActuallyFullscreen, 
                    `window: ${window.innerWidth}x${window.innerHeight}, screen: ${window.screen.width}x${window.screen.height}`);
        
        // 如果后端状态与实际不符，使用实际状态
        if (state !== isActuallyFullscreen) {
          console.warn('[FullScreenControl] State mismatch! Backend says:', state, 'but actual is:', isActuallyFullscreen);
          state = isActuallyFullscreen;
        }
        
        console.log('[FullScreenControl] Final fullscreen state:', state);
        setIsFullScreen(state);
        
        // 如果不是全屏状态，确保清理残留的class
        if (!state) {
          document.body.classList.remove('graph-fullscreen-active');
          const graphContainer = document.querySelector('.graph-viewer-container');
          if (graphContainer) {
            graphContainer.classList.remove('graph-fullscreen-mode');
          }
          console.log('[FullScreenControl] Cleaned up residual fullscreen classes');
        }
      } catch (error) {
        console.error('[FullScreenControl] Failed to get initial fullscreen state:', error);
        // 出错时默认为非全屏
        setIsFullScreen(false);
      }
    };
    initFullscreenState();
  }, []);

  // 监听ESC键，退出全屏
  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullScreen) {
        console.log('[FullScreenControl] ESC key pressed, exiting fullscreen');
        try {
          // 调用后端退出全屏
          const newState = await get_ipc_api().windowToggleFullscreen();
          setIsFullScreen(newState);
        } catch (error) {
          console.error('[FullScreenControl] Error exiting fullscreen:', error);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isFullScreen]);

  // 监听窗口大小变化，检测手动退出全屏（ESC键）
  useEffect(() => {
    const handleResize = async () => {
      // 检查实际窗口是否全屏
      const isActuallyFullscreen = window.innerWidth === window.screen.width && 
                                   window.innerHeight === window.screen.height;
      
      // 如果状态不一致，更新状态
      if (isActuallyFullscreen !== isFullScreen) {
        console.log('[FullScreenControl] Window resize detected, updating state from', isFullScreen, 'to', isActuallyFullscreen);
        setIsFullScreen(isActuallyFullscreen);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [isFullScreen]);

  // 监听全屏状态变化，添加/移除全屏样式
  useEffect(() => {
    const graphContainer = document.querySelector('.graph-viewer-container');
    if (!graphContainer) {
      console.warn('[FullScreenControl] Graph container not found for styling');
      return;
    }

    if (isFullScreen) {
      // 进入全屏：添加全屏class
      console.log('[FullScreenControl] Adding fullscreen classes');
      graphContainer.classList.add('graph-fullscreen-mode');
      document.body.classList.add('graph-fullscreen-active');
      
      // 验证class是否添加成功
      console.log('[FullScreenControl] Body classes:', document.body.className);
      console.log('[FullScreenControl] Container classes:', graphContainer.className);
      console.log('[FullScreenControl] Graph container display:', window.getComputedStyle(graphContainer).display);
      console.log('[FullScreenControl] Graph container visibility:', window.getComputedStyle(graphContainer).visibility);
      
      // 调试DOM结构
      const lightragPorted = document.querySelector('[data-ec-scope="lightrag-ported"]');
      if (lightragPorted) {
        console.log('[FullScreenControl] lightrag-ported children count:', lightragPorted.children.length);
        Array.from(lightragPorted.children).forEach((child, index) => {
          console.log(`[FullScreenControl] Child ${index + 1}:`, child.tagName, child.className, 
                      'display:', window.getComputedStyle(child as HTMLElement).display);
        });
      }
      
      // 强制触发重绘
      document.body.offsetHeight;
    } else {
      // 退出全屏：移除全屏class
      console.log('[FullScreenControl] Removing fullscreen classes');
      graphContainer.classList.remove('graph-fullscreen-mode');
      document.body.classList.remove('graph-fullscreen-active');
    }
  }, [isFullScreen]);

  const toggle = useCallback(async () => {
    try {
      console.log('[FullScreenControl] Toggle clicked, current state:', isFullScreen);
      const newState = await get_ipc_api().windowToggleFullscreen();
      console.log('[FullScreenControl] New fullscreen state:', newState);
      setIsFullScreen(newState);
    } catch (error) {
      console.error('[FullScreenControl] Error toggling fullscreen:', error);
    }
  }, [isFullScreen]);

  return (
    <Tooltip title={isFullScreen ? t('graphPanel.control.exitFullScreen', 'Exit Fullscreen') : t('graphPanel.control.fullScreen', 'Fullscreen')}>
      <button
        onClick={toggle}
        style={{
          background: 'rgba(45, 55, 72, 0.95)',
          border: '2px solid rgba(255, 255, 255, 0.2)',
          borderRadius: 8,
          cursor: 'pointer',
          padding: 8,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
          backdropFilter: 'blur(12px)',
          transition: 'all 0.2s'
        }}
      >
        {isFullScreen ? <Minimize size={16} /> : <Maximize size={16} />}
      </button>
    </Tooltip>
  );
};

export default FullScreenControl;
