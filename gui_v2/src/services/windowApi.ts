/**
 * Window API
 * 提供窗口控制相关的 API 方法
 */

import { IPCWCClient } from './ipc/ipcWCClient';

/**
 * Toggle window fullscreen state
 * @returns Promise with the new fullscreen state
 */
export async function toggleFullscreen(): Promise<boolean> {
    const response = await IPCWCClient.getInstance().invoke('window_toggle_fullscreen', {});
    console.log('[windowApi] toggleFullscreen response:', response);
    console.log('[windowApi] toggleFullscreen result:', response?.result);
    console.log('[windowApi] toggleFullscreen data:', response?.data);
    
    // Try both result and data fields
    const isFullscreen = response?.result?.is_fullscreen ?? response?.data?.is_fullscreen ?? false;
    console.log('[windowApi] toggleFullscreen final state:', isFullscreen);
    return isFullscreen;
}

/**
 * Get current window fullscreen state
 * @returns Promise with the current fullscreen state
 */
export async function getFullscreenState(): Promise<boolean> {
    const response = await IPCWCClient.getInstance().invoke('window_get_fullscreen_state', {});
    console.log('[windowApi] getFullscreenState response:', response);
    console.log('[windowApi] getFullscreenState result:', response?.result);
    
    // Try both result and data fields
    return response?.result?.is_fullscreen ?? response?.data?.is_fullscreen ?? false;
}
