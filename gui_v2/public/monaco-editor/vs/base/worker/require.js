// AMD loader for Monaco Editor workers
(function(global) {
  var define = function(deps, callback) {
    if (typeof callback !== 'function') {
      callback = deps;
      deps = [];
    }
    var exports = {};
    var module = { exports: exports };
    callback(function(name) {
      return require(name);
    }, exports, module);
    return module.exports;
  };

  var require = function(name) {
    if (name === 'vs/base/worker/workerMain') {
      return self.MonacoWorker;
    }
    return self[name];
  };

  global.define = define;
  global.require = require;
})(self); 