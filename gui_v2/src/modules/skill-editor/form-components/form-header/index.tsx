import { Field, FieldRenderProps } from '@flowgram.ai/free-layout-editor';
import { useClientContext, CommandService, FlowNodeFormData, FormModelV2 } from '@flowgram.ai/free-layout-editor';
import { Typography, Button, Input } from '@douyinfe/semi-ui';
import { IconSmallTriangleDown, IconSmallTriangleLeft } from '@douyinfe/semi-icons';
import { useCallback, useState } from 'react';

import { Feedback } from '../feedback';
import { FlowCommandId } from '../../shortcuts';
import { useIsSidebar, useNodeRenderContext } from '../../hooks';
import { NodeMenu } from '../../components/node-menu';
import { getIcon } from './utils';
import { Header, Operators, Title } from './styles';

const { Text } = Typography;

export function FormHeader() {
  const { node, expanded, toggleExpand, readonly } = useNodeRenderContext();
  const ctx = useClientContext();
  const isSidebar = useIsSidebar();
  const [isEditing, setIsEditing] = useState(false);
  const formModel = node.getData(FlowNodeFormData).getFormModel<FormModelV2>();
  const [title, setTitle] = useState(formModel.getValueIn<string>('title') || '');

  const handleExpand = (e: React.MouseEvent) => {
    toggleExpand();
    e.stopPropagation(); // Disable clicking prevents the sidebar from opening
  };

  const handleDelete = () => {
    ctx.get<CommandService>(CommandService).executeCommand(FlowCommandId.DELETE, [node]);
  };

  const handleDoubleClick = useCallback(() => {
    if (!readonly) {
      setIsEditing(true);
    }
  }, [readonly]);

  const handleTitleChange = useCallback((value: string) => {
    setTitle(value);
  }, []);

  const handleTitleConfirm = useCallback(() => {
    setIsEditing(false);
    formModel.setValueIn('title', title);
  }, [formModel, title]);

  const handleTitleCancel = useCallback(() => {
    setIsEditing(false);
    setTitle(formModel.getValueIn<string>('title') || '');
  }, [formModel]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleTitleConfirm();
    } else if (e.key === 'Escape') {
      handleTitleCancel();
    }
  }, [handleTitleConfirm, handleTitleCancel]);

  return (
    <Header>
      {getIcon(node)}
      <Title>
        <Field name="title">
          {({ field: { value }, fieldState }: FieldRenderProps<string>) => (
            <div style={{ height: 24 }} onDoubleClick={handleDoubleClick}>
              {isEditing ? (
                <Input
                  value={title}
                  onChange={handleTitleChange}
                  onBlur={handleTitleConfirm}
                  onKeyDown={handleKeyDown}
                  autoFocus
                  size="small"
                  style={{ width: '100%' }}
                />
              ) : (
                <Text ellipsis={{ showTooltip: true }}>{value}</Text>
              )}
              <Feedback errors={fieldState?.errors} />
            </div>
          )}
        </Field>
      </Title>
      {node.renderData.expandable && !isSidebar && (
        <Button
          type="primary"
          icon={expanded ? <IconSmallTriangleDown /> : <IconSmallTriangleLeft />}
          size="small"
          theme="borderless"
          onClick={handleExpand}
        />
      )}
      {readonly ? undefined : (
        <Operators>
          <NodeMenu node={node} deleteNode={handleDelete} />
        </Operators>
      )}
    </Header>
  );
}
