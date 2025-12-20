/**
 * Colored Group Chat Icon
 * 彩色群组聊天图标 - Optimize层次感和Position
 */

export const GroupIconColored = ({ size = 40 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Background circle with subtle gradient */}
    <circle cx="20" cy="20" r="20" fill="url(#group-bg-gradient)" />
    
    {/* Subtle inner shadow for depth */}
    <circle cx="20" cy="20" r="19" stroke="url(#inner-shadow)" strokeWidth="2" opacity="0.15" />
    
    {/* Three people with better layering - back to front */}
    
    {/* Person 3 - Right back (smallest, most transparent) */}
    <g opacity="0.75">
      <circle cx="26" cy="18" r="3" fill="#FFFFFF" />
      <path
        d="M22 28c0-2 1.8-3.5 4-3.5s4 1.5 4 3.5"
        stroke="#FFFFFF"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
      />
    </g>
    
    {/* Person 1 - Left back (smallest, most transparent) */}
    <g opacity="0.75">
      <circle cx="14" cy="18" r="3" fill="#FFFFFF" />
      <path
        d="M10 28c0-2 1.8-3.5 4-3.5s4 1.5 4 3.5"
        stroke="#FFFFFF"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
      />
    </g>
    
    {/* Person 2 - Center front (largest, most prominent) */}
    <g opacity="1">
      <circle cx="20" cy="14" r="4.2" fill="#FFFFFF" />
      <path
        d="M14 28c0-3 2.7-5.5 6-5.5s6 2.5 6 5.5"
        stroke="#FFFFFF"
        strokeWidth="2.4"
        strokeLinecap="round"
        fill="none"
      />
    </g>
    
    <defs>
      {/* Subtle gradient with softer colors matching dark theme */}
      <linearGradient id="group-bg-gradient" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#6366F1" stopOpacity="0.6" />
        <stop offset="100%" stopColor="#8B5CF6" stopOpacity="0.5" />
      </linearGradient>
      {/* Inner shadow effect */}
      <linearGradient id="inner-shadow" x1="20" y1="0" x2="20" y2="40" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#000000" />
        <stop offset="100%" stopColor="#FFFFFF" />
      </linearGradient>
    </defs>
  </svg>
);
