import { usePlayground, WorkflowLineEntity } from '@flowgram.ai/free-layout-editor';

import './index.less';

export const useVisible = (params: {
  line: WorkflowLineEntity;
  selected?: boolean;
  hovered?: boolean;
}): boolean => {
  const playground = usePlayground();
  const { line, selected = false, hovered } = params;
  if (line.disposed) {
    // 在 dispose 后，再去Get line.to | line.from 会导致ErrorCreate端口
    return false;
  }
  if (playground.config.readonly) {
    return false;
  }
  if (!selected && !hovered) {
    return false;
  }
  return true;
};
