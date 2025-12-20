/**
 * Colored Git/Branch Icon
 */
export const IconGitColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M6 3c-1.1 0-2 .9-2 2 0 .8.5 1.5 1.2 1.8v10.4c-.7.3-1.2 1-1.2 1.8 0 1.1.9 2 2 2s2-.9 2-2c0-.8-.5-1.5-1.2-1.8V12h4.2c.7 0 1.3-.3 1.8-.8l3-3c.5-.5 1.1-.8 1.8-.8H18c.7 0 1.2-1 1.2-1.8 0-1.1-.9-2-2-2s-2 .9-2 2c0 .8.5 1.5 1.2 1.8h-1.2c-1.3 0-2.6.5-3.5 1.5l-3 3c-.2.2-.5.3-.8.3H7V6.8C7.5 6.5 8 5.8 8 5c0-1.1-.9-2-2-2z"
      fill="url(#git-gradient)"
    />
    <defs>
      <linearGradient id="git-gradient" x1="4" y1="3" x2="20" y2="21" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#FF6B6B" />
        <stop offset="100%" stopColor="#EE5A6F" />
      </linearGradient>
    </defs>
  </svg>
);
