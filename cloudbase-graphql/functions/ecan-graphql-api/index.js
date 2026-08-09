// Thin wrapper: cloudbaserc handler requires index.js -> exports.main.
// Main implementation lives at ./main.js (renamed from index.js to avoid the
// self-recursive require('./index.js'));
try {
  module.exports = require('./main.js');
} catch (e) {
  console.error('[ecan-graphql-api] FATAL load error:', e.message);
  console.error(e.stack);
  module.exports = {
    main: async () => ({
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        error: 'ecan-graphql-api load failed',
        message: e.message,
        stack: (e.stack || '').split('\n').slice(0, 5).join('\n'),
      }),
    }),
  };
}