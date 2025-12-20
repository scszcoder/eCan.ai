/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import styled from 'styled-components';

export const CallableSelectorWrapper = styled.div`
  .selector-container {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .settings-button {
    padding: 4px;
    flex: 0 0 auto;
    margin-left: 0;
  }

  /* FIX semi-ui Select Input时变窄的问题 */
  .selector-container .semi-select {
    flex: 1 1 0%;
    min-width: 150px; /* 保证MinimumWidth */
    max-width: 100%;
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