import styled from '@emotion/styled';
import { Form, Card } from 'antd';

/**
 * 全局统一的表单项样式
 * 解决 label 和输入框间距太近、输入框边框不明显的问题
 */
export const StyledFormItem = styled(Form.Item)`
  margin-bottom: 24px !important;
  
  .ant-form-item-label {
    padding-bottom: 12px !important;
    
    > label {
      font-size: 14px;
      font-weight: 600;
      color: rgba(255, 255, 255, 0.95);
      letter-spacing: 0.3px;
      
      &::after {
        content: '' !important;
      }
    }
  }
  
  /* 所有输入框的统一样式（排除 TextArea） */
  .ant-input:not(textarea),
  .ant-input-number,
  .ant-input-number-input,
  .ant-picker,
  .ant-select-selector {
    min-height: 44px !important;
    border: 1.5px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 8px !important;
    background: rgba(255, 255, 255, 0.05) !important;
    transition: all 0.3s ease !important;

    &:hover {
      border-color: rgba(64, 169, 255, 0.5) !important;
      background: rgba(255, 255, 255, 0.08) !important;
    }

    &:focus,
    &:focus-within {
      border-color: #40a9ff !important;
      background: rgba(255, 255, 255, 0.1) !important;
      box-shadow: 0 0 0 2px rgba(64, 169, 255, 0.1) !important;
    }
  }
  
  /* 禁用状态 */
  .ant-input-disabled,
  .ant-input-number-disabled,
  .ant-select-disabled .ant-select-selector,
  .ant-picker-disabled,
  .ant-checkbox-disabled,
  .ant-radio-disabled {
    background: rgba(255, 255, 255, 0.03) !important;
    border-color: rgba(255, 255, 255, 0.08) !important;
    color: rgba(255, 255, 255, 0.5) !important;
    cursor: not-allowed !important;
  }
  
  /* TextArea 容器样式 */
  .ant-input-textarea {
    border: 1.5px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 8px !important;
    background: rgba(255, 255, 255, 0.05) !important;
    transition: all 0.3s ease !important;

    &:hover {
      border-color: rgba(64, 169, 255, 0.5) !important;
      background: rgba(255, 255, 255, 0.08) !important;
    }

    &:focus-within {
      border-color: #40a9ff !important;
      background: rgba(255, 255, 255, 0.1) !important;
      box-shadow: 0 0 0 2px rgba(64, 169, 255, 0.1) !important;
    }
  }

  /* TextArea 内部 textarea 元素样式 */
  .ant-input-textarea textarea.ant-input {
    padding: 12px 14px !important;
    background: transparent !important;
    border: none !important;
    color: rgba(255, 255, 255, 0.95) !important;
    min-height: auto !important;
    height: auto !important;

    &:focus {
      box-shadow: none !important;
    }
  }
  
  /* Select 下拉箭头 */
  .ant-select-arrow,
  .ant-picker-suffix {
    color: rgba(255, 255, 255, 0.45) !important;
  }
  
  /* Placeholder 样式 */
  input::placeholder,
  textarea::placeholder {
    color: rgba(255, 255, 255, 0.35) !important;
  }
  
  /* Checkbox 和 Radio 样式 */
  .ant-checkbox-wrapper,
  .ant-radio-wrapper {
    color: rgba(255, 255, 255, 0.85);
  }
  
  .ant-checkbox-inner,
  .ant-radio-inner {
    border: 1.5px solid rgba(255, 255, 255, 0.15) !important;
    background: rgba(255, 255, 255, 0.05) !important;
  }
  
  .ant-checkbox-checked .ant-checkbox-inner,
  .ant-radio-checked .ant-radio-inner {
    border-color: #40a9ff !important;
    background: #40a9ff !important;
  }
`;

/**
 * 全局统一的卡片样式
 */
export const StyledCard = styled(Card)`
  background: rgba(255, 255, 255, 0.02) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  border-radius: 12px !important;
  
  .ant-card-head {
    border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    padding: 16px 24px !important;
    
    .ant-card-head-title {
      font-size: 15px;
      font-weight: 600;
      color: rgba(255, 255, 255, 0.95);
    }
  }
  
  .ant-card-body {
    padding: 24px !important;
  }
`;

/**
 * 表单容器样式
 */
export const FormContainer = styled.div`
  max-height: 100%;
  overflow: auto;
  padding: 24px;
  background: rgba(0, 0, 0, 0.2);
`;

/**
 * 按钮容器样式
 */
export const ButtonContainer = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 8px;
  padding: 20px 24px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
`;

/**
 * 统一的按钮样式属性
 */
export const buttonStyle = {
  height: '44px',
  borderRadius: '8px',
  fontWeight: 500,
  minWidth: '100px',
};

/**
 * 统一的大按钮样式属性（用于主要操作）
 */
export const primaryButtonStyle = {
  ...buttonStyle,
  minWidth: '120px',
};

