/* Minimal luna client for web apps that do not ship webOSTV.js.
   Provides window.webOS.service.request(uri, {method, parameters, onSuccess,
   onFailure}) on top of the runtime's built-in PalmServiceBridge. */
(function () {
  "use strict";

  function makeRequest() {
    return function (uri, opts) {
      opts = opts || {};
      var bridge;
      try {
        bridge = new PalmServiceBridge();
      } catch (e) {
        if (opts.onFailure) opts.onFailure({ returnValue: false, errorText: "no PalmServiceBridge" });
        return null;
      }
      var settled = false;
      bridge.onservicecallback = function (msg) {
        if (settled) return;
        settled = true;
        var res;
        try { res = JSON.parse(msg) || {}; } catch (e) { res = { returnValue: false, errorText: "bad reply" }; }
        if (res.returnValue === false) {
          if (opts.onFailure) opts.onFailure(res);
        } else if (opts.onSuccess) {
          opts.onSuccess(res);
        }
        if (opts.onComplete) { try { opts.onComplete(res); } catch (e) {} }
      };
      try {
        bridge.call(String(uri), JSON.stringify(opts.parameters || {}));
      } catch (e) {
        settled = true;
        if (opts.onFailure) opts.onFailure({ returnValue: false, errorText: String(e) });
      }
      return { cancel: function () { try { bridge.cancel(); } catch (e) {} } };
    };
  }

  if (!window.webOS) window.webOS = {};
  if (!window.webOS.service) window.webOS.service = {};
  if (!window.webOS.service.request) window.webOS.service.request = makeRequest();
})();
