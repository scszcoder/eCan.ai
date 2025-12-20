import React, { useMemo } from 'react';
import styled from '@emotion/styled';
import { LabelConfig } from './types';

const PreviewContainer = styled.div`
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 20px;
  background: var(--bg-secondary, #1e293b);
  border-radius: 8px;
  overflow: auto;
`;

const SvgWrapper = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: center;
  flex-shrink: 0;
`;

interface LabelPreviewProps {
  config: LabelConfig | null;
  maxWidth?: number;
  maxHeight?: number;
}

const LabelPreview: React.FC<LabelPreviewProps> = ({ 
  config, 
  maxWidth = 500, 
  maxHeight = 600 
}) => {
  const svgContent = useMemo(() => {
    if (!config) {
      return null;
    }

    const { 
      unit, 
      sheet_width, 
      sheet_height, 
      label_width, 
      label_height, 
      top_margin, 
      left_margin, 
      rows, 
      cols, 
      row_pitch, 
      col_pitch 
    } = config;

    // Calculate scale to fit in container
    const aspectRatio = sheet_width / sheet_height;
    let svgWidth: number;
    let svgHeight: number;

    if (aspectRatio > maxWidth / maxHeight) {
      svgWidth = maxWidth;
      svgHeight = maxWidth / aspectRatio;
    } else {
      svgHeight = maxHeight;
      svgWidth = maxHeight * aspectRatio;
    }

    // Scale factor from real units to SVG pixels
    const scale = svgWidth / sheet_width;

    // Padding for dimension markups
    const padding = 60;
    const totalWidth = svgWidth + padding * 2;
    const totalHeight = svgHeight + padding * 2;

    // Helper to format dimension value
    const formatDim = (value: number) => {
      return `${value.toFixed(value % 1 === 0 ? 0 : 2)} ${unit}`;
    };

    // Generate labels
    const labels: JSX.Element[] = [];
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        const x = padding + (left_margin + col * (label_width + col_pitch)) * scale;
        const y = padding + (top_margin + row * (label_height + row_pitch)) * scale;
        const w = label_width * scale;
        const h = label_height * scale;

        labels.push(
          <rect
            key={`label-${row}-${col}`}
            x={x}
            y={y}
            width={w}
            height={h}
            fill="rgba(59, 130, 246, 0.2)"
            stroke="#3b82f6"
            strokeWidth={1.5}
            rx={2}
          />
        );
      }
    }

    // Dimension markup arrows and text
    const markups: JSX.Element[] = [];
    const arrowSize = 6;
    const textOffset = 12;

    // Sheet width (bottom)
    const sheetWidthY = padding + svgHeight + 25;
    markups.push(
      <g key="sheet-width">
        <line
          x1={padding}
          y1={sheetWidthY}
          x2={padding + svgWidth}
          y2={sheetWidthY}
          stroke="#94a3b8"
          strokeWidth={1}
          markerStart="url(#arrowLeft)"
          markerEnd="url(#arrowRight)"
        />
        <text
          x={padding + svgWidth / 2}
          y={sheetWidthY + textOffset}
          fill="#94a3b8"
          fontSize={11}
          textAnchor="middle"
        >
          Sheet: {formatDim(sheet_width)}
        </text>
      </g>
    );

    // Sheet height (right)
    const sheetHeightX = padding + svgWidth + 25;
    markups.push(
      <g key="sheet-height">
        <line
          x1={sheetHeightX}
          y1={padding}
          x2={sheetHeightX}
          y2={padding + svgHeight}
          stroke="#94a3b8"
          strokeWidth={1}
          markerStart="url(#arrowUp)"
          markerEnd="url(#arrowDown)"
        />
        <text
          x={sheetHeightX + textOffset}
          y={padding + svgHeight / 2}
          fill="#94a3b8"
          fontSize={11}
          textAnchor="middle"
          transform={`rotate(90, ${sheetHeightX + textOffset}, ${padding + svgHeight / 2})`}
        >
          Sheet: {formatDim(sheet_height)}
        </text>
      </g>
    );

    // Top margin
    if (top_margin > 0) {
      const marginX = padding - 20;
      markups.push(
        <g key="top-margin">
          <line
            x1={marginX}
            y1={padding}
            x2={marginX}
            y2={padding + top_margin * scale}
            stroke="#22c55e"
            strokeWidth={1}
            markerStart="url(#arrowUpGreen)"
            markerEnd="url(#arrowDownGreen)"
          />
          <text
            x={marginX - 5}
            y={padding + (top_margin * scale) / 2}
            fill="#22c55e"
            fontSize={9}
            textAnchor="end"
            dominantBaseline="middle"
          >
            {formatDim(top_margin)}
          </text>
        </g>
      );
    }

    // Left margin
    if (left_margin > 0) {
      const marginY = padding - 20;
      markups.push(
        <g key="left-margin">
          <line
            x1={padding}
            y1={marginY}
            x2={padding + left_margin * scale}
            y2={marginY}
            stroke="#22c55e"
            strokeWidth={1}
            markerStart="url(#arrowLeftGreen)"
            markerEnd="url(#arrowRightGreen)"
          />
          <text
            x={padding + (left_margin * scale) / 2}
            y={marginY - 5}
            fill="#22c55e"
            fontSize={9}
            textAnchor="middle"
          >
            {formatDim(left_margin)}
          </text>
        </g>
      );
    }

    // Label width (first label)
    const labelWidthY = padding + top_margin * scale + label_height * scale + 15;
    markups.push(
      <g key="label-width">
        <line
          x1={padding + left_margin * scale}
          y1={labelWidthY}
          x2={padding + left_margin * scale + label_width * scale}
          y2={labelWidthY}
          stroke="#f59e0b"
          strokeWidth={1}
          markerStart="url(#arrowLeftOrange)"
          markerEnd="url(#arrowRightOrange)"
        />
        <text
          x={padding + left_margin * scale + (label_width * scale) / 2}
          y={labelWidthY + textOffset}
          fill="#f59e0b"
          fontSize={10}
          textAnchor="middle"
        >
          Label: {formatDim(label_width)}
        </text>
      </g>
    );

    // Label height (first label)
    const labelHeightX = padding + left_margin * scale + label_width * scale + 15;
    markups.push(
      <g key="label-height">
        <line
          x1={labelHeightX}
          y1={padding + top_margin * scale}
          x2={labelHeightX}
          y2={padding + top_margin * scale + label_height * scale}
          stroke="#f59e0b"
          strokeWidth={1}
          markerStart="url(#arrowUpOrange)"
          markerEnd="url(#arrowDownOrange)"
        />
        <text
          x={labelHeightX + 5}
          y={padding + top_margin * scale + (label_height * scale) / 2}
          fill="#f59e0b"
          fontSize={10}
          textAnchor="start"
          dominantBaseline="middle"
        >
          {formatDim(label_height)}
        </text>
      </g>
    );

    // Column pitch (if multiple columns)
    if (cols > 1 && col_pitch > 0) {
      const pitchY = padding + top_margin * scale + label_height * scale / 2;
      const x1 = padding + left_margin * scale + label_width * scale;
      const x2 = x1 + col_pitch * scale;
      markups.push(
        <g key="col-pitch">
          <line
            x1={x1}
            y1={pitchY}
            x2={x2}
            y2={pitchY}
            stroke="#8b5cf6"
            strokeWidth={1}
            strokeDasharray="3,2"
            markerStart="url(#arrowLeftPurple)"
            markerEnd="url(#arrowRightPurple)"
          />
          <text
            x={(x1 + x2) / 2}
            y={pitchY - 8}
            fill="#8b5cf6"
            fontSize={9}
            textAnchor="middle"
          >
            Gap: {formatDim(col_pitch)}
          </text>
        </g>
      );
    }

    // Row pitch (if multiple rows)
    if (rows > 1 && row_pitch > 0) {
      const pitchX = padding + left_margin * scale + label_width * scale / 2;
      const y1 = padding + top_margin * scale + label_height * scale;
      const y2 = y1 + row_pitch * scale;
      markups.push(
        <g key="row-pitch">
          <line
            x1={pitchX}
            y1={y1}
            x2={pitchX}
            y2={y2}
            stroke="#8b5cf6"
            strokeWidth={1}
            strokeDasharray="3,2"
            markerStart="url(#arrowUpPurple)"
            markerEnd="url(#arrowDownPurple)"
          />
          <text
            x={pitchX + 8}
            y={(y1 + y2) / 2}
            fill="#8b5cf6"
            fontSize={9}
            textAnchor="start"
            dominantBaseline="middle"
          >
            Gap: {formatDim(row_pitch)}
          </text>
        </g>
      );
    }

    return (
      <svg width={totalWidth} height={totalHeight} viewBox={`0 0 ${totalWidth} ${totalHeight}`}>
        <defs>
          {/* Gray arrows for sheet dimensions */}
          <marker id="arrowLeft" markerWidth={arrowSize} markerHeight={arrowSize} refX={0} refY={arrowSize/2} orient="auto">
            <path d={`M${arrowSize},0 L0,${arrowSize/2} L${arrowSize},${arrowSize}`} fill="none" stroke="#94a3b8" strokeWidth={1} />
          </marker>
          <marker id="arrowRight" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize} refY={arrowSize/2} orient="auto">
            <path d={`M0,0 L${arrowSize},${arrowSize/2} L0,${arrowSize}`} fill="none" stroke="#94a3b8" strokeWidth={1} />
          </marker>
          <marker id="arrowUp" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize/2} refY={0} orient="auto">
            <path d={`M0,${arrowSize} L${arrowSize/2},0 L${arrowSize},${arrowSize}`} fill="none" stroke="#94a3b8" strokeWidth={1} />
          </marker>
          <marker id="arrowDown" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize/2} refY={arrowSize} orient="auto">
            <path d={`M0,0 L${arrowSize/2},${arrowSize} L${arrowSize},0`} fill="none" stroke="#94a3b8" strokeWidth={1} />
          </marker>
          
          {/* Green arrows for margins */}
          <marker id="arrowLeftGreen" markerWidth={arrowSize} markerHeight={arrowSize} refX={0} refY={arrowSize/2} orient="auto">
            <path d={`M${arrowSize},0 L0,${arrowSize/2} L${arrowSize},${arrowSize}`} fill="none" stroke="#22c55e" strokeWidth={1} />
          </marker>
          <marker id="arrowRightGreen" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize} refY={arrowSize/2} orient="auto">
            <path d={`M0,0 L${arrowSize},${arrowSize/2} L0,${arrowSize}`} fill="none" stroke="#22c55e" strokeWidth={1} />
          </marker>
          <marker id="arrowUpGreen" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize/2} refY={0} orient="auto">
            <path d={`M0,${arrowSize} L${arrowSize/2},0 L${arrowSize},${arrowSize}`} fill="none" stroke="#22c55e" strokeWidth={1} />
          </marker>
          <marker id="arrowDownGreen" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize/2} refY={arrowSize} orient="auto">
            <path d={`M0,0 L${arrowSize/2},${arrowSize} L${arrowSize},0`} fill="none" stroke="#22c55e" strokeWidth={1} />
          </marker>
          
          {/* Orange arrows for label dimensions */}
          <marker id="arrowLeftOrange" markerWidth={arrowSize} markerHeight={arrowSize} refX={0} refY={arrowSize/2} orient="auto">
            <path d={`M${arrowSize},0 L0,${arrowSize/2} L${arrowSize},${arrowSize}`} fill="none" stroke="#f59e0b" strokeWidth={1} />
          </marker>
          <marker id="arrowRightOrange" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize} refY={arrowSize/2} orient="auto">
            <path d={`M0,0 L${arrowSize},${arrowSize/2} L0,${arrowSize}`} fill="none" stroke="#f59e0b" strokeWidth={1} />
          </marker>
          <marker id="arrowUpOrange" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize/2} refY={0} orient="auto">
            <path d={`M0,${arrowSize} L${arrowSize/2},0 L${arrowSize},${arrowSize}`} fill="none" stroke="#f59e0b" strokeWidth={1} />
          </marker>
          <marker id="arrowDownOrange" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize/2} refY={arrowSize} orient="auto">
            <path d={`M0,0 L${arrowSize/2},${arrowSize} L${arrowSize},0`} fill="none" stroke="#f59e0b" strokeWidth={1} />
          </marker>
          
          {/* Purple arrows for pitch */}
          <marker id="arrowLeftPurple" markerWidth={arrowSize} markerHeight={arrowSize} refX={0} refY={arrowSize/2} orient="auto">
            <path d={`M${arrowSize},0 L0,${arrowSize/2} L${arrowSize},${arrowSize}`} fill="none" stroke="#8b5cf6" strokeWidth={1} />
          </marker>
          <marker id="arrowRightPurple" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize} refY={arrowSize/2} orient="auto">
            <path d={`M0,0 L${arrowSize},${arrowSize/2} L0,${arrowSize}`} fill="none" stroke="#8b5cf6" strokeWidth={1} />
          </marker>
          <marker id="arrowUpPurple" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize/2} refY={0} orient="auto">
            <path d={`M0,${arrowSize} L${arrowSize/2},0 L${arrowSize},${arrowSize}`} fill="none" stroke="#8b5cf6" strokeWidth={1} />
          </marker>
          <marker id="arrowDownPurple" markerWidth={arrowSize} markerHeight={arrowSize} refX={arrowSize/2} refY={arrowSize} orient="auto">
            <path d={`M0,0 L${arrowSize/2},${arrowSize} L${arrowSize},0`} fill="none" stroke="#8b5cf6" strokeWidth={1} />
          </marker>
        </defs>

        {/* Sheet background */}
        <rect
          x={padding}
          y={padding}
          width={svgWidth}
          height={svgHeight}
          fill="#ffffff"
          stroke="#64748b"
          strokeWidth={2}
          rx={4}
        />

        {/* Labels */}
        {labels}

        {/* Dimension markups */}
        {markups}
      </svg>
    );
  }, [config, maxWidth, maxHeight]);

  if (!config) {
    return (
      <PreviewContainer>
        <div style={{ color: '#94a3b8', fontSize: 14 }}>
          Select a label configuration to preview
        </div>
      </PreviewContainer>
    );
  }

  return (
    <PreviewContainer>
      <SvgWrapper>{svgContent}</SvgWrapper>
    </PreviewContainer>
  );
};

export default LabelPreview;
