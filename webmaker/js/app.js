/* ==========================================================================
   STMG 制作器 · 主控
   把文件树 / 编辑器 / 引擎 / 预览 / 导出串成一个工作流。
   ========================================================================== */
(function () {
  "use strict";

  var FS = window.STMGFS;
  var Store = window.STMGStore;
  var Engine = window.STMG_ENGINE;
  var Exp = window.STMG_EXPORT;

  var $ = function (id) { return document.getElementById(id); };

  var state = {
    proj: null,
    tabs: [],
    active: null,
    dirty: false,
    check: null,
    checkTimer: 0,
    saveTimer: 0,
    driver: null,
    pumping: false,
    pendingAnswer: null,
    running: false,
    events: 0,
    unsub: null
  };

  var editor = null;

  /* ==================== 小工具 ==================== */
  function toast(text, bad) {
    var el = document.createElement("div");
    el.textContent = text;
    el.style.cssText = "position:fixed;left:50%;bottom:46px;transform:translateX(-50%) translateY(10px);"
      + "z-index:300;padding:10px 18px;border-radius:9px;font-size:13px;"
      + "background:" + (bad ? "#4a1c26" : "#1d2331") + ";border:1px solid "
      + (bad ? "#7a3040" : "#333c52") + ";color:" + (bad ? "#ffc0c8" : "#dfe4f2")
      + ";box-shadow:0 10px 30px rgba(0,0,0,.5);opacity:0;transition:.2s";
    document.body.appendChild(el);
    requestAnimationFrame(function () {
      el.style.opacity = "1"; el.style.transform = "translateX(-50%) translateY(0)";
    });
    setTimeout(function () {
      el.style.opacity = "0"; el.style.transform = "translateX(-50%) translateY(8px)";
      setTimeout(function () { el.remove(); }, 220);
    }, 2200);
  }

  function fmtBytes(n) { return FS.human(n || 0); }

  function fileName(p) { return String(p).split("/").pop(); }

  function langOf(p) {
    var k = FS.kindOf(p);
    if (k === "stm") return "stm";
    if (k === "py") return "py";
    return "text";
  }

  /* ==================== 模态框 ==================== */
  var modalOn = false;
  function openModal(opt) {
    $("modal-title").textContent = opt.title || "";
    var body = $("modal-body");
    body.innerHTML = "";
    if (typeof opt.body === "string") body.innerHTML = opt.body;
    else if (opt.body) body.appendChild(opt.body);

    var foot = $("modal-foot");
    foot.innerHTML = "";
    (opt.buttons || [{ label: "关闭" }]).forEach(function (b) {
      var el = document.createElement("button");
      el.className = "btn" + (b.primary ? " primary" : "");
      el.textContent = b.label;
      el.onclick = function () {
        if (!b.onClick || b.onClick() !== false) closeModal();
      };
      foot.appendChild(el);
    });
    $("modal").className = "modal" + (opt.wide ? " wide" : "");
    $("modal-mask").classList.add("on");
    modalOn = true;
  }
  function closeModal() {
    $("modal-mask").classList.remove("on");
    modalOn = false;
  }

  /* ==================== 项目 ==================== */
  function assetPaths() {
    return Object.keys(state.proj.files).filter(function (p) { return FS.isAsset(p); });
  }
  function assetBytes() {
    var n = 0;
    Object.keys(state.proj.files).forEach(function (p) {
      var f = state.proj.files[p];
      if (f && f.blob) n += f.blob.size;
    });
    return n;
  }

  function markDirty() {
    state.dirty = true;
    $("dirty-dot").classList.add("dirty");
    $("project-saved").textContent = "未保存";
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(saveNow, 900);
  }

  async function saveNow() {
    if (!state.proj) return;
    try {
      await Store.save(state.proj);
      state.dirty = false;
      $("dirty-dot").classList.remove("dirty");
      $("project-saved").textContent = "已保存";
    } catch (e) {
      $("project-saved").textContent = "保存失败";
      toast("保存失败：" + e.message, true);
    }
  }

  function setProject(proj) {
    state.proj = proj;
    state.tabs = [];
    state.active = null;
    state.check = null;
    state.driver = null;
    $("project-name").textContent = proj.name || "未命名项目";
    $("dirty-dot").classList.remove("dirty");
    $("project-saved").textContent = "已保存";

    // 默认打开 script.stm
    var first = proj.files["script.stm"] ? "script.stm"
      : Object.keys(proj.files).filter(function (p) { return FS.kindOf(p) === "stm"; })[0];
    if (first) openFile(first);

    renderTree();
    updateAssetStats();
    Store.setMeta("last", proj.id);
    Store.save(proj);

    // 切项目时把旧引擎停掉
    stopRun(true);
  }

  function updateAssetStats() {
    var n = assetPaths().length;
    $("asset-count").textContent = n + " 个素材";
    $("asset-size").textContent = fmtBytes(assetBytes());
    $("sb-assets").textContent = "素材：" + n + " 个 / " + fmtBytes(assetBytes());
  }

  /* ==================== 文件树 ==================== */
  function cmpFile(a, b) {
    var rank = function (p) {
      if (p === "script.stm") return 0;
      if (/^script\.[a-z]{2,3}\.stm$/.test(p)) return 1;
      if (p === "options.stm") return 2;
      if (p.indexOf("custom/") === 0) return 3;
      return 4;
    };
    var d = rank(a) - rank(b);
    return d !== 0 ? d : a.localeCompare(b, "zh");
  }

  function renderTree() {
    var box = $("tree");
    box.innerHTML = "";
    if (!state.proj) return;

    var files = Object.keys(state.proj.files).sort(cmpFile);
    var tree = { dirs: {}, files: [] };

    files.forEach(function (p) {
      var seg = p.split("/");
      var node = tree;
      for (var i = 0; i < seg.length - 1; i++) {
        if (!node.dirs[seg[i]]) node.dirs[seg[i]] = { dirs: {}, files: [] };
        node = node.dirs[seg[i]];
      }
      node.files.push(p);
    });

    var errLines = {};
    if (state.check && state.check.issues) {
      // 只对当前文件标红点（其它文件的错误在问题面板里看）
      state.check.issues.forEach(function (it) {
        if (it.level !== "error") return;
        errLines[state.active] = (errLines[state.active] || 0) + 1;
      });
    }

    function makeNode(path) {
      var k = FS.kindOf(path);
      var cls = k === "bin" ? "txt" : k;
      var letter = k === "stm" ? "S" : k === "py" ? "P"
        : k === "img" ? "I" : k === "aud" ? "A" : "T";
      var el = document.createElement("div");
      el.className = "node" + (state.active === path ? " active" : "");
      el.dataset.path = path;
      el.innerHTML = '<span class="ico ' + cls + '">' + letter + "</span>"
        + '<span class="nm">' + escapeHtml(fileName(path)) + "</span>";
      if (state.tabs.indexOf(path) >= 0 && isDirtyFile(path)) {
        el.insertAdjacentHTML("beforeend", '<span class="dot-dirty"></span>');
      }
      el.onclick = function () { openFile(path); };
      return el;
    }

    function walk(node, depth) {
      Object.keys(node.dirs).sort().forEach(function (name) {
        var dirEl = document.createElement("div");
        dirEl.className = "node dir-node";
        dirEl.style.paddingLeft = (6 + depth * 10) + "px";
        dirEl.textContent = name + "/";
        box.appendChild(dirEl);
        walk(node.dirs[name], depth + 1);
      });
      node.files.forEach(function (p) {
        var el = makeNode(p);
        el.style.paddingLeft = (6 + depth * 10) + "px";
        box.appendChild(el);
      });
    }
    walk(tree, 0);
  }

  function isDirtyFile() { return false; }   // 统一自动保存，不做逐文件脏标记

  /* ==================== 标签页 ==================== */
  function renderTabs() {
    var box = $("tabs");
    box.innerHTML = "";
    state.tabs.forEach(function (p) {
      var el = document.createElement("div");
      el.className = "tab" + (p === state.active ? " active" : "");
      el.innerHTML = '<span class="tname">' + escapeHtml(fileName(p)) + "</span>"
        + '<span class="tx" title="关闭">×</span>';
      el.onclick = function (e) {
        if (e.target.classList.contains("tx")) {
          closeTab(p);
          return;
        }
        openFile(p, true);
      };
      box.appendChild(el);
    });
  }

  function closeTab(p) {
    var i = state.tabs.indexOf(p);
    if (i < 0) return;
    state.tabs.splice(i, 1);
    if (state.active === p) {
      var next = state.tabs[Math.max(0, i - 1)];
      state.active = null;
      if (next) openFile(next, true);
      else showEditorEmpty();
    }
    renderTabs();
    renderTree();
  }

  function showEditorEmpty() {
    $("editor").hidden = true;
    $("editor-empty").classList.add("on");
    $("pos-info").textContent = "行 -，列 -";
  }

  /* ==================== 打开文件 ==================== */
  function openFile(path, keepScroll) {
    var f = state.proj.files[path];
    if (!f) return;
    var kind = FS.kindOf(path);

    if (kind === "img" || kind === "aud") {
      previewAsset(path);
      return;
    }

    if (state.tabs.indexOf(path) < 0) state.tabs.push(path);
    state.active = path;
    renderTabs();

    $("editor").hidden = false;
    $("editor-empty").classList.remove("on");
    $("file-lang").textContent = langOf(path) === "stm" ? "STMG 剧本"
      : langOf(path) === "py" ? "Python" : "纯文本";
    editor.setLang(langOf(path));
    editor.setValue(f.text || "");
    if (keepScroll) { /* 保持原样，不重置 */ }
    editor.focus();

    renderTree();
    updateGutterMarkers();
    $("sb-script").textContent = "剧本：" + path + " · " + editor.getValue().split("\n").length + " 行";
  }

  function previewAsset(path) {
    var f = state.proj.files[path];
    if (!f || !f.blob) return;
    var url = URL.createObjectURL(f.blob);
    var body = document.createElement("div");
    if (FS.kindOf(path) === "img") {
      var img = document.createElement("img");
      img.src = url;
      img.style.cssText = "max-width:100%;max-height:60vh;display:block;margin:0 auto;border-radius:8px";
      body.appendChild(img);
    } else {
      var au = document.createElement("audio");
      au.src = url; au.controls = true;
      au.style.cssText = "width:100%;margin:20px 0";
      body.appendChild(au);
    }
    var info = document.createElement("div");
    info.style.cssText = "font-size:12px;color:#6d7691;margin-top:14px;text-align:center";
    info.textContent = path + " · " + fmtBytes(f.blob.size);
    body.appendChild(info);
    openModal({
      title: fileName(path),
      body: body,
      buttons: [
        { label: "删除这个素材", onClick: function () { deleteFile(path); } },
        { label: "关闭", primary: true }
      ]
    });
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  /* ==================== 检查 ==================== */
  function scheduleCheck() {
    clearTimeout(state.checkTimer);
    state.checkTimer = setTimeout(doCheck, 800);
  }

  async function doCheck(force) {
    if (!state.proj) return null;
    var script = state.proj.files["script.stm"];
    if (!script) return null;

    setEngineBadge("busy", "检查中…");
    try {
      var res = await Engine.check(
        script.text || "",
        (state.proj.files["options.stm"] || {}).text || "",
        assetPaths()
      );
      state.check = res;
      renderIssues(res);
      updateGutterMarkers();
      updateCheckStatus(res);
      setEngineBadge("ready", "引擎就绪");
      return res;
    } catch (e) {
      setEngineBadge("bad", "引擎异常");
      renderIssues({
        fatal: String(e.message || e), issues: [], errors: 1,
        missing: [], unused: [], stats: {}
      });
      $("sb-check").className = "sb-item bad";
      $("sb-check").textContent = "引擎没起来";
      toast("引擎加载失败：" + String(e.message || e).slice(0, 90), true);
      return null;
    }
  }

  function updateCheckStatus(res) {
    var el = $("sb-check");
    if (!res) { el.className = "sb-item"; el.textContent = "未检查"; return; }
    if (res.fatal) {
      el.className = "sb-item bad";
      el.textContent = "解析失败";
      return;
    }
    var n = res.errors | 0;
    if (n === 0) {
      el.className = "sb-item ok";
      el.textContent = "体检通过 · " + (res.stats.say || 0) + " 句台词";
    } else {
      el.className = "sb-item bad";
      el.textContent = (res.level || "有错误") + " · " + n + " 个";
    }
  }

  function updateGutterMarkers() {
    if (!editor || !state.check) return;
    var list = (state.check.issues || []).slice();
    // 素材缺失当成提示，标记在最后一行
    editor.setMarkers(list);
  }

  function renderIssues(res) {
    var box = $("issues-body");
    var badge = $("issue-badge");
    box.innerHTML = "";

    var items = [];
    if (res && res.fatal) {
      items.push({ level: "error", line: 0, message: "解析器崩了：" + res.fatal, hint: "" });
    }
    if (res && res.issues) items = items.concat(res.issues);
    if (res && res.missing && res.missing.length) {
      items.push({
        level: "warn", line: 0,
        message: "缺 " + res.missing.length + " 个静态素材：" + res.missing.slice(0, 3).join("、")
          + (res.missing.length > 3 ? " 等" : ""),
        hint: "从左边上传，或者改剧本里的路径"
      });
    }
    if (res && res.options && res.options.issues) {
      items = items.concat(res.options.issues);
    }

    var errs = items.filter(function (i) { return i.level === "error"; }).length;
    badge.textContent = errs ? String(errs) : "0";

    if (!items.length) {
      box.innerHTML = '<div class="issue-ok">没有问题。剧本能跑，素材也都找到了。</div>';
      $("issues-title").textContent = "问题";
      return;
    }
    $("issues-title").textContent = "问题（" + errs + " 错误 / "
      + (items.length - errs) + " 提示）";

    items.forEach(function (it) {
      var row = document.createElement("div");
      row.className = "issue-row " + (it.level === "warn" ? "warn" : "error");
      row.innerHTML = '<span class="ilv">' + (it.level === "warn" ? "提示" : "错误") + "</span>"
        + '<span class="iwhere">' + (it.line ? "行 " + it.line : "全局") + "</span>"
        + '<span class="imsg">' + escapeHtml(it.message)
        + (it.hint ? '<span class="ihint"> — ' + escapeHtml(it.hint) + "</span>" : "")
        + "</span>";
      if (it.line) {
        row.onclick = function () {
          if (state.active !== "script.stm") openFile("script.stm");
          editor.gotoLine(it.line);
        };
      }
      box.appendChild(row);
    });
  }

  /* ==================== 引擎状态 ==================== */
  function setEngineBadge(kind, text) {
    var el = $("engine-badge");
    el.className = "engine-badge" + (kind ? " " + kind : "");
    $("engine-text").textContent = text;
    $("sb-engine").textContent = "引擎：" + text;
    $("sb-engine").className = "sb-item" + (kind === "ready" ? " ok"
      : kind === "bad" ? " bad" : kind === "busy" ? " warn" : "");
  }

  /* ==================== 运行预览 ==================== */
  async function apiFetch(req) {
    var url0 = String((req && req.url) || "");
    var key = String((req && req.key) || "");
    var timeout = Number((req && req.timeout) || 10000) || 10000;
    if (!url0) return { ok: false, result: null, why: "没写 url" };
    var url = /^https?:\/\//i.test(url0) ? url0 : ("http://" + url0);
    var opt = { method: "GET", headers: {} };
    if (key) opt.headers["Authorization"] = "Bearer " + key;
    var ctl = null, timer = null, job = null, guard = null;
    try {
      if (typeof AbortController === "function") {
        ctl = new AbortController(); opt.signal = ctl.signal;
      }
      job = fetch(url, opt);
      guard = new Promise(function (_, rej) {
        timer = setTimeout(function () { if (ctl) ctl.abort(); rej(new Error("TIMEOUT")); }, timeout);
      });
      var resp = await Promise.race([job, guard]);
      var text = await resp.text();
      if (resp.ok) return { ok: true, result: text, why: "" };
      return { ok: false, result: null, why: "HTTP " + resp.status };
    } catch (e) {
      return { ok: false, result: null, why: String((e && e.message) || e) };
    } finally {
      if (timer) clearTimeout(timer);
      if (job && job.catch) job.catch(function () {});
    }
  }

  function previewCfg() {
    var files = state.proj.files;
    var scriptText = (files["script.stm"] || {}).text || "";
    var optionsText = (files["options.stm"] || {}).text || "";

    var title = state.proj.name || "预览";
    var m = /title\s*=\s*"([^"]*)"/i.exec(scriptText);
    if (m) title = m[1];
    var size = /Size\s*=\s*(\d+)\s*[xX×]\s*(\d+)/.exec(scriptText);
    var font = /Font\s*=\s*"([^"]*)"/i.exec(scriptText);
    var ver = /Ver\s*=\s*"([^"]*)"/i.exec(scriptText);

    // custom/gui.py 的界面设置（正则抠，够用）
    var gui = (files["custom/gui.py"] || {}).text || "";
    var fs = null, box = null;
    var mfs = /text_size\s*["']?\s*\]?\s*=\s*([0-9.]+)/.exec(gui);
    if (mfs) fs = Math.round(parseFloat(mfs[1]) * 1.05);
    var mb = /box_h\s*["']?\s*\]?\s*=\s*([0-9.]+)/.exec(gui);
    if (mb) box = Math.round(parseFloat(mb[1]) * 100);

    var w = size ? parseInt(size[1], 10) : 1280;
    var h = size ? parseInt(size[2], 10) : 720;

    // 素材走 object URL，比 base64 快得多
    var assets = {};
    Object.keys(files).forEach(function (p) {
      var f = files[p];
      if (f && f.blob) assets[p] = URL.createObjectURL(f.blob);
    });

    return {
      title: title,
      ver: "v" + ((ver && ver[1]) || "1.0.0"),
      w: w, h: h,
      font: '"' + ((font && font[1]) || "Microsoft YaHei") + '"',
      box: box || 26,
      fs: fs || Math.max(16, Math.round(h * 0.028)),
      key: "stmg:preview:" + (state.proj.id || "x"),
      mode: "remote",
      engineLabel: "制作器实时预览",
      autostart: true,
      scriptText: scriptText,
      optionsText: optionsText,
      assets: assets
    };
  }

  function mountPreview() {
    var cfg = previewCfg();
    var doc = "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
      + "<base href=\"" + escapeHtml(location.href) + "\">"
      + "<style>" + window.STMG_PLAYER.css + "</style></head><body>"
      + window.STMG_PLAYER.body
      + "<script>window.STMG_CFG=" + JSON.stringify(cfg).replace(/</g, "\\u003c") + "<\/script>"
      + "<script src=\"js/player.js\"><\/script>"
      + "<script>STMG_PLAYER.boot(window.STMG_CFG);<\/script>"
      + "</body></html>";

    var pane = $("preview-pane");
    pane.classList.remove("collapsed");
    $("main").classList.remove("no-preview");
    $("preview-frame-wrap").classList.add("on");
    $("preview-empty").classList.add("hide");

    var ifr = $("preview");
    ifr.onload = function () { fitPreview(); };
    ifr.srcdoc = doc;

    $("preview-meta").textContent = cfg.w + "×" + cfg.h;
    $("preview-status").textContent = "运行中";
    $("preview-events").textContent = "0 条事件";
    state.events = 0;
  }

  async function run() {
    if (!state.proj) return;
    if (!state.proj.files["script.stm"]) {
      toast("先新建一个 script.stm", true);
      return;
    }
    await saveNow();

    $("btn-run").disabled = true;
    setEngineBadge("busy", "启动引擎…");

    var res = await doCheck();
    if (res && res.errors > 0) {
      toast("剧本还有 " + res.errors + " 个错误，先跑起来看看卡在哪", true);
    }

    try {
      await Engine.boot(function (s) { setEngineBadge("busy", s); });
    } catch (e) {
      setEngineBadge("bad", "引擎没起来");
      toast(String(e.message || e).slice(0, 120), true);
      $("btn-run").disabled = false;
      return;
    }

    createDriver();
    state.running = true;
    $("btn-stop").disabled = false;
    setEngineBadge("ready", "引擎就绪");
    mountPreview();
    $("btn-run").disabled = false;
    $("preview-pane").scrollIntoView({ block: "nearest" });
  }

  function createDriver() {
    var script = (state.proj.files["script.stm"] || {}).text || "";
    var options = (state.proj.files["options.stm"] || {}).text || "";
    state.driver = Engine.createDriver(script, options, "/game/script.stm");
    state.events = 0;
    state.pumping = false;
  }

  function postToPreview(msg) {
    var ifr = $("preview");
    if (ifr && ifr.contentWindow) {
      msg.__stmg = 1;
      ifr.contentWindow.postMessage(msg, "*");
    }
  }

  async function pump(answer) {
    if (!state.driver) return;
    if (state.pumping) { state.pendingAnswer = answer; return; }
    state.pumping = true;

    try {
      var a = answer, guard = 0;
      while (true) {
        if (++guard > 200000) {
          postToPreview({ type: "fatal", message: "剧本可能死循环了（事件超过 20 万条）" });
          break;
        }
        var ev = state.driver.next(a);
        a = undefined;

        if (ev === null) { postToPreview({ type: "done" }); break; }
        if (ev.t === "fatal") {
          postToPreview({ type: "fatal", message: ev.message });
          setEngineBadge("bad", "剧本跑出错");
          break;
        }
        if (ev.t === "api_pending") {
          var r = await apiFetch(ev);
          state.driver.resolveApi(ev.n, r.ok, r.result);
          if (!r.ok) console.warn("[预览] R.api 失败：" + r.why);
          continue;
        }

        var ch = state.driver.vfsChanges();
        if (ch) console.log("[预览] 沙箱文件变更", ch);

        state.events++;
        $("preview-events").textContent = state.events + " 条事件";
        postToPreview({ type: "event", ev: ev });
        break;
      }
    } catch (e) {
      postToPreview({ type: "fatal", message: String((e && e.message) || e) });
    } finally {
      state.pumping = false;
      if (state.pendingAnswer !== null && state.pendingAnswer !== undefined) {
        var na = state.pendingAnswer; state.pendingAnswer = null;
        setTimeout(function () { pump(na); }, 0);
      }
    }
  }

  function stopRun(silent) {
    if (state.driver) {
      try { state.driver.stop(); } catch (e) {}
      state.driver = null;
    }
    state.running = false;
    $("btn-stop").disabled = true;
    if (!silent) {
      postToPreview({ type: "stop" });
      $("preview-status").textContent = "已停止";
      toast("预览已停止");
    }
    // 释放素材 object URL
    Object.keys((state.proj && state.proj.files) || {}).forEach(function (p) {
      var f = state.proj.files[p];
      if (f && f.blob && f._url) { URL.revokeObjectURL(f._url); f._url = null; }
    });
  }

  function fitPreview() {
    var ifr = $("preview");
    var wrap = $("preview-frame-wrap");
    var mode = $("preview-size").value;
    var w = Number($("preview-meta").textContent.split("×")[0]) || 1280;
    var h = Number($("preview-meta").textContent.split("×")[1]) || 720;

    if (mode === "fit") {
      // 撑满容器，缩放由播放器内部的 fit() 处理（舞台等比居中）
      ifr.style.width = "100%";
      ifr.style.height = "100%";
      ifr.style.transform = "none";
    } else {
      var s = parseFloat(mode) || 1;
      ifr.style.width = w + "px";
      ifr.style.height = h + "px";
      ifr.style.transform = "scale(" + s + ")";
    }
  }

  /* ==================== 导入 / 导出 ==================== */
  function importFiles(fileList) {
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) return;

    // 单个 zip = 整个项目
    var zip = files.filter(function (f) { return /\.zip$/i.test(f.name); })[0];
    if (zip) { importZip(zip); return; }

    // 一堆文件 = 加进当前项目
    addFiles(files.map(function (f) {
      return { path: f.webkitRelativePath || f.name, file: f };
    }));
  }

  /* 拖进来的可能是整个文件夹：webkitGetAsEntry 递归把里面的文件全捞出来 */
  async function importDrop(dt) {
    var items = dt.items;
    var entries = [];
    if (items && items.length) {
      for (var i = 0; i < items.length; i++) {
        if (items[i].kind !== "file") continue;
        var en = items[i].webkitGetAsEntry && items[i].webkitGetAsEntry();
        if (en) entries.push(en);
      }
    }
    if (!entries.length) { importFiles(dt.files); return; }

    var got = [];
    for (var k = 0; k < entries.length; k++) await readEntry(entries[k], "", got);
    if (!got.length) { importFiles(dt.files); return; }

    // 拖进来的文件夹里只有一个 zip，那它就是个项目包
    if (got.length === 1 && /\.zip$/i.test(got[0].path)) {
      importZip(got[0].file);
      return;
    }
    addFiles(got);
  }

  function readEntry(entry, prefix, out) {
    return new Promise(function (res) {
      if (entry.isFile) {
        entry.file(function (f) {
          out.push({ path: prefix + entry.name, file: f });
          res();
        }, function () { res(); });
        return;
      }
      if (!entry.isDirectory) { res(); return; }
      var reader = entry.createReader();
      var all = [];
      var next = function () {
        // readEntries 一次最多回 100 条，要一直读到空为止
        reader.readEntries(function (batch) {
          if (!batch.length) {
            (async function () {
              for (var i = 0; i < all.length; i++) {
                await readEntry(all[i], prefix + entry.name + "/", out);
              }
              res();
            })();
            return;
          }
          all = all.concat(Array.prototype.slice.call(batch));
          next();
        }, function () { res(); });
      };
      next();
    });
  }

  async function importZip(file) {
    try {
      var buf = await file.arrayBuffer();
      var entries = await FS.readZip(buf);
      if (!entries.length) { toast("这个 zip 是空的", true); return; }
      var name = file.name.replace(/\.zip$/i, "");
      var proj = FS.projectFromEntries(entries, name);
      setProject(proj);
      await saveNow();
      toast("已导入 " + Object.keys(proj.files).length + " 个文件");
    } catch (e) {
      toast("导入失败：" + e.message, true);
    }
  }

  async function addFiles(items) {
    if (!state.proj) return;
    var n = 0;
    for (var i = 0; i < items.length; i++) {
      var rel = String(items[i].path || "").replace(/\\/g, "/").replace(/^\.?\//, "");
      var f = items[i].file;
      if (!rel || !f) continue;
      if (/\.(stm|py|txt|md|json|css|js|bat)$/i.test(rel)) {
        state.proj.files[rel] = { type: "text", text: await readText(f) };
      } else {
        state.proj.files[rel] = {
          type: "bin",
          blob: new Blob([f], { type: f.type || "application/octet-stream" })
        };
      }
      n++;
    }
    renderTree();
    updateAssetStats();
    markDirty();
    scheduleCheck();
    toast("加入 " + n + " 个文件");
  }

  function readText(file) {
    return new Promise(function (res, rej) {
      var fr = new FileReader();
      fr.onload = function () { res(String(fr.result || "")); };
      fr.onerror = rej;
      fr.readAsText(file, "utf-8");
    });
  }

  function download(blob, name) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 1000);
  }

  function exportDialog() {
    var body = document.createElement("div");
    body.innerHTML = [
      '<div class="field"><label>导出成什么</label></div>',
      '<div class="tpl-grid">',
      '  <button class="tpl sel" data-k="desktop"><div class="tname">桌面版（推荐）</div>',
      '    <div class="tdesc">解压双击「启动游戏.bat」就能玩，附 exe 打包脚本</div></button>',
      '  <button class="tpl" data-k="web"><div class="tname">网页版</div>',
      '    <div class="tdesc">index.html + assets + pyodide，丢 GitHub Pages 就能分享</div></button>',
      '  <button class="tpl" data-k="single"><div class="tname">单个 HTML</div>',
      '    <div class="tdesc">素材全内联，一个文件发给人；体积大，只适合小项目</div></button>',
      '  <button class="tpl" data-k="project"><div class="tname">项目源包</div>',
      '    <div class="tdesc">只有 .stm 和素材，给桌面版 STMG 仓库或做备份</div></button>',
      '</div>',
      '<div class="progress" style="display:none"><i></i></div>',
      '<div class="progress-text" id="exp-p"></div>'
    ].join("");

    var kind = "desktop";
    Array.prototype.forEach.call(body.querySelectorAll(".tpl"), function (b) {
      b.onclick = function () {
        Array.prototype.forEach.call(body.querySelectorAll(".tpl"), function (x) {
          x.classList.remove("sel");
        });
        b.classList.add("sel");
        kind = b.dataset.k;
      };
    });

    openModal({
      title: "导出项目",
      wide: true,
      body: body,
      buttons: [
        { label: "取消" },
        {
          label: "开始导出", primary: true,
          onClick: function () {
            doExport(kind, body);
            return false;   // 不关窗口，让它显示进度
          }
        }
      ]
    });
  }

  async function doExport(kind, body) {
    if (!state.proj) return;
    var bar = body.querySelector(".progress");
    var barIn = bar.querySelector("i");
    var txt = body.querySelector("#exp-p");
    bar.style.display = "block";

    function progress(s) {
      txt.textContent = s;
      var m = /(\d+)\/(\d+)/.exec(s);
      if (m) barIn.style.width = Math.round(parseInt(m[1], 10) / parseInt(m[2], 10) * 100) + "%";
      else barIn.style.width = "40%";
    }

    try {
      await saveNow();
      var out;
      if (kind === "project") {
        progress("打包项目文件…");
        out = await Exp.project(state.proj);
      } else if (kind === "web") {
        out = await Exp.web(state.proj, progress);
      } else if (kind === "single") {
        if (assetBytes() > 24 * 1024 * 1024) {
          toast("素材超过 24MB，单文件会很卡，建议用桌面版", true);
        }
        out = await Exp.singleHtml(state.proj, progress);
      } else {
        out = await Exp.desktop(state.proj, progress);
      }
      barIn.style.width = "100%";
      txt.textContent = "完成：" + out.name + (out.size ? "（" + fmtBytes(out.size) + "）" : "");
      download(out.blob, out.name);
      setTimeout(closeModal, 900);
    } catch (e) {
      txt.textContent = "失败：" + (e.message || e);
      toast("导出失败：" + (e.message || e), true);
    }
  }

  /* ==================== 新建项目 ==================== */
  function newDialog() {
    var body = document.createElement("div");
    body.innerHTML = [
      '<div class="field"><label>项目名</label>',
      '<input type="text" id="np-name" value="我的新剧本" maxlength="40"></div>',
      '<div class="field"><label>起手模板</label>',
      '<div class="tpl-grid">',
      '  <button class="tpl sel" data-t="blank"><div class="tname">空白</div>',
      '    <div class="tdesc">一句台词 + 一个选项，最短的可运行骨架</div></button>',
      '  <button class="tpl" data-t="demo"><div class="tname">演示剧本</div>',
      '    <div class="tdesc">变量、选项、条件、询问名字，各来一遍</div></button>',
      '</div></div>',
      '<div class="field"><label>已有项目</label>',
      '<div id="np-list" style="font-size:12px;color:#6d7691">读取中…</div></div>'
    ].join("");

    var tpl = "blank";
    Array.prototype.forEach.call(body.querySelectorAll(".tpl"), function (b) {
      b.onclick = function () {
        Array.prototype.forEach.call(body.querySelectorAll(".tpl"), function (x) {
          x.classList.remove("sel");
        });
        b.classList.add("sel");
        tpl = b.dataset.t;
      };
    });

    Store.list().then(function (rows) {
      var box = body.querySelector("#np-list");
      if (!rows.length) { box.textContent = "还没有保存过的项目"; return; }
      box.innerHTML = "";
      rows.slice(0, 8).forEach(function (r) {
        var b = document.createElement("button");
        b.className = "btn";
        b.style.margin = "0 6px 6px 0";
        b.textContent = r.name + "（" + r.files + " 个文件）";
        b.onclick = function () {
          Store.load(r.id).then(function (p) {
            if (p) { setProject(p); closeModal(); toast("已打开 " + p.name); }
          });
        };
        box.appendChild(b);
      });
    });

    openModal({
      title: "新建 / 打开项目",
      body: body,
      buttons: [
        { label: "取消" },
        {
          label: "创建", primary: true,
          onClick: function () {
            var name = (body.querySelector("#np-name").value || "").trim() || "未命名项目";
            var proj = FS.blankProject(name, tpl);
            setProject(proj);
            toast("已创建 " + name);
          }
        }
      ]
    });
  }

  function renameDialog() {
    var body = document.createElement("div");
    body.innerHTML = '<div class="field"><label>项目名</label>'
      + '<input type="text" id="rn-name" value="' + escapeHtml(state.proj.name || "") + '" maxlength="40"></div>';
    openModal({
      title: "重命名项目",
      body: body,
      buttons: [
        { label: "取消" },
        {
          label: "保存", primary: true,
          onClick: function () {
            var v = (body.querySelector("#rn-name").value || "").trim();
            if (!v) return false;
            state.proj.name = v;
            $("project-name").textContent = v;
            markDirty();
          }
        }
      ]
    });
  }

  /* ==================== 删除文件 ==================== */
  function deleteFile(path) {
    if (!path) return;
    var ok = confirm("删除「" + path + "」？\n（素材删了就没了，剧本可以从回收站外的备份恢复）");
    if (!ok) return;
    delete state.proj.files[path];
    state.tabs = state.tabs.filter(function (p) { return p !== path; });
    if (state.active === path) {
      state.active = null;
      if (state.tabs.length) openFile(state.tabs[0], true);
      else showEditorEmpty();
    }
    renderTabs(); renderTree(); updateAssetStats(); markDirty();
    scheduleCheck();
    closeModal();
    toast("已删除 " + path);
  }

  function newFileDialog() {
    var body = document.createElement("div");
    body.innerHTML = [
      '<div class="field"><label>文件路径</label>',
      '<input type="text" id="nf-path" placeholder="例如 script.en.stm 或 custom/gui.py"></div>',
      '<div class="field"><label>内容</label>',
      '<select id="nf-tpl">',
      '  <option value="empty">空文件</option>',
      '  <option value="scene">一段场景（带标签）</option>',
      '  <option value="options">options.stm 模板</option>',
      '</select></div>',
      '<div class="field"><div class="hint">素材请用上面的「上传」按钮，这里只建文本文件。</div></div>'
    ].join("");
    openModal({
      title: "新建文件",
      body: body,
      buttons: [
        { label: "取消" },
        {
          label: "创建", primary: true,
          onClick: function () {
            var p = (body.querySelector("#nf-path").value || "").trim().replace(/\\/g, "/");
            if (!p) { toast("路径不能为空", true); return false; }
            if (state.proj.files[p]) { toast("这个路径已经有了", true); return false; }
            var t = body.querySelector("#nf-tpl").value;
            var txt = "";
            if (t === "scene") {
              txt = '\n<-- 这一段可以用 include "文件名.stm" 插进主剧本 -->\n'
                + '"场景开始。"\n\n'
                + 'S.cg("bg/room.png")\n'
                + '角色A"这里是一句台词。"\n';
            } else if (t === "options") {
              txt = FS.TEMPLATE_OPTIONS;
            }
            state.proj.files[p] = { type: "text", text: txt };
            renderTree(); markDirty();
            openFile(p);
            toast("已创建 " + p);
          }
        }
      ]
    });
  }

  /* ==================== 查找条 ==================== */
  var findBar = null;
  function toggleFind() {
    if (!findBar) {
      findBar = document.createElement("div");
      findBar.className = "findbar";
      findBar.innerHTML = '<input id="fb-q" placeholder="查找">'
        + '<span class="fb-count" id="fb-n">0 / 0</span>'
        + '<input id="fb-r" class="replace" placeholder="替换为">'
        + '<button class="mini" id="fb-prev" title="上一个">↑</button>'
        + '<button class="mini" id="fb-next" title="下一个">↓</button>'
        + '<button class="mini" id="fb-rep" title="替换">换</button>'
        + '<button class="mini" id="fb-all" title="全部替换">全</button>'
        + '<button class="mini" id="fb-x" title="关闭">×</button>';
      $("editor-wrap").appendChild(findBar);

      var q = findBar.querySelector("#fb-q");
      q.addEventListener("input", countMatches);
      q.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); findNext(e.shiftKey ? -1 : 1); }
      });
      findBar.querySelector("#fb-next").onclick = function () { findNext(1); };
      findBar.querySelector("#fb-prev").onclick = function () { findNext(-1); };
      findBar.querySelector("#fb-x").onclick = function () { findBar.classList.remove("on"); editor.focus(); };
      findBar.querySelector("#fb-rep").onclick = function () {
        var sel = editor.getValue().slice(editor.ta.selectionStart, editor.ta.selectionEnd);
        var r = findBar.querySelector("#fb-r").value;
        if (!sel) { findNext(1); return; }
        editor.replaceRange(editor.ta.selectionStart, editor.ta.selectionEnd, r);
        countMatches();
      };
      findBar.querySelector("#fb-all").onclick = function () {
        var qv = findBar.querySelector("#fb-q").value;
        var rv = findBar.querySelector("#fb-r").value;
        if (!qv) return;
        var v = editor.getValue();
        var n = 0;
        while (v.indexOf(qv) >= 0) { v = v.replace(qv, rv); n++; if (n > 5000) break; }
        editor.setValue(v);
        editor.onChange(v);
        countMatches();
        toast("替换了 " + n + " 处");
      };
    }
    findBar.classList.toggle("on");
    if (findBar.classList.contains("on")) {
      var sel = editor.getValue().slice(editor.ta.selectionStart, editor.ta.selectionEnd);
      var q = findBar.querySelector("#fb-q");
      if (sel && sel.indexOf("\n") < 0) q.value = sel;
      q.focus(); q.select();
      countMatches();
    }
  }

  function countMatches() {
    var q = findBar.querySelector("#fb-q").value;
    var v = editor.getValue();
    if (!q) { findBar.querySelector("#fb-n").textContent = "0 / 0"; return; }
    var n = 0, i = 0;
    while ((i = v.indexOf(q, i)) >= 0) { n++; i += q.length; if (n > 9999) break; }
    findBar.querySelector("#fb-n").textContent = n + " 处";
  }

  function findNext(dir) {
    var q = findBar.querySelector("#fb-q").value;
    if (!q) return;
    if (dir < 0) {
      // 往前找：把起点挪到选区前面
      var from = Math.max(0, editor.ta.selectionStart - q.length - 1);
      var idx = editor.getValue().toLowerCase().lastIndexOf(q.toLowerCase(), from);
      if (idx < 0) idx = editor.getValue().toLowerCase().lastIndexOf(q.toLowerCase());
      if (idx >= 0) editor.setSelection(idx, idx + q.length);
    } else {
      editor.findNext(q, { from: editor.ta.selectionEnd });
    }
  }

  /* ==================== 拖放 ==================== */
  function bindDrop() {
    var veil = $("drop-veil");
    var depth = 0;
    document.addEventListener("dragenter", function (e) {
      if (!e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") < 0) return;
      e.preventDefault();
      depth++;
      veil.classList.add("on");
      $("drop-hint").classList.add("hot");
    });
    document.addEventListener("dragover", function (e) {
      if (e.dataTransfer) e.preventDefault();
    });
    document.addEventListener("dragleave", function () {
      depth = Math.max(0, depth - 1);
      if (depth === 0) { veil.classList.remove("on"); $("drop-hint").classList.remove("hot"); }
    });
    document.addEventListener("drop", function (e) {
      e.preventDefault();
      depth = 0;
      veil.classList.remove("on");
      $("drop-hint").classList.remove("hot");
      if (e.dataTransfer) importDrop(e.dataTransfer);
    });
  }

  /* ==================== 分隔条 ==================== */
  function bindSplits() {
    function drag(el, onMove) {
      el.addEventListener("mousedown", function (e) {
        e.preventDefault();
        el.classList.add("drag");
        var move = function (ev) { onMove(ev); };
        var up = function () {
          el.classList.remove("drag");
          document.removeEventListener("mousemove", move);
          document.removeEventListener("mouseup", up);
          document.body.style.cursor = "";
        };
        document.body.style.cursor = "col-resize";
        document.addEventListener("mousemove", move);
        document.addEventListener("mouseup", up);
      });
    }
    var main = $("main");
    drag($("vsplit-a"), function (e) {
      var w = Math.max(150, Math.min(420, e.clientX));
      main.style.setProperty("--side-w", w + "px");
    });
    drag($("vsplit-b"), function (e) {
      var total = main.clientWidth;
      var w = Math.max(260, Math.min(total - 320, total - e.clientX));
      main.style.setProperty("--preview-w", w + "px");
    });
  }

  /* ==================== 快捷键 ==================== */
  function bindKeys() {
    document.addEventListener("keydown", function (e) {
      var ctrl = e.ctrlKey || e.metaKey;
      if (ctrl && e.key.toLowerCase() === "s") {
        e.preventDefault(); saveNow(); toast("已保存");
      } else if (ctrl && e.key.toLowerCase() === "n") {
        e.preventDefault(); newDialog();
      } else if (ctrl && e.key.toLowerCase() === "o") {
        e.preventDefault(); $("file-input").click();
      } else if (ctrl && e.key.toLowerCase() === "f") {
        e.preventDefault(); toggleFind();
      } else if (ctrl && e.key.toLowerCase() === "b") {
        e.preventDefault(); doCheck();
      } else if (ctrl && e.key.toLowerCase() === "w") {
        e.preventDefault(); if (state.active) closeTab(state.active);
      } else if (e.key === "F5") {
        e.preventDefault();
        if (e.shiftKey) stopRun(); else run();
      } else if (e.key === "Escape") {
        if (modalOn) closeModal();
        else if (findBar && findBar.classList.contains("on")) findBar.classList.remove("on");
      }
    });
  }

  /* ==================== 初始化 ==================== */
  async function init() {
    editor = new window.STMGEditor($("editor"), {
      onChange: function (v) {
        if (!state.active) return;
        var f = state.proj.files[state.active];
        if (!f || f.type !== "text") return;
        f.text = v;
        markDirty();
        scheduleCheck();
      },
      onCursor: function (p) {
        $("pos-info").textContent = "行 " + p.line + "，列 " + p.col;
      }
    });

    bindDrop();
    bindSplits();
    bindKeys();

    $("btn-new").onclick = newDialog;
    $("btn-import").onclick = function () { $("file-input").click(); };
    $("btn-export").onclick = exportDialog;
    $("btn-check").onclick = doCheck;
    $("btn-run").onclick = run;
    $("btn-stop").onclick = function () { stopRun(); };
    $("btn-find").onclick = toggleFind;
    $("btn-new-file").onclick = newFileDialog;
    $("btn-del-file").onclick = function () { if (state.active) deleteFile(state.active); };
    $("btn-upload").onclick = function () { $("file-input").click(); };
    $("project-chip").onclick = renameDialog;
    $("modal-x").onclick = closeModal;
    $("modal-mask").onclick = function (e) {
      if (e.target === $("modal-mask")) closeModal();
    };
    $("issues").querySelector(".issues-head").onclick = function () {
      $("issues").classList.toggle("collapsed");
    };
    $("btn-issues-toggle").onclick = function () {
      $("issues").classList.toggle("collapsed");
    };
    $("btn-preview-close").onclick = function () {
      stopRun(true);
      $("preview-pane").classList.add("collapsed");
      $("main").classList.add("no-preview");
      $("preview-frame-wrap").classList.remove("on");
      $("preview-empty").classList.remove("hide");
      $("preview-status").textContent = "已收起";
    };
    $("btn-preview-full").onclick = function () {
      var pane = $("preview-pane");
      if (pane.classList.contains("collapsed")) {
        pane.classList.remove("collapsed");
        $("main").classList.remove("no-preview");
        $("preview-frame-wrap").classList.add("on");
        $("preview-empty").classList.add("hide");
      }
      pane.classList.toggle("theater");
      document.body.classList.toggle("theater-on", pane.classList.contains("theater"));
      setTimeout(fitPreview, 60);
    };
    $("preview-size").onchange = fitPreview;
    window.addEventListener("resize", function () {
      if ($("preview-frame-wrap").classList.contains("on")) fitPreview();
    });

    $("file-input").onchange = function (e) {
      importFiles(e.target.files);
      e.target.value = "";
    };

    // 预览消息
    window.addEventListener("message", function (e) {
      var d = e.data;
      if (!d || d.__stmg !== 1) return;
      if (d.type === "next") pump(d.answer);
      else if (d.type === "restart") {
        createDriver();
        $("preview-events").textContent = "0 条事件";
        $("preview-status").textContent = "运行中";
      } else if (d.type === "ready") {
        $("preview-status").textContent = "运行中";
      }
    });

    // 打字机/引擎日志别刷屏
    Engine.setLog(function () {});

    // 恢复上次的项目
    try {
      await Store.init();
      var last = await Store.getMeta("last", null);
      var proj = last ? await Store.load(last) : null;
      if (proj && proj.files && Object.keys(proj.files).length) {
        setProject(proj);
        toast("接着上次的项目：" + proj.name);
      } else {
        var p = FS.blankProject("我的第一个 STMG", "blank");
        setProject(p);
        toast("新建了一个空白项目，点「运行」先看看效果");
      }
    } catch (e) {
      var p2 = FS.blankProject("我的第一个 STMG", "blank");
      setProject(p2);
      toast("本地存储不可用（隐私模式？），改动不会保留", true);
    }

    // 后台预热引擎，第一次点运行就不用等
    setEngineBadge("busy", "引擎预热中…");
    Engine.boot(function (s) {
      setEngineBadge("busy", s.length > 22 ? s.slice(0, 22) + "…" : s);
    }).then(function () {
      setEngineBadge("ready", "引擎就绪");
      doCheck();
    }).catch(function (e) {
      setEngineBadge("bad", "引擎没起来");
      $("sb-check").className = "sb-item bad";
      $("sb-check").textContent = "引擎没起来";
      console.warn(e);
    });
  }

  // 排错用的入口：控制台里可以直接看状态、手动触发流程
  window.STMG_APP = {
    state: state,
    run: run,
    check: doCheck,
    save: saveNow,
    editor: function () { return editor; }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
