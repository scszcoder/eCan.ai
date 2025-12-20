/**
 * Colored Step/Forward Icon
 */
export const IconStepColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10" fill="url(#step-gradient)" />
    <path d="M7.5 6.5l7 5.5-7 5.5V6.5z" fill="#FFFFFF" />
    <rect x="15" y="7" width="2.5" height="10" rx="1" fill="#FFFFFF" />
    <defs>
      <linearGradient id="step-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#42A5F5" />
        <stop offset="100%" stopColor="#1E88E5" />
      </linearGradient>
    </defs>
  </svg>
);
