/* Panel logic for status.html — kept OUT of the HTML on purpose.
 *
 * plugin_gui_server serves these pages with `script-src 'self'`, which
 * blocks inline <script>. An inline block therefore never executes in
 * the packaged app: the page renders its shell, no bridge call is made,
 * and the panel looks empty with nothing in the log. Keep panel code in
 * a .js file next to the page. */

(async function init() {
  try {
    const ctx = await ecan.plugin.host.context();
    document.documentElement.setAttribute('data-theme', ctx.theme || 'light');
    // Read a counter we maintain in storage — example only; the
    // hook's runtime state lives in StateStore, not here.
    const lastFire = await ecan.plugin.storage.get('last_fire_ts');
    const text = lastFire
      ? `last bypass: ${new Date(lastFire).toLocaleTimeString()}`
      : 'no events yet';
    document.getElementById('counts').textContent = text;
    ecan.plugin.ui.resize(72);
  } catch (e) {
    document.getElementById('text').textContent = 'bridge unavailable';
  }
})();
