/**
 * Colored Help Icon
 */
export const IconHelpColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10" fill="url(#help-gradient)" />
    <path
      d="M12 6c-1.1 0-2 .9-2 2h1.5c0-.28.22-.5.5-.5s.5.22.5.5c0 .5-.5.75-1 1.25-.5.5-1 1-1 2.25h1.5c0-.75.5-1.25 1-1.75.5-.5 1-1 1-2.25 0-1.1-.9-2-2-2zm-1 9h2v2h-2v-2z"
      fill="#FFFFFF"
    />
    <defs>
      <linearGradient id="help-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#AB47BC" />
        <stop offset="100%" stopColor="#8E24AA" />
      </linearGradient>
    </defs>
  </svg>
);
