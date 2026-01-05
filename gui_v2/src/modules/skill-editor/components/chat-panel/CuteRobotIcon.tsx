/**
 * CuteRobotIcon - Shared cute robot SVG icon component
 */

import React from 'react';

export const CuteRobotIcon: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Robot head */}
    <rect x="4" y="6" width="16" height="14" rx="3" fill="white" />
    {/* Antenna */}
    <circle cx="12" cy="3" r="2" fill="#FFD93D" />
    <rect x="11" y="4" width="2" height="3" fill="white" />
    {/* Left eye */}
    <circle cx="8.5" cy="11" r="2.5" fill="#3B82F6" />
    <circle cx="9" cy="10.5" r="1" fill="white" />
    {/* Right eye */}
    <circle cx="15.5" cy="11" r="2.5" fill="#3B82F6" />
    <circle cx="16" cy="10.5" r="1" fill="white" />
    {/* Smile */}
    <path
      d="M8 15.5C8 15.5 9.5 17.5 12 17.5C14.5 17.5 16 15.5 16 15.5"
      stroke="#3B82F6"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    {/* Cheeks */}
    <circle cx="6" cy="14" r="1.5" fill="#FFB6C1" opacity="0.6" />
    <circle cx="18" cy="14" r="1.5" fill="#FFB6C1" opacity="0.6" />
  </svg>
);

export default CuteRobotIcon;
