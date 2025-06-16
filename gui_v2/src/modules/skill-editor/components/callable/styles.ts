import styled from 'styled-components';

export const CallableSelectorWrapper = styled.div`
  width: 100%;
  max-width: 100%;

  .selector-container {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .function-option {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;

    .function-icon {
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--semi-color-text-2);
      width: 16px;
      height: 16px;
    }

    .function-name {
      color: var(--semi-color-text-0);
    }
  }

  .settings-button {
    padding: 4px;
  }

  .semi-select-option {
    padding: 8px 12px;

    .function-option {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px 0;

      .function-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--semi-color-text-2);
        width: 16px;
        height: 16px;
      }

      .function-name {
        color: var(--semi-color-text-0);
      }
    }
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
    color: #fff !important;
  }

  .ant-form-item-required::before {
    color: #fff !important;
  }

  .ant-input {
    color: #fff !important;
    background-color: transparent !important;
  }

  .ant-input::placeholder {
    color: rgba(255, 255, 255, 0.5) !important;
  }

  .ant-input:focus {
    border-color: #fff !important;
  }

  .ant-input:hover {
    border-color: rgba(255, 255, 255, 0.8) !important;
  }

  .ant-select-selection-item {
    color: #fff !important;
  }

  .ant-select-selection-placeholder {
    color: rgba(255, 255, 255, 0.5) !important;
  }

  .ant-select-arrow {
    color: #fff !important;
  }

  .ant-select-item-option-selected {
    color: #fff !important;
    background-color: var(--semi-color-fill-0) !important;
  }

  .ant-select-item-option-active {
    background-color: var(--semi-color-fill-1) !important;
  }

  .ant-select-dropdown {
    background-color: var(--semi-color-bg-2);
  }

  .code-preview {
    margin-top: 8px;
    border: 1px solid var(--semi-color-border);
    border-radius: 4px;
    overflow: hidden;
  }
`; 