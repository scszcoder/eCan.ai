import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Maximize, Minimize } from 'lucide-react';
import { Button, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';

/**
 * Component that toggles full screen mode for the graph.
 * Uses IPC to control the native window fullscreen state + CSS to hide other UI elements.
 */
const FullScreenControl: React.FC = () => {
  const { t } = useTranslation();
  const [isFullScreen, setIsFullScreen] = useState(false);
  const isTogglingRef = useRef(false);

  // Helper to trigger Sigma resize
  const triggerResize = () => {
    setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
      // Force redraw/reflow
      document.body.offsetHeight; 
    }, 100);
  };

  // 初始化时获取全屏状态并清理可能残留的class
  useEffect(() => {
    const initFullscreenState = async () => {
      try {
        let state = await get_ipc_api().windowGetFullscreenState();
        
        // 检查实际窗口是否全屏（通过窗口尺寸判断）
        // Allow small tolerance for pixel differences
        const isActuallyFullscreen = Math.abs(window.innerWidth - window.screen.width) < 5 && 
                                     Math.abs(window.innerHeight - window.screen.height) < 5;
        
        // 如果后端状态与实际不符，使用实际状态
        if (state !== isActuallyFullscreen) {
          state = isActuallyFullscreen;
        }
        
        setIsFullScreen(state);
        
        // 如果不是全屏状态，确保清理残留的class
        if (!state) {
          document.body.classList.remove('graph-fullscreen-active');
          const graphContainer = document.querySelector('.graph-viewer-container');
          if (graphContainer) {
            graphContainer.classList.remove('graph-fullscreen-mode');
          }
        }
      } catch (error) {
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
        try {
          isTogglingRef.current = true;
          // 调用后端退出全屏
          const newState = await get_ipc_api().windowToggleFullscreen();
          setIsFullScreen(newState);
          setTimeout(() => { isTogglingRef.current = false; }, 1000);
        } catch (error) {
          isTogglingRef.current = false;
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
      if (isTogglingRef.current) return;

      // 检查实际窗口是否全屏
      const isActuallyFullscreen = Math.abs(window.innerWidth - window.screen.width) < 5 && 
                                   Math.abs(window.innerHeight - window.screen.height) < 5;
      
      // 如果状态不一致，更新状态
      if (isActuallyFullscreen !== isFullScreen) {
        setIsFullScreen(isActuallyFullscreen);
        triggerResize();
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
      return;
    }

    if (isFullScreen) {
      // 进入全屏：添加全屏class
      graphContainer.classList.add('graph-fullscreen-mode');
      document.body.classList.add('graph-fullscreen-active');
      
      // 强制Sigma重新渲染
      triggerResize();
    } else {
      // 退出全屏：移除全屏class
      graphContainer.classList.remove('graph-fullscreen-mode');
      document.body.classList.remove('graph-fullscreen-active');
      triggerResize();
    }
  }, [isFullScreen]);

  const toggle = useCallback(async () => {
    if (isTogglingRef.current) return;
    
    try {
      isTogglingRef.current = true;
      const newState = await get_ipc_api().windowToggleFullscreen();
      setIsFullScreen(newState);
      
      // Reset toggling flag after animation duration
      setTimeout(() => {
        isTogglingRef.current = false;
      }, 1000);
    } catch (error) {
      isTogglingRef.current = false;
    }
  }, [isFullScreen]);

  return (
    <Tooltip 
      title={isFullScreen ? t('graphPanel.sideBar.fullScreenControl.windowed', 'Exit Fullscreen') : t('graphPanel.sideBar.fullScreenControl.fullScreen', 'Fullscreen')}
      placement="right"
    >
      <Button
        type="text"
        icon={isFullScreen ? <Minimize size={18} style={{ color: '#ffffff' }} /> : <Maximize size={18} style={{ color: '#ffffff' }} />}
        onClick={toggle}
        style={{ width: 36, height: 36, color: '#ffffff' }}
      />
    </Tooltip>
  );
};

export default FullScreenControl;
