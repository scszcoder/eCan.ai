import { useEffect } from 'react';
import { useRegisterEvents, useSigma } from '@react-sigma/core';
import { useGraphStore } from '../stores/graph';

const GraphControl: React.FC = () => {
  const sigma = useSigma();
  const register = useRegisterEvents();

  // ensure sigma instance in store
  useEffect(() => {
    if (sigma) {
      const cur = useGraphStore.getState().sigmaInstance;
      if (!cur) useGraphStore.getState().setSigmaInstance(sigma as any);
    }
  }, [sigma]);

  useEffect(() => {
    const { setSelectedNode, setFocusedNode, setSelectedEdge, setFocusedEdge } = useGraphStore.getState();
    register({
      enterNode: (e) => setFocusedNode(e.node),
      leaveNode: () => setFocusedNode(null),
      clickNode: (e) => { setSelectedNode(e.node, true); setSelectedEdge(null); },
      clickStage: () => { setSelectedNode(null); setSelectedEdge(null); setFocusedNode(null); setFocusedEdge(null); }
    });
  }, [register]);

  return null;
};

export default GraphControl;
