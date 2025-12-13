export interface LabelConfig {
  name: string;
  id: string;
  unit: 'in' | 'mm';
  sheet_width: number;
  sheet_height: number;
  label_width: number;
  label_height: number;
  top_margin: number;
  left_margin: number;
  rows: number;
  cols: number;
  row_pitch: number;
  col_pitch: number;
  _filepath?: string;
  _filename?: string;
}

export type ConfigSource = 'system' | 'user' | 'custom';

export interface DimensionMarkup {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  value: number;
  unit: string;
}
