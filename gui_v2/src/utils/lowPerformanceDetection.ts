/**
 * Low Performance Detection
 *
 * 检测当前设备是否为低性能环境，自动应用"减少动画"模式，
 * 避免在 Modal/Drawer/Dropdown 等弹层打开时出现闪烁。
 *
 * 触发条件（满足任一即视为低性能）：
 *   1. navigator.hardwareConcurrency < 4  （CPU 核心数少于 4）
 *   2. navigator.deviceMemory < 4        （可用内存少于 4GB）
 *   3. effectiveType 为 '2g' 或 'slow-2g' （网络连接慢）
 *   4. prefers-reduced-motion: reduce    （用户系统启用了减少动画）
 *   5. 用户/代码主动调用 enableReducedMotion()
 *
 * 启用"减少动画"的方式：
 *   - 在 html 根元素上添加 .reduce-motion 类（CSS 已准备好对应规则）
 *   - prefers-reduced-motion: reduce 媒体查询也会自动生效
 */

let lowPerformanceDetected = false;
let initialized = false;

/**
 * 检测低性能环境
 */
export function detectLowPerformance(): boolean {
    if (typeof window === 'undefined') return false;
    if (lowPerformanceDetected) return true;

    try {
        // 1. 检查 CPU 核心数
        const cores = navigator.hardwareConcurrency;
        if (typeof cores === 'number' && cores < 4) {
            console.log('[LowPerformance] Low CPU cores detected:', cores);
            return true;
        }

        // 2. 检查内存（Chrome 支持）
        const memory = (navigator as any).deviceMemory;
        if (typeof memory === 'number' && memory < 4) {
            console.log('[LowPerformance] Low device memory detected:', memory, 'GB');
            return true;
        }

        // 3. 检查网络连接类型
        const conn = (navigator as any).connection;
        if (conn && (conn.effectiveType === '2g' || conn.effectiveType === 'slow-2g')) {
            console.log('[LowPerformance] Slow connection detected:', conn.effectiveType);
            return true;
        }

        // 4. 检查 prefers-reduced-motion
        if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            console.log('[LowPerformance] User prefers reduced motion');
            return true;
        }
    } catch (e) {
        console.warn('[LowPerformance] Detection failed:', e);
    }

    return false;
}

/**
 * 应用"减少动画"模式
 */
export function enableReducedMotion(): void {
    if (typeof document === 'undefined') return;
    document.documentElement.classList.add('reduce-motion');
    lowPerformanceDetected = true;
    console.log('[LowPerformance] Reduced motion mode enabled');
}

/**
 * 取消"减少动画"模式（用于手动切换）
 */
export function disableReducedMotion(): void {
    if (typeof document === 'undefined') return;
    document.documentElement.classList.remove('reduce-motion');
    lowPerformanceDetected = false;
    console.log('[LowPerformance] Reduced motion mode disabled');
}

/**
 * 检查当前是否启用了"减少动画"
 */
export function isReducedMotionEnabled(): boolean {
    if (typeof document === 'undefined') return false;
    if (document.documentElement.classList.contains('reduce-motion')) return true;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return true;
    return lowPerformanceDetected;
}

/**
 * 初始化低性能检测（应用启动时调用一次）
 */
export function initLowPerformanceDetection(): void {
    if (typeof window === 'undefined') return;
    if (initialized) return;
    initialized = true;

    // 检查 localStorage 中用户是否手动设置过
    const userSetting = localStorage.getItem('reduceMotion');
    if (userSetting === 'true') {
        enableReducedMotion();
        return;
    }
    if (userSetting === 'false') {
        return; // 用户明确禁用，不自动开启
    }

    // 自动检测低性能环境
    if (detectLowPerformance()) {
        enableReducedMotion();
    }

    // 监听用户系统偏好变化
    if (window.matchMedia) {
        const mql = window.matchMedia('(prefers-reduced-motion: reduce)');
        const handler = (e: MediaQueryListEvent) => {
            if (e.matches) {
                enableReducedMotion();
            } else if (!localStorage.getItem('reduceMotion')) {
                disableReducedMotion();
            }
        };
        // 兼容旧版浏览器
        if (mql.addEventListener) {
            mql.addEventListener('change', handler);
        } else if ((mql as any).addListener) {
            (mql as any).addListener(handler);
        }
    }
}

// Auto-initialize when module is imported
if (typeof window !== 'undefined') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initLowPerformanceDetection();
        });
    } else {
        initLowPerformanceDetection();
    }
}
