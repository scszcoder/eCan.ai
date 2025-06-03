import styled from '@emotion/styled';

export const CallableSelectorWrapper = styled.div`
  width: 100%;
  max-width: 100%;

  .callable-selector {
    display: flex;
    align-items: center;
    gap: 4px;
    width: 100%;
  }

  .ant-select {
    flex: 1;
    width: 100%;
  }

  .ant-select-selector {
    background-color: #f5f5f5 !important;
    width: 100% !important;
    transition: all 0.3s;

    &:hover {
      background-color: #e6e6e6 !important;
    }
  }

  .ant-select-selection-item {
    color: #333 !important;
    font-size: 14px;
    line-height: 1.5;
  }

  .ant-select-dropdown {
    background-color: #fff;
    border-radius: 4px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    max-width: 300px !important;
  }

  .ant-select-item {
    padding: 8px 12px;
    color: #333;
    font-size: 14px;
    line-height: 1.5;
    transition: background 0.3s;
    white-space: normal;
    word-break: break-word;

    &:hover {
      background-color: #f5f5f5;
    }

    &-option-selected {
      background-color: #e6f7ff !important;
      color: #1890ff;
    }
  }

  .ant-btn {
    padding: 4px 8px;
    height: 32px;
    margin-left: 0;
    flex-shrink: 0;
    background-color: #f5f5f5;
    border-color: #d9d9d9;
    color: #666;
    transition: all 0.3s;
    box-shadow: none;

    &:hover {
      background-color: #e6e6e6 !important;
      border-color: #d9d9d9 !important;
      color: #333 !important;
      box-shadow: none !important;
    }

    &:active {
      background-color: #d9d9d9 !important;
      border-color: #d9d9d9 !important;
      color: #333 !important;
      box-shadow: none !important;
    }

    &[disabled] {
      background-color: #f5f5f5 !important;
      border-color: #d9d9d9 !important;
      color: #bfbfbf !important;
      box-shadow: none !important;
    }

    .anticon {
      font-size: 14px;
    }
  }

  .function-option {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .function-name {
    font-weight: 500;
    color: inherit;
  }

  .function-desc {
    color: #666;
    font-size: 12px;
  }
`;

export const CallableEditorWrapper = styled.div`
  width: 100%;
  max-width: 100%;

  .code-preview {
    background-color: #f5f5f5;
    padding: 12px;
    border-radius: 4px;
    margin-top: 8px;
    width: 100%;
  }

  .schema-editor {
    margin-top: 16px;
    width: 100%;
  }
`; 