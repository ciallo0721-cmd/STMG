/* ==========================================================================
   STMG 制作器 · 引擎桥
   把 Pyodide（WebAssembly 里的 CPython）拉起来，装进 stmg 的源码，
   然后给上层两个能力：
       check(...)      语法体检（带行号，给编辑器画红点）
       createDriver()  真正跑剧本（事件流和桌面版同一套代码产出）
   制作器和导出的播放器共用这一份。
   ========================================================================== */
(function () {
  "use strict";

  var PYODIDE_BASE = window.STMG_PYODIDE_URL || "pyodide/";
  var SRC = window.STMG_ENGINE_SRC || {};

  var _py = null;          // Pyodide 实例
  var _bridges = null;     // {web_bridge, webtools}
  var _booting = null;
  var _fail = "";
  var _log = function () {};

  function loadScript(src) {
    return new Promise(function (res, rej) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = function () { res(); };
      s.onerror = function () { rej(new Error("加载失败：" + src)); };
      document.head.appendChild(s);
    });
  }

  function whyLocal() {
    return location.protocol === "file:"
      ? "浏览器不让 file:// 页面加载 WebAssembly 引擎。请在这个目录里起一个 http 服务"
        + "（python -m http.server 8000），再访问 http://localhost:8000/"
      : "";
  }

  /* ---------------- 启动 ---------------- */
  function boot(onStage) {
    if (_bridges) return Promise.resolve(_bridges);
    if (_booting) return _booting;

    var stage = onStage || function () {};

    _booting = (async function () {
      try {
        var base = new URL(PYODIDE_BASE, location.href).href;
        stage("加载引擎加载器…");
        if (typeof window.loadPyodide !== "function") {
          await loadScript(base + "pyodide.js");
        }

        stage("解压 WebAssembly 引擎（第一次约 10MB）…");
        var py = await loadPyodide({
          indexURL: base,
          stdout: function (s) { _log(s); },
          stderr: function (s) { _log(s); }
        });

        stage("装载 STMG 引擎源码…");
        var keys = Object.keys(SRC);
        if (!keys.length) throw new Error("引擎源码没打包进来（js/engine-src.js 是空的）");

        Object.keys(SRC).forEach(function (p) {
          var dir = p.split("/").slice(0, -1).join("/");
          if (dir) {
            try { py.FS.mkdirTree(dir); } catch (e) { /* 已存在 */ }
          }
          py.FS.writeFile(p, SRC[p], { encoding: "utf8" });
        });

        py.runPython(
          "import sys\n" +
          "if '/stmg_root' not in sys.path:\n" +
          "    sys.path.insert(0, '/stmg_root')\n"
        );

        stage("初始化解析器…");
        var wb = py.pyimport("stmg.web_bridge");
        var wt = py.pyimport("stmg.webtools");

        _py = py;
        _bridges = { web_bridge: wb, webtools: wt };
        stage("引擎就绪");
        return _bridges;
      } catch (e) {
        _fail = String((e && e.message) || e) + " " + whyLocal();
        _booting = null;
        throw new Error(_fail);
      }
    })();

    return _booting;
  }

  /* ---------------- 语法体检 ---------------- */
  async function check(scriptText, optionsText, assetPaths) {
    var b = await boot();
    var raw = b.webtools.check(
      String(scriptText == null ? "" : scriptText),
      String(optionsText == null ? "" : optionsText),
      JSON.stringify(assetPaths || [])
    );
    try { return JSON.parse(String(raw)); }
    catch (e) { return { ok: false, fatal: "引擎返回的不是 JSON：" + String(raw).slice(0, 200) }; }
  }

  /* ---------------- 语句树（导出 --engine js 用） ---------------- */
  async function ast(scriptText) {
    var b = await boot();
    var raw = String(b.webtools.ast(String(scriptText || "")));
    return raw && raw !== "null" ? raw : null;
  }

  /* ---------------- 运行驱动 ---------------- */
  function createDriver(scriptText, optionsText, scriptPath) {
    if (!_bridges) throw new Error("引擎还没启动");
    var d = _bridges.web_bridge.Driver(
      String(scriptText || ""), String(optionsText || ""),
      scriptPath || "/game/script.stm"
    );
    var done = false;
    return {
      /* 拿下一个事件（对象）；跑完返回 null */
      next: function (answer) {
        if (done) return null;
        var raw;
        try { raw = String(d.next(answer === undefined ? null : answer)); }
        catch (e) { done = true; return { t: "fatal", message: String((e && e.message) || e) }; }
        var ev;
        try { ev = JSON.parse(raw); }
        catch (e) { done = true; return { t: "fatal", message: "引擎输出坏了：" + raw.slice(0, 160) }; }
        if (!ev || ev.t === "__done__") { done = true; return null; }
        return ev;
      },
      vfsChanges: function () {
        try { return JSON.parse(String(d.vfs_changes())); } catch (e) { return null; }
      },
      resolveApi: function (n, ok, result) {
        try { d.resolve_api(n, !!ok, result == null ? "" : String(result)); } catch (e) {}
      },
      loadVfs: function (text) {
        try { d.load_vfs(String(text || "{}")); } catch (e) {}
      },
      setVfsEnabled: function (flag) {
        try { d.set_vfs_enabled(!!flag); } catch (e) {}
      },
      info: function () {
        try { return JSON.parse(String(d.info())); } catch (e) { return {}; }
      },
      stop: function () { done = true; }
    };
  }

  window.STMG_ENGINE = {
    boot: boot,
    check: check,
    ast: ast,
    createDriver: createDriver,
    get ready() { return !!_bridges; },
    get failed() { return _fail; },
    setLog: function (fn) { _log = fn || function () {}; }
  };
})();
