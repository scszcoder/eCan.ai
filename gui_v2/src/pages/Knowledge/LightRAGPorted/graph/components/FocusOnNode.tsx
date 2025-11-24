import { useCamera, useSigma } from '@react-sigma/core';
import { useEffect } from 'react';
import { useGraphStore } from '../stores/graph';

/**
 * 组件用于高亮节点并将相机聚焦到节点
 */
const FocusOnNode: React.FC<{ node: string | null; move?: boolean }> = ({ node, move }) => {
  const sigma = useSigma();
  const { gotoNode } = useCamera();

  /**
   * 当选中的节点变化时，高亮节点并将相机聚焦到它
   */
  useEffect(() => {
    const graph = sigma.getGraph();

    if (move) {
      if (node && graph.hasNode(node)) {
        try {
          graph.setNodeAttribute(node, 'highlighted', true);
          gotoNode(node);
        } catch (error) {
          console.error('Error focusing on node:', error);
        }
      } else {
        // 如果没有选中节点但需要移动，重置为默认视图
        sigma.setCustomBBox(null);
        sigma.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1 }, { duration: 0 });
      }
      useGraphStore.getState().setMoveToSelectedNode(false);
    } else if (node && graph.hasNode(node)) {
      try {
        graph.setNodeAttribute(node, 'highlighted', true);
      } catch (error) {
        console.error('Error highlighting node:', error);
      }
    }

    return () => {
      if (node && graph.hasNode(node)) {
        try {
          graph.setNodeAttribute(node, 'highlighted', false);
        } catch (error) {
          console.error('Error cleaning up node highlight:', error);
        }
      }
    };
  }, [node, move, sigma, gotoNode]);

  return null;
};

export default FocusOnNode;
