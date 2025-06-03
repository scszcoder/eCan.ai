import styled from '@emotion/styled';

export const CallableSelectorWrapper = styled.div`
  width: 100%;
  max-width: 100%;

  .selector-container {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;

    .semi-select {
      flex: 1;
    }

    .settings-button {
      flex-shrink: 0;
      width: 24px;
      height: 24px;
      padding: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--semi-color-text-2);
      border-radius: 4px;
      
      &:hover {
        color: var(--semi-color-text-0);
        background-color: var(--semi-color-fill-0);
      }

      .semi-icon {
        font-size: 14px;
      }
    }
  }

  .semi-select-option {
    padding: 8px 12px;
  }

  .function-option {
    display: flex;
    align-items: center;
    padding: 4px 0;
    width: 100%;
    white-space: nowrap;
    gap: 12px;
    
    .function-icon {
      display: flex;
      align-items: center;
      color: var(--semi-color-text-2);
      flex-shrink: 0;
    }
    
    .function-name {
      font-weight: 500;
      color: var(--semi-color-text-0);
      flex-shrink: 0;
    }
  }
`;

export const CallableEditorWrapper = styled.div`
  width: 100%;
  max-width: 100%;
  color: var(--semi-color-text-0);

  .ant-form-item-label > label {
    color: var(--semi-color-text-0);
  }

  .ant-input,
  .ant-input-textarea,
  .ant-select-selector {
    color: var(--semi-color-text-0);
  }

  .ant-select-selection-item {
    color: var(--semi-color-text-0);
  }

  .code-preview {
    margin-top: 16px;
    background: var(--semi-color-bg-2);
    border-radius: 4px;
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
    font-size: 12px;
    line-height: 1.5;
    white-space: pre;
    overflow-x: auto;
    color: var(--semi-color-text-0);
  }

  .schema-editor {
    margin-top: 16px;

    .monaco-editor {
      .margin {
        background-color: var(--semi-color-bg-2);
      }
    }

    .monaco-editor-background {
      background-color: var(--semi-color-bg-2);
    }

    .monaco-editor .margin-view-overlays .cgmr {
      background-color: var(--semi-color-bg-2);
    }

    .monaco-editor .view-overlays .current-line {
      background-color: var(--semi-color-fill-0);
    }

    .monaco-editor .line-numbers {
      color: var(--semi-color-text-0);
    }

    .monaco-editor .view-line {
      color: var(--semi-color-text-0);
    }

    .monaco-editor .token {
      color: var(--semi-color-text-0);
    }

    .monaco-editor .mtk1,
    .monaco-editor .mtk2,
    .monaco-editor .mtk3,
    .monaco-editor .mtk4,
    .monaco-editor .mtk5,
    .monaco-editor .mtk6,
    .monaco-editor .mtk7,
    .monaco-editor .mtk8,
    .monaco-editor .mtk9,
    .monaco-editor .mtk10,
    .monaco-editor .mtk11,
    .monaco-editor .mtk12,
    .monaco-editor .mtk13,
    .monaco-editor .mtk14,
    .monaco-editor .mtk15,
    .monaco-editor .mtk16,
    .monaco-editor .mtk17,
    .monaco-editor .mtk18,
    .monaco-editor .mtk19,
    .monaco-editor .mtk20,
    .monaco-editor .mtk21,
    .monaco-editor .mtk22,
    .monaco-editor .mtk23,
    .monaco-editor .mtk24,
    .monaco-editor .mtk25,
    .monaco-editor .mtk26,
    .monaco-editor .mtk27,
    .monaco-editor .mtk28,
    .monaco-editor .mtk29,
    .monaco-editor .mtk30 {
      color: var(--semi-color-text-0);
    }

    .monaco-editor .monaco-editor-background,
    .monaco-editor .margin,
    .monaco-editor .margin-view-overlays .cgmr,
    .monaco-editor .view-overlays .current-line {
      background-color: var(--semi-color-bg-2);
    }

    .monaco-editor .view-line,
    .monaco-editor .line-numbers,
    .monaco-editor .token,
    .monaco-editor .mtk1,
    .monaco-editor .mtk2,
    .monaco-editor .mtk3,
    .monaco-editor .mtk4,
    .monaco-editor .mtk5,
    .monaco-editor .mtk6,
    .monaco-editor .mtk7,
    .monaco-editor .mtk8,
    .monaco-editor .mtk9,
    .monaco-editor .mtk10,
    .monaco-editor .mtk11,
    .monaco-editor .mtk12,
    .monaco-editor .mtk13,
    .monaco-editor .mtk14,
    .monaco-editor .mtk15,
    .monaco-editor .mtk16,
    .monaco-editor .mtk17,
    .monaco-editor .mtk18,
    .monaco-editor .mtk19,
    .monaco-editor .mtk20,
    .monaco-editor .mtk21,
    .monaco-editor .mtk22,
    .monaco-editor .mtk23,
    .monaco-editor .mtk24,
    .monaco-editor .mtk25,
    .monaco-editor .mtk26,
    .monaco-editor .mtk27,
    .monaco-editor .mtk28,
    .monaco-editor .mtk29,
    .monaco-editor .mtk30 {
      color: var(--semi-color-text-0);
    }
  }
`; 