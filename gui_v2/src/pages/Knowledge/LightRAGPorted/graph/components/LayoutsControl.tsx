import React, { useCallback, useState, useMemo, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSigma } from '@react-sigma/core';
import { animateNodes } from 'sigma/utils';
import { useLayoutCircular } from '@react-sigma/layout-circular';
import { useLayoutCirclepack } from '@react-sigma/layout-circlepack';
import { useLayoutRandom } from '@react-sigma/layout-random';
import { useLayoutNoverlap } from '@react-sigma/layout-noverlap';
import { useLayoutForce } from '@react-sigma/layout-force';
import { useLayoutForceAtlas2 } from '@react-sigma/layout-forceatlas2';
import { Button, Popover, Tooltip } from 'antd';
import { Grip, Play, Pause } from 'lucide-react';
import { useSettingsStore } from '../stores/settings';

type LayoutName = 'circular' | 'circlepack' | 'random' | 'noverlap' | 'force' | 'fa2';

const LayoutsControl: React.FC = () => {
  const { t } = useTranslation();
  const sigma = useSigma();
  const [open, setOpen] = useState(false);
  const [currentLayout, setCurrentLayout] = useState<LayoutName | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);
  const animationTimerRef = useRef<number | null>(null);

  const maxIterations = useSettingsStore((s) => s.graphLayoutMaxIterations);

  const circular = useLayoutCircular();
  const circlepack = useLayoutCirclepack();
  const random = useLayoutRandom();
  const noverlap = useLayoutNoverlap({
    maxIterations,
    settings: {
      margin: 5,
      expansion: 1.1,
      gridSize: 1,
      ratio: 1,
      speed: 3,
    }
  });
  const force = useLayoutForce({
    maxIterations,
    settings: {
      attraction: 0.0003,
      repulsion: 0.02,
      gravity: 0.02,
      inertia: 0.4,
      maxMove: 100
    }
  });
  const fa2 = useLayoutForceAtlas2({ iterations: maxIterations });

  const layouts = useMemo(() => ({
    circular: { layout: circular, hasAnimation: false },
    circlepack: { layout: circlepack, hasAnimation: false },
    random: { layout: random, hasAnimation: false },
    noverlap: { layout: noverlap, hasAnimation: true },
    force: { layout: force, hasAnimation: true },
    fa2: { layout: fa2, hasAnimation: true }
  }), [circular, circlepack, random, noverlap, force, fa2]);

  const updatePositions = useCallback((layoutName: LayoutName) => {
    const graph = sigma?.getGraph();
    if (!graph || graph.order === 0) return;
    
    try {
      const positions = layouts[layoutName].layout.positions();
      animateNodes(graph as any, positions as any, { duration: 300 });
    } catch (error) {
      console.error('Error updating positions:', error);
      if (animationTimerRef.current) {
        window.clearInterval(animationTimerRef.current);
        animationTimerRef.current = null;
        setIsAnimating(false);
      }
    }
  }, [sigma, layouts]);

  const stopAnimation = useCallback(() => {
    if (animationTimerRef.current) {
      window.clearInterval(animationTimerRef.current);
      animationTimerRef.current = null;
    }
    setIsAnimating(false);
  }, []);

  const startAnimation = useCallback((layoutName: LayoutName) => {
    stopAnimation();
    
    updatePositions(layoutName);
    
    animationTimerRef.current = window.setInterval(() => {
      updatePositions(layoutName);
    }, 200);
    
    setIsAnimating(true);
    
    // Auto-stop after 3 seconds
    setTimeout(() => {
      stopAnimation();
    }, 3000);
  }, [updatePositions, stopAnimation]);

  const run = useCallback((which: LayoutName) => {
    const graph = sigma?.getGraph();
    if (!graph || graph.order === 0) return;
    
    setCurrentLayout(which);
    
    if (layouts[which].hasAnimation) {
      startAnimation(which);
    } else {
      const pos = layouts[which].layout.positions();
      animateNodes(graph as any, pos as any, { duration: 400 });
    }
    
    setOpen(false);
  }, [sigma, layouts, startAnimation]);

  const toggleAnimation = useCallback(() => {
    if (!currentLayout || !layouts[currentLayout].hasAnimation) return;
    
    if (isAnimating) {
      stopAnimation();
    } else {
      startAnimation(currentLayout);
    }
  }, [currentLayout, isAnimating, layouts, stopAnimation, startAnimation]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (animationTimerRef.current) {
        window.clearInterval(animationTimerRef.current);
        animationTimerRef.current = null;
      }
    };
  }, []);

  const content = (
    <div style={{ padding: 4, minWidth: 150, background: 'rgba(45, 55, 72, 0.95)', borderRadius: 8 }}>
      <div onClick={() => run('circular')} style={{ padding: '6px 12px', cursor: 'pointer', borderRadius: 4, fontSize: 12, color: '#ffffff' }} onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
        {t('graphPanel.sideBar.layoutsControl.layouts.Circular', '环形')}
      </div>
      <div onClick={() => run('circlepack')} style={{ padding: '6px 12px', cursor: 'pointer', borderRadius: 4, fontSize: 12, color: '#ffffff' }} onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
        {t('graphPanel.sideBar.layoutsControl.layouts.Circlepack', '圆形打包')}
      </div>
      <div onClick={() => run('random')} style={{ padding: '6px 12px', cursor: 'pointer', borderRadius: 4, fontSize: 12, color: '#ffffff' }} onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
        {t('graphPanel.sideBar.layoutsControl.layouts.Random', '随机')}
      </div>
      <div onClick={() => run('noverlap')} style={{ padding: '6px 12px', cursor: 'pointer', borderRadius: 4, fontSize: 12, color: '#ffffff' }} onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
        {t('graphPanel.sideBar.layoutsControl.layouts.Noverlaps', '无重叠')}
      </div>
      <div onClick={() => run('force')} style={{ padding: '6px 12px', cursor: 'pointer', borderRadius: 4, fontSize: 12, color: '#ffffff' }} onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
        {t('graphPanel.sideBar.layoutsControl.layouts.Force Directed', '力导向')}
      </div>
      <div onClick={() => run('fa2')} style={{ padding: '6px 12px', cursor: 'pointer', borderRadius: 4, fontSize: 12, color: '#ffffff' }} onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
        {t('graphPanel.sideBar.layoutsControl.layouts.Force Atlas', '力地图')}
      </div>
    </div>
  );

  const showAnimationButton = currentLayout && layouts[currentLayout]?.hasAnimation;

  return (
    <>
      {showAnimationButton && (
        <Tooltip title={isAnimating ? t('graphPanel.sideBar.layoutsControl.stopAnimation', '停止动画') : t('graphPanel.sideBar.layoutsControl.startAnimation', '开始动画')}>
          <Button
            type="text"
            icon={isAnimating ? <Pause size={18} style={{ color: '#ffffff' }} /> : <Play size={18} style={{ color: '#ffffff' }} />}
            onClick={toggleAnimation}
            style={{ width: 36, height: 36, color: '#ffffff' }}
          />
        </Tooltip>
      )}
      <Popover content={content} trigger="click" open={open} onOpenChange={setOpen} placement="rightTop">
        <Tooltip title={t('graphPanel.sideBar.layoutsControl.layoutGraph', '布局图谱')}>
          <Button
            type="text"
            icon={<Grip size={18} style={{ color: '#ffffff' }} />}
            style={{ width: 36, height: 36, color: '#ffffff' }}
          />
        </Tooltip>
      </Popover>
    </>
  );
};

export default LayoutsControl;
