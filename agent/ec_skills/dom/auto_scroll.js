/**
 * Scrolls down the page in increments until the page height stabilizes,
 * ensuring all lazy-loaded content is triggered.
 *
 * This function is designed to be called with Selenium's `execute_async_script`.
 * It returns the number of downward scrolls performed via the callback.
 */
async function scrollToPageBottom() {
  const done = arguments[arguments.length - 1];
  const root = document.documentElement;
  const scrollStep = Math.round(window.innerHeight * 0.85);
  const maxScrolls = 40; // Hard safety cap
  let downScrolls = 0;
  let lastHeight = -1;
  let stableCount = 0;
  const maxStableCount = 3;

  try {
    while (stableCount < maxStableCount && downScrolls < maxScrolls) {
      const currentHeight = root.scrollHeight;
      if (currentHeight === lastHeight) {
        stableCount++;
      } else {
        stableCount = 0;
      }
      lastHeight = currentHeight;

      window.scrollBy(0, scrollStep);
      downScrolls++;

      // early exit if we're already at the bottom
      if (root.scrollTop + window.innerHeight >= currentHeight) {
        break;
      }

      await new Promise(r => setTimeout(r, 500));
    }
  } finally {
    done(downScrolls);
  }
}

/**
 * Scrolls back to the top of the page.
 *
 * This function is designed to be called with Selenium's `execute_async_script`.
 * @param {number} downScrolls - The number of times the page was scrolled down.
 * @param {number} scrollStepSize - The pixel size for each upward scroll step.
 */
async function scrollToPageTop() {
  const downScrolls = (arguments[0] ?? 0);
  const scrollStepSize = arguments[1] || 600;
  const done = arguments[arguments.length - 1];

  let upScrolls = 0;
  try {
    for (let i = 0; i < downScrolls && window.scrollY > 0; i++) {
      window.scrollBy(0, -scrollStepSize);
      upScrolls++;
      await new Promise(r => setTimeout(r, 50));
    }
    window.scrollTo(0, 0);
  } finally {
    done(upScrolls);
  }
}