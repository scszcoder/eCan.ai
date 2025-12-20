import type { ReactNode, FC, CSSProperties } from 'react';

interface ICommentContainer {
  focused: boolean;
  children?: ReactNode;
  style?: React.CSSProperties;
}

export const CommentContainer: FC<ICommentContainer> = (props) => {
  const { focused, children, style } = props;

  const scrollbarStyle = {
    // Scroll条样式
    scrollbarWidth: 'thin',
    scrollbarColor: 'rgb(159 159 158 / 65%) transparent',
    // 针对 WebKit Browser（如 Chrome、Safari）的样式
    '&:WebkitScrollbar': {
      width: '4px',
    },
    '&::WebkitScrollbarTrack': {
      background: 'transparent',
    },
    '&::WebkitScrollbarThumb': {
      backgroundColor: 'rgb(159 159 158 / 65%)',
      borderRadius: '20px',
      border: '2px solid transparent',
    },
  } as unknown as CSSProperties;

  return (
    <div
      className="workflow-comment-container"
      data-flow-editor-selectable="false"
      style={{
        // tailwind 不Support outline 的样式，所以这里Need使用 style 来Settings
        outline: focused ? '1px solid #FF811A' : '1px solid #F2B600',
        backgroundColor: focused ? '#FFF3EA' : '#FFFBED',
        ...scrollbarStyle,
        ...style,
      }}
    >
      {children}
    </div>
  );
};
