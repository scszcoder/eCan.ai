import { useEffect, useState } from 'react';
import { useRegisterEvents, useSigma, useSetSettings } from '@react-sigma/core';
import { useLayoutForceAtlas2 } from '@react-sigma/layout-forceatlas2';
import { useGraphStore } from '../stores/graph';
import { useSettingsStore } from '../stores/settings';
import { useTheme } from '@/contexts/ThemeContext';
import * as Constants from '../lib/constants';
import { AbstractGraph } from 'graphology-types';

const isButtonPressed = (ev: MouseEvent | TouchEvent) => {
  if (ev.type.startsWith('mouse')) {
    if ((ev as MouseEvent).buttons !== 0) {
      return true;
    }
  }
  return false;
};

const GraphControl: React.FC = () => {
  const sigma = useSigma();
  const register = useRegisterEvents();
  const setSettings = useSetSettings();

  const maxIterations = useSettingsStore((s) => s.graphLayoutMaxIterations || 300);
  const { assign: assignLayout } = useLayoutForceAtlas2({ iterations: maxIterations });

  const { theme } = useTheme();
  const hideUnselectedEdges = useSettingsStore((s) => s.enableHideUnselectedEdges);
  const enableEdgeEvents = useSettingsStore((s) => s.enableEdgeEvents);
  const renderEdgeLabels = useSettingsStore((s) => s.showEdgeLabel);
  const renderLabels = useSettingsStore((s) => s.showNodeLabel);
  const minEdgeSize = useSettingsStore((s) => s.minEdgeSize || 1);
  const maxEdgeSize = useSettingsStore((s) => s.maxEdgeSize || 5);
  
  const selectedNode = useGraphStore((s) => s.selectedNode);
  const focusedNode = useGraphStore((s) => s.focusedNode);
  const selectedEdge = useGraphStore((s) => s.selectedEdge);
  const focusedEdge = useGraphStore((s) => s.focusedEdge);
  const sigmaGraph = useGraphStore((s) => s.sigmaGraph);

  // Track system theme changes
  const [systemThemeIsDark, setSystemThemeIsDark] = useState(() =>
    window.matchMedia('(prefers-color-scheme: dark)').matches
  );

  useEffect(() => {
    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const handler = (e: MediaQueryListEvent) => setSystemThemeIsDark(e.matches);
      mediaQuery.addEventListener('change', handler);
      return () => mediaQuery.removeEventListener('change', handler);
    }
  }, [theme]);

  // Ensure sigma instance in store and apply layout
  useEffect(() => {
    if (sigmaGraph && sigma) {
      try {
        if (typeof (sigma as any).setGraph === 'function') {
          (sigma as any).setGraph(sigmaGraph as unknown as AbstractGraph);
        } else {
          (sigma as any).graph = sigmaGraph;
        }
      } catch (error) {
        console.error('Error setting graph on sigma instance:', error);
      }
      assignLayout();
    }
  }, [sigma, sigmaGraph, assignLayout, maxIterations]);

  // Ensure sigma instance is set in store
  useEffect(() => {
    if (sigma) {
      const currentInstance = useGraphStore.getState().sigmaInstance;
      if (!currentInstance) {
        useGraphStore.getState().setSigmaInstance(sigma as any);
      }
    }
  }, [sigma]);

  // Register events
  useEffect(() => {
    const { setFocusedNode, setSelectedNode, setFocusedEdge, setSelectedEdge, clearSelection } =
      useGraphStore.getState();

    type NodeEvent = { node: string; event: { original: MouseEvent | TouchEvent } };
    type EdgeEvent = { edge: string; event: { original: MouseEvent | TouchEvent } };

    const events: Record<string, any> = {
      enterNode: (event: NodeEvent) => {
        if (!isButtonPressed(event.event.original)) {
          const graph = sigma.getGraph();
          if (graph.hasNode(event.node)) {
            setFocusedNode(event.node);
          }
        }
      },
      leaveNode: (event: NodeEvent) => {
        if (!isButtonPressed(event.event.original)) {
          setFocusedNode(null);
        }
      },
      clickNode: (event: NodeEvent) => {
        const graph = sigma.getGraph();
        if (graph.hasNode(event.node)) {
          setSelectedNode(event.node, true);
          setSelectedEdge(null);
        }
      },
      clickStage: () => clearSelection()
    };

    if (enableEdgeEvents) {
      events.clickEdge = (event: EdgeEvent) => {
        setSelectedEdge(event.edge);
        setSelectedNode(null);
      };

      events.enterEdge = (event: EdgeEvent) => {
        if (!isButtonPressed(event.event.original)) {
          setFocusedEdge(event.edge);
        }
      };

      events.leaveEdge = (event: EdgeEvent) => {
        if (!isButtonPressed(event.event.original)) {
          setFocusedEdge(null);
        }
      };
    }

    register(events);
  }, [register, enableEdgeEvents, sigma]);

  // Dynamic edge size calculation
  useEffect(() => {
    if (sigma && sigmaGraph) {
      const graph = sigma.getGraph();
      let minWeight = Number.MAX_SAFE_INTEGER;
      let maxWeight = 0;

      graph.forEachEdge((edge) => {
        const weight = graph.getEdgeAttribute(edge, 'originalWeight') || 1;
        if (typeof weight === 'number') {
          minWeight = Math.min(minWeight, weight);
          maxWeight = Math.max(maxWeight, weight);
        }
      });

      const weightRange = maxWeight - minWeight;
      if (weightRange > 0) {
        const sizeScale = maxEdgeSize - minEdgeSize;
        graph.forEachEdge((edge) => {
          const weight = graph.getEdgeAttribute(edge, 'originalWeight') || 1;
          if (typeof weight === 'number') {
            const scaledSize = minEdgeSize + sizeScale * Math.pow((weight - minWeight) / weightRange, 0.5);
            graph.setEdgeAttribute(edge, 'size', scaledSize);
          }
        });
      } else {
        graph.forEachEdge((edge) => {
          graph.setEdgeAttribute(edge, 'size', minEdgeSize);
        });
      }

      sigma.refresh();
    }
  }, [sigma, sigmaGraph, minEdgeSize, maxEdgeSize]);

  // Apply reducers for visual effects
  useEffect(() => {
    const isDarkTheme = theme === 'dark' || (theme === 'system' && systemThemeIsDark);
    const labelColor = isDarkTheme ? Constants.labelColorDarkTheme : Constants.labelColorLightTheme;
    const edgeColor = isDarkTheme ? Constants.edgeColorDarkTheme : undefined;

    setSettings({
      enableEdgeEvents,
      renderEdgeLabels,
      renderLabels,

      nodeReducer: (node, data) => {
        const graph = sigma.getGraph();

        if (!graph.hasNode(node)) {
          return { ...data, highlighted: false, labelColor } as any;
        }

        const newData: any = { 
          ...data, 
          highlighted: data.highlighted || false, 
          labelColor 
        };

        const _focusedNode = focusedNode || selectedNode;
        const _focusedEdge = focusedEdge || selectedEdge;

        if (_focusedNode && graph.hasNode(_focusedNode)) {
          try {
            if (node === _focusedNode || graph.neighbors(_focusedNode).includes(node)) {
              newData.highlighted = true;
              if (node === selectedNode) {
                newData.borderColor = Constants.nodeBorderColorSelected;
              }
            } else {
              newData.color = Constants.nodeColorDisabled;
            }
          } catch (error) {
            console.error('Error in nodeReducer:', error);
            return { ...data, highlighted: false, labelColor } as any;
          }
        } else if (_focusedEdge && graph.hasEdge(_focusedEdge)) {
          try {
            if (graph.extremities(_focusedEdge).includes(node)) {
              newData.highlighted = true;
              newData.size = 3;
            } else {
              newData.color = Constants.nodeColorDisabled;
            }
          } catch (error) {
            console.error('Error accessing edge extremities:', error);
            return { ...data, highlighted: false, labelColor } as any;
          }
        }

        if (newData.highlighted && isDarkTheme) {
          newData.labelColor = '#ffffff';
        }

        return newData;
      },

      edgeReducer: (edge, data) => {
        const graph = sigma.getGraph();

        if (!graph.hasEdge(edge)) {
          return { ...data, hidden: false, labelColor, color: edgeColor } as any;
        }

        const newData: any = { ...data, hidden: false, labelColor, color: edgeColor };

        const _focusedNode = focusedNode || selectedNode;
        const edgeHighlightColor = isDarkTheme
          ? Constants.edgeColorHighlightedDarkTheme
          : Constants.edgeColorHighlightedLightTheme;

        if (_focusedNode && graph.hasNode(_focusedNode)) {
          try {
            if (hideUnselectedEdges) {
              if (!graph.extremities(edge).includes(_focusedNode)) {
                newData.hidden = true;
              }
            } else {
              if (graph.extremities(edge).includes(_focusedNode)) {
                newData.color = edgeHighlightColor;
              }
            }
          } catch (error) {
            console.error('Error in edgeReducer:', error);
            return { ...data, hidden: false, labelColor, color: edgeColor } as any;
          }
        } else {
          const _selectedEdge = selectedEdge && graph.hasEdge(selectedEdge) ? selectedEdge : null;
          const _focusedEdge = focusedEdge && graph.hasEdge(focusedEdge) ? focusedEdge : null;

          if (_selectedEdge || _focusedEdge) {
            if (edge === _selectedEdge) {
              newData.color = Constants.nodeBorderColorSelected;
            } else if (edge === _focusedEdge) {
              newData.color = edgeHighlightColor;
            } else if (hideUnselectedEdges) {
              newData.hidden = true;
            }
          }
        }

        return newData;
      }
    });
  }, [
    selectedNode,
    focusedNode,
    selectedEdge,
    focusedEdge,
    setSettings,
    sigma,
    theme,
    systemThemeIsDark,
    hideUnselectedEdges,
    enableEdgeEvents,
    renderEdgeLabels,
    renderLabels
  ]);

  return null;
};

export default GraphControl;
