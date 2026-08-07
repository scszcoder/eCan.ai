// Thin wrapper: cloudbaserc handler requires index.js -> exports.main.
// Real implementation lives at the project root so dev and prod share one source.
module.exports = require('../../index.js');