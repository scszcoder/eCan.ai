import { useEffect } from 'react';
import { useSigma, useRegisterEvents } from '@react-sigma/core';
import { useGraphStore } from '../stores/graph';

/**
 * Component that enables dragging nodes in the graph.
 * Nodes can be dragged to reposition them manually.
 */
const DragNodes: React.FC = () => {
  const sigma = useSigma();
  const graph = sigma.getGraph();
  const registerEvents = useRegisterEvents();
  const setSelectedNode = useGraphStore((s) => s.setSelectedNode);

  useEffect(() => {
    let draggedNode: string | null = null;
    let isDragging = false;

    // Register Sigma event handlers
    registerEvents({
      downNode: (e) => {
        isDragging = true;
        draggedNode = e.node;
        
        // Select the node
        setSelectedNode(draggedNode, false);
        
        // Disable camera movement while dragging
        sigma.getCamera().disable();
        
        console.log('[DragNodes] Start dragging node:', draggedNode);
      },
      
      mousemove: (e) => {
        if (!isDragging || !draggedNode) return;

        // Get the pointer position in graph coordinates
        const pos = sigma.viewportToGraph(e);

        // Update node position
        graph.setNodeAttribute(draggedNode, 'x', pos.x);
        graph.setNodeAttribute(draggedNode, 'y', pos.y);

        // Prevent default to avoid text selection
        e.preventSigmaDefault();
        e.original.preventDefault();
      },
      
      mouseup: () => {
        if (isDragging && draggedNode) {
          console.log('[DragNodes] Stop dragging node:', draggedNode);
          
          // Re-enable camera movement
          sigma.getCamera().enable();
          
          isDragging = false;
          draggedNode = null;
        }
      },
      
      mousedown: () => {
        // If clicking on empty space, ensure dragging is disabled
        if (!isDragging) {
          sigma.getCamera().enable();
        }
      }
    });
  }, [sigma, graph, registerEvents, setSelectedNode]);

  return null;
};

export default DragNodes;
