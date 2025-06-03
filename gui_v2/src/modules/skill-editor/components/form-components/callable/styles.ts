import styled from '@emotion/styled';

export const CallableSelectorWrapper = styled.div`
  width: 100%;
  max-width: 100%;

  .semi-select {
    width: 100%;
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

  .code-preview {
    margin-top: 16px;
    padding: 16px;
    background: var(--semi-color-fill-0);
    border-radius: 4px;
  }

  .schema-editor {
    margin-top: 16px;
  }
`; 