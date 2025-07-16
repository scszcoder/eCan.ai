


/**
 * Scrolls down the page in increments until the page height stabilizes,
 * ensuring all lazy-loaded content is triggered.
 *
 * This function is designed to be called with Selenium's `execute_async_script`.
 * It returns the number of downward scrolls performed via the callback.
 */
async function scrollToPageBottom() {
  const done = arguments[arguments.length - 1];
  const scrollStep = Math.round(window.innerHeight * 0.85);
  let downScrolls = 0;
  let lastHeight = -1;
  let stableCount = 0;
  const maxStableCount = 3; // Stop after 3 stable checks where height doesn't change

  while (stableCount < maxStableCount) {
    const currentHeight = document.body.scrollHeight;

    // Check if the page height has stopped changing
    if (currentHeight === lastHeight) {
      stableCount++;
    } else {
      stableCount = 0; // Reset counter if height changes
    }
    lastHeight = currentHeight;

    window.scrollBy(0, scrollStep);
    downScrolls++;

    // Wait for a moment to allow new content to load
    await new Promise(resolve => setTimeout(resolve, 500));

    // Break if we've reached the absolute bottom of the page
    if (window.innerHeight + window.scrollY >= document.body.scrollHeight) {
      break;
    }
  }

  // Return the number of scrolls performed to the Python callback
  done(downScrolls);
}

/**
 * Scrolls back to the top of the page.
 *
 * This function is designed to be called with Selenium's `execute_async_script`.
 * @param {number} downScrolls - The number of times the page was scrolled down.
 * @param {number} scrollStepSize - The pixel size for each upward scroll step.
 */
async function scrollToPageTop() {
  const downScrolls = arguments[0];
  const scrollStepSize = arguments[1] || 600; // Use provided step or a default
  const done = arguments[arguments.length - 1];

  let upScrolls = 0;
  for (let i = 0; i < downScrolls; i++) {
    if (window.scrollY === 0) break; // Check if we are already at the top

    window.scrollBy(0, -scrollStepSize);
    upScrolls++;

    // A short delay to make the scroll smooth
    await new Promise(resolve => setTimeout(resolve, 50));
  }

  // As a final measure, ensure we are exactly at the top
  window.scrollTo(0, 0);

  // Return the number of upward scrolls performed
  done(upScrolls);
}