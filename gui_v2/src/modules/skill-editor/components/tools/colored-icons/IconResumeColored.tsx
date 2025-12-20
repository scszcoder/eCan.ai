/**
 * Colored Resume/Play Icon (different from main Play)
 */
export const IconResumeColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10" fill="url(#resume-gradient)" />
    <path d="M9.5 7.5v9l7-4.5-7-4.5z" fill="#FFFFFF" />
    <defs>
      <linearGradient id="resume-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#66BB6A" />
        <stop offset="100%" stopColor="#43A047" />
      </linearGradient>
    </defs>
  </svg>
);
