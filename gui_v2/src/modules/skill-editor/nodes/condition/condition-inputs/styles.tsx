import styled from 'styled-components';

export const ConditionPort = styled.div`
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--primary-color, #3b82f6);
  border: 2px solid #fff;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  cursor: crosshair;
  z-index: 100;
  pointer-events: auto;
`;
