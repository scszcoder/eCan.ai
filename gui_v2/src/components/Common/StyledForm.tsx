import styled from '@emotion/styled';
import { Form, Card } from 'antd';

/**
 * 全局统一的Form项样式
 * 解决 label 和Input框间距太近、Input框边框不明显的问题
 *
 * All control geometry/colors resolve from the design tokens in
 * src/styles/global.css so this file stays theme-agnostic (dark + light).
 */
export const StyledFormItem = styled(Form.Item)`
  margin-bottom: 16px !important;

  .ant-form-item-label {
    padding-bottom: 8px !important;
    
    > label {
      font-size: 14px;
      font-weight: 600;
      color: var(--text-primary);
      letter-spacing: 0.3px;
      
      /* 移除冒号 */
      &::after {
        content: '' !important;
        margin: 0 !important;
      }
      
      /* 保留必填星号（Ant Design 使用 .ant-form-item-required 类） */
      &.ant-form-item-required::before {
        color: var(--error-text) !important;
        font-size: 14px !important;
        margin-right: 4px !important;
      }
    }
  }
  
  /* Input with suffix/prefix (affix wrapper) */
  .ant-input-affix-wrapper {
    min-height: var(--control-height-md) !important;
    border: 1.5px solid var(--border-color) !important;
    border-radius: var(--control-radius) !important;
    background: var(--control-bg) !important;
    transition: all 0.3s ease !important;
    
    &:hover {
      border-color: var(--primary-border) !important;
      background: var(--control-bg-hover) !important;
    }
    
    &:focus,
    &:focus-within,
    &.ant-input-affix-wrapper-focused {
      border-color: var(--primary-light) !important;
      background: var(--control-bg-focus) !important;
      box-shadow: var(--shadow-focus) !important;
    }
    
    /* Inner input should have no border */
    .ant-input {
      border: none !important;
      background: transparent !important;
      box-shadow: none !important;
      min-height: auto !important;
    }
  }
  
  /* Standalone Input (no suffix/prefix) */
  .ant-input:not(.ant-input-affix-wrapper .ant-input):not(textarea),
  .ant-input-number,
  .ant-input-number-input,
  .ant-picker {
    min-height: var(--control-height-md) !important;
    border: 1.5px solid var(--border-color) !important;
    border-radius: var(--control-radius) !important;
    background: var(--control-bg) !important;
    transition: all 0.3s ease !important;

    &:hover {
      border-color: var(--primary-border) !important;
      background: var(--control-bg-hover) !important;
    }

    &:focus,
    &:focus-within {
      border-color: var(--primary-light) !important;
      background: var(--control-bg-focus) !important;
      box-shadow: var(--shadow-focus) !important;
    }
  }
  
  /* Password input wrapper */
  .ant-input-password {
    min-height: var(--control-height-md) !important;
    border: 1.5px solid var(--border-color) !important;
    border-radius: var(--control-radius) !important;
    background: var(--control-bg) !important;
    transition: all 0.3s ease !important;
    
    &:hover {
      border-color: var(--primary-border) !important;
      background: var(--control-bg-hover) !important;
    }
    
    &:focus-within,
    &.ant-input-affix-wrapper-focused {
      border-color: var(--primary-light) !important;
      background: var(--control-bg-focus) !important;
      box-shadow: var(--shadow-focus) !important;
    }
    
    .ant-input {
      border: none !important;
      background: transparent !important;
      box-shadow: none !important;
      min-height: auto !important;
    }
  }
  
  /* Select / multiple select */
  .ant-select-selector {
    min-height: var(--control-height-md) !important;
    border: 1.5px solid var(--border-color) !important;
    border-radius: var(--control-radius) !important;
    background: var(--control-bg) !important;
    transition: all 0.3s ease !important;
  }

  .ant-select:not(.ant-select-disabled):hover .ant-select-selector {
    border-color: var(--primary-border) !important;
    background: var(--control-bg-hover) !important;
  }

  .ant-select-focused .ant-select-selector,
  .ant-select-open .ant-select-selector {
    border-color: var(--primary-light) !important;
    background: var(--control-bg-focus) !important;
    box-shadow: var(--shadow-focus) !important;
  }

  /* Multi-select must be free to grow with its tags: min-height only,
     never a fixed height. */
  .ant-select-multiple .ant-select-selector {
    min-height: var(--control-height-md) !important;
    padding: 0 8px !important;
    align-items: center !important;
  }

  .ant-select-multiple .ant-select-selection-overflow {
    flex-wrap: nowrap !important;
    overflow: hidden;
  }

  .ant-select-multiple .ant-select-selection-item,
  .ant-select-multiple .ant-select-selection-placeholder {
    height: 24px !important;
    line-height: 22px !important;
  }

  .ant-select-multiple .ant-select-selection-item {
    display: inline-flex;
    align-items: center;
    max-width: 100%;
    margin-inline-end: 4px !important;
  }

  .ant-select-multiple .ant-select-selection-item-content {
    white-space: nowrap !important;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .ant-select-single .ant-select-selector {
    height: var(--control-height-md) !important;
    padding: 0 11px !important;
    align-items: center !important;
  }

  .ant-select-single .ant-select-selection-item,
  .ant-select-single .ant-select-selection-placeholder {
    line-height: calc(var(--control-height-md) - 2px) !important;
  }

  /* DisabledStatus */
  .ant-input-disabled,
  .ant-input-number-disabled,
  .ant-select-disabled .ant-select-selector,
  .ant-picker-disabled,
  .ant-checkbox-disabled,
  .ant-radio-disabled {
    background: var(--control-bg) !important;
    border-color: var(--border-color) !important;
    color: var(--text-tertiary) !important;
    cursor: not-allowed !important;
  }
  
  /* TextArea Container样式 */
  .ant-input-textarea {
    border: 1.5px solid var(--border-color) !important;
    border-radius: var(--control-radius) !important;
    background: var(--control-bg) !important;
    transition: all 0.3s ease !important;

    &:hover {
      border-color: var(--primary-border) !important;
      background: var(--control-bg-hover) !important;
    }

    &:focus-within {
      border-color: var(--primary-light) !important;
      background: var(--control-bg-focus) !important;
      box-shadow: var(--shadow-focus) !important;
    }
  }

  /* TextArea Internal textarea 元素样式 */
  .ant-input-textarea textarea.ant-input {
    padding: 12px 14px !important;
    background: transparent !important;
    border: none !important;
    color: var(--text-primary) !important;
    min-height: auto !important;
    height: auto !important;

    &:focus {
      box-shadow: none !important;
    }
  }

  /* Select / Picker 箭头颜色（保持 AntD 默认布局） */
  .ant-select-arrow,
  .ant-picker-suffix {
    color: var(--text-secondary) !important;
  }
  
  /* Placeholder 样式 */
  input::placeholder,
  textarea::placeholder {
    color: var(--text-tertiary) !important;
  }

  /* Checkbox 和 Radio 样式 */
  .ant-checkbox-wrapper,
  .ant-radio-wrapper {
    color: var(--text-secondary);
  }
  
  .ant-checkbox-inner,
  .ant-radio-inner {
    border: 1.5px solid var(--border-color) !important;
    background: var(--control-bg) !important;
  }
  
  .ant-checkbox-checked .ant-checkbox-inner,
  .ant-radio-checked .ant-radio-inner {
    border-color: var(--primary-light) !important;
    background: var(--primary-light) !important;
  }
`;

/**
 * 全局统一的卡片样式
 */
export const StyledCard = styled(Card)`
  background: var(--bg-secondary) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: var(--radius-lg) !important;
  
  .ant-card-head {
    border-bottom: 1px solid var(--border-color) !important;
    padding: 16px 24px !important;
    
    .ant-card-head-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--text-primary);
    }
  }
  
  .ant-card-body {
    padding: 24px !important;
  }
`;

/**
 * FormContainer样式
 */
export const FormContainer = styled.div`
  max-height: 100%;
  overflow: auto;
  padding: 24px;
  background: var(--bg-secondary);
`;

/**
 * ButtonContainer样式
 */
export const ButtonContainer = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 8px;
  padding: 20px 24px;
  background: var(--control-bg);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
`;

/**
 * 统一的Button样式Property
 */
export const buttonStyle = {
  height: 'var(--control-height-lg)',
  borderRadius: 'var(--control-radius)',
  fontWeight: 500,
  minWidth: '100px',
};

/**
 * 统一的大Button样式Property（Used forMainOperation）
 */
export const primaryButtonStyle = {
  ...buttonStyle,
  minWidth: '120px',
};
