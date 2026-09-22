/* Panel logic for node.html — kept OUT of the HTML on purpose.
 *
 * plugin_gui_server serves these pages with `script-src 'self'`, which
 * blocks inline <script>. An inline block therefore never executes in
 * the packaged app: the page renders its shell, no bridge call is made,
 * and the panel looks empty with nothing in the log. Keep panel code in
 * a .js file next to the page. */

// Per-node scope: config.set is denied by the host (use ui events to
// request the skill editor to persist). For Phase 3 the node-scope
// iframe is shown but only reads context to demonstrate the
// host_api_version contract; saving lands in a follow-on slice.
(async function init() {
  try {
    const ctx = await ecan.plugin.host.context();
    document.documentElement.setAttribute('data-theme', ctx.theme || 'light');
    document.getElementById('cooldown').value = 1500;
    const h = document.body.scrollHeight + 24;
    ecan.plugin.ui.resize(h);
  } catch (e) {
    document.body.innerHTML = '<p class="err">Bridge not available: ' + e.message + '</p>';
  }
})();
