/* ==========================================================================
   STMG 播放器（制作器预览 + 导出产物共用）

   两种运行模式，渲染逻辑完全一样：
     local   自己在页面里起 Pyodide 引擎（导出后的 index.html 用这个）
     remote  引擎在父窗口（制作器），这边只管画；靠 postMessage 一问一答

   对外：
     STMG_PLAYER.css       播放器样式（制作器塞进 iframe srcdoc）
     STMG_PLAYER.body      播放器的 DOM 结构
     STMG_PLAYER.boot(cfg) 启动
   ========================================================================== */
(function () {
  "use strict";

  /* ==================== 样式 ==================== */
  var CSS = [
    ':root{--accent:#7d8cff;--accent2:#ff8fc7;--ink:#eef0f7;--sub:#9aa0b5;',
    '--panel:rgba(16,18,26,.86);--stroke:rgba(255,255,255,.13);--radius:16px;',
    '--w:1280px;--h:720px;--box:26%;--fs:19px;--game-font:"Microsoft YaHei"}',
    '*{box-sizing:border-box;margin:0;padding:0}',
    'html,body{height:100%;overflow:hidden;background:#07080c;',
    'font-family:var(--game-font),system-ui,"Segoe UI",sans-serif;color:var(--ink)}',
    'body{-webkit-font-smoothing:antialiased}',
    'button{font-family:inherit;cursor:pointer;border:none;background:none;color:inherit}',
    '#app{position:fixed;inset:0;overflow:hidden}',
    '#stage{position:absolute;left:50%;top:50%;width:var(--w);height:var(--h);overflow:hidden;',
    'background:#0a0c12;box-shadow:0 30px 90px rgba(0,0,0,.7);border-radius:6px;',
    'transform-origin:center center;user-select:none}',
    '.layer{position:absolute;inset:0;background-size:cover;background-position:center;',
    'background-repeat:no-repeat;opacity:0;transition:opacity .25s ease}',
    '.layer.on{opacity:1}',
    '.ph{display:grid;place-items:center;text-align:center;padding:20px;white-space:pre-line;',
    'font-size:15px;color:rgba(255,255,255,.62);letter-spacing:.5px;',
    'text-shadow:0 1px 8px rgba(0,0,0,.5)}',
    '#spr-layer{position:absolute;inset:0;pointer-events:none}',
    '#l-avg{position:absolute;inset:0;pointer-events:none}',
    '.spr{position:absolute;bottom:0;height:88%;background-size:contain;',
    'background-position:bottom center;background-repeat:no-repeat;',
    'opacity:0;transition:opacity .28s ease;filter:drop-shadow(0 12px 30px rgba(0,0,0,.45))}',
    '.spr.on{opacity:1}',
    '.spr.left{left:2%}',
    '.spr.center{left:50%;transform:translateX(-50%)}',
    '.spr.right{right:2%}',
    '#dialogue{position:absolute;left:5.5%;right:5.5%;bottom:4%;min-height:var(--box);',
    'padding:30px 34px 26px;border-radius:var(--radius);',
    'background:linear-gradient(180deg,rgba(12,14,22,.84),rgba(12,14,22,.94));',
    'border:1px solid var(--stroke);backdrop-filter:blur(14px);',
    'box-shadow:0 22px 50px rgba(0,0,0,.5);',
    'opacity:0;transform:translateY(14px);transition:opacity .22s,transform .22s;',
    'pointer-events:none;display:flex;flex-direction:column}',
    '#dialogue.on{opacity:1;transform:none;pointer-events:auto;cursor:pointer}',
    '#namebox{position:absolute;top:-17px;left:28px;padding:7px 22px;border-radius:999px;',
    'font-size:19px;font-weight:700;letter-spacing:.6px;color:#fff;',
    'background:linear-gradient(135deg,var(--accent),var(--accent2));',
    'box-shadow:0 8px 20px rgba(0,0,0,.4);opacity:0;transition:opacity .18s}',
    '#namebox.on{opacity:1}',
    '#text{font-size:var(--fs);line-height:1.95;letter-spacing:.4px;',
    'word-break:break-word;white-space:pre-wrap;flex:1}',
    '#text .code{font-family:ui-monospace,Consolas,monospace;',
    'background:rgba(255,255,255,.1);padding:1px 6px;border-radius:5px;font-size:.92em}',
    '#hint{position:absolute;right:26px;bottom:14px;font-size:15px;color:var(--accent2);',
    'animation:bob 1.1s ease-in-out infinite;opacity:0;transition:opacity .2s}',
    '#hint.on{opacity:1}',
    '@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(5px)}}',
    '#ctrl{position:absolute;right:5.5%;bottom:calc(4% + var(--box) + 12px);display:flex;gap:8px;',
    'opacity:0;transition:opacity .2s}',
    '#ctrl.on{opacity:1}',
    '#ctrl button{padding:8px 15px;border-radius:10px;font-size:15px;color:var(--ink);',
    'background:rgba(12,14,22,.7);border:1px solid var(--stroke);backdrop-filter:blur(8px);',
    'transition:background .15s,transform .15s}',
    '#ctrl button:hover{background:rgba(125,140,255,.32);transform:translateY(-1px)}',
    '#ctrl button.act{background:linear-gradient(135deg,var(--accent),var(--accent2));border-color:transparent}',
    '.ov{position:absolute;inset:0;display:none;z-index:20}',
    '.ov.on{display:block}',
    '.mask{position:absolute;inset:0;background:rgba(4,5,9,.72);backdrop-filter:blur(6px)}',
    '#title{text-align:center}',
    '#title.on{display:grid;place-items:center}',
    '#title .bg{position:absolute;inset:0;',
    'background:radial-gradient(1200px 700px at 20% 10%,rgba(125,140,255,.3),transparent 60%),',
    'radial-gradient(900px 600px at 85% 90%,rgba(255,143,199,.26),transparent 60%),',
    'linear-gradient(160deg,#0b0d15,#131726 60%,#0a0b11)}',
    '#title .inner{position:relative;z-index:2}',
    '#title h1{font-size:72px;font-weight:800;letter-spacing:4px;',
    'background:linear-gradient(120deg,#fff,#c9d2ff 45%,#ffc3e2);',
    '-webkit-background-clip:text;background-clip:text;color:transparent;',
    'text-shadow:0 12px 40px rgba(0,0,0,.5)}',
    '#title .ver{margin-top:10px;font-size:16px;color:var(--sub);letter-spacing:2px}',
    '#title .menu{margin-top:46px;display:flex;flex-direction:column;gap:14px;align-items:center}',
    '#title .menu button{width:280px;padding:15px 0;border-radius:14px;font-size:19px;',
    'letter-spacing:3px;color:var(--ink);background:rgba(255,255,255,.06);',
    'border:1px solid var(--stroke);backdrop-filter:blur(10px);transition:all .18s}',
    '#title .menu button:hover{background:rgba(125,140,255,.3);transform:translateY(-2px)}',
    '#title .menu button.dim{opacity:.4;pointer-events:none}',
    '#engine-state{position:absolute;left:0;right:0;bottom:22px;font-size:13px;',
    'color:var(--sub);letter-spacing:.6px;padding:0 24px}',
    '#choose.on{display:grid;place-items:center}',
    '.choices{position:relative;z-index:2;display:flex;flex-direction:column;gap:16px;',
    'width:min(760px,74%);animation:pop .22s ease}',
    '@keyframes pop{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}',
    '.choices button{padding:20px 28px;border-radius:14px;font-size:21px;text-align:left;',
    'color:var(--ink);background:linear-gradient(135deg,rgba(28,32,48,.92),rgba(18,20,30,.92));',
    'border:1px solid var(--stroke);backdrop-filter:blur(10px);',
    'transition:all .16s;position:relative;overflow:hidden}',
    '.choices button:before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;',
    'background:linear-gradient(180deg,var(--accent),var(--accent2));opacity:0;transition:opacity .16s}',
    '.choices button:hover{transform:translateX(6px);border-color:rgba(125,140,255,.6)}',
    '.choices button:hover:before{opacity:1}',
    '#ask.on{display:grid;place-items:center}',
    '.askcard{position:relative;z-index:2;width:min(680px,72%);padding:30px;',
    'border-radius:var(--radius);background:var(--panel);border:1px solid var(--stroke);',
    'backdrop-filter:blur(14px);box-shadow:0 24px 60px rgba(0,0,0,.5);animation:pop .22s ease}',
    '.askcard p{font-size:20px;margin-bottom:18px;line-height:1.7}',
    '.askrow{display:flex;gap:12px}',
    '.askrow input{flex:1;padding:13px 15px;border-radius:12px;font-size:17px;color:var(--ink);',
    'background:rgba(255,255,255,.07);border:1px solid var(--stroke);outline:none}',
    '.askrow input:focus{border-color:var(--accent)}',
    '.askrow button{padding:13px 28px;border-radius:12px;font-size:16px;color:#fff;',
    'background:linear-gradient(135deg,var(--accent),var(--accent2))}',
    '.panel{position:absolute;inset:6% 8%;z-index:2;display:flex;flex-direction:column;',
    'border-radius:var(--radius);background:var(--panel);border:1px solid var(--stroke);',
    'backdrop-filter:blur(16px);box-shadow:0 24px 60px rgba(0,0,0,.55);animation:pop .2s ease}',
    '.panel h2{font-size:21px;padding:20px 24px 12px;letter-spacing:2px}',
    '.panel .body{flex:1;overflow-y:auto;padding:0 24px 10px}',
    '.panel .foot{padding:14px 24px 20px;display:flex;gap:12px;justify-content:flex-end}',
    '.btn{padding:10px 22px;border-radius:11px;font-size:15px;background:rgba(255,255,255,.08);',
    'border:1px solid var(--stroke);transition:all .15s}',
    '.btn:hover{background:rgba(125,140,255,.3)}',
    '.btn.pri{background:linear-gradient(135deg,var(--accent),var(--accent2));',
    'border-color:transparent;color:#fff}',
    '.hist-item{padding:10px 0;border-bottom:1px solid rgba(255,255,255,.07);line-height:1.7}',
    '.hist-item .who{color:var(--accent2);font-weight:700;margin-right:10px}',
    '.hist-item.narration{color:var(--sub)}',
    '.slots{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:13px}',
    '.slot{padding:15px;border-radius:13px;text-align:left;background:rgba(255,255,255,.05);',
    'border:1px solid var(--stroke);transition:all .15s;min-height:100px}',
    '.slot:hover{background:rgba(125,140,255,.22);transform:translateY(-2px)}',
    '.slot .n{font-size:13px;color:var(--accent2);letter-spacing:1px}',
    '.slot .t{font-size:12px;color:var(--sub);margin-top:7px;line-height:1.6}',
    '.slot .d{font-size:14px;margin-top:9px;line-height:1.6;overflow:hidden;',
    'display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}',
    '.slot.empty{opacity:.5}',
    '.field{display:flex;align-items:center;gap:15px;padding:13px 0}',
    '.field label{width:110px;font-size:15px;color:var(--sub)}',
    '.field input[type=range]{flex:1;accent-color:var(--accent)}',
    '.field .val{width:66px;text-align:right;font-size:14px;color:var(--sub)}',
    '.tip{padding:6px 0 12px;color:var(--sub);font-size:13px;line-height:1.8}',
    '#ending.on{display:grid;place-items:center;text-align:center}',
    '#ending .inner{position:relative;z-index:2}',
    '#ending h2{font-size:44px;letter-spacing:8px;margin-bottom:24px;',
    'background:linear-gradient(120deg,#fff,#c9d2ff,#ffc3e2);',
    '-webkit-background-clip:text;background-clip:text;color:transparent}',
    '#boot-mask{position:absolute;inset:0;z-index:60;display:none;place-items:center;',
    'background:rgba(6,8,13,.92);text-align:center;padding:40px}',
    '#boot-mask.on{display:grid}',
    '#boot-mask .bm-t{font-size:17px;letter-spacing:1px;margin-bottom:10px}',
    '#boot-mask .bm-s{font-size:13px;color:var(--sub);line-height:1.8;max-width:520px}',
    '#boot-mask .bar{width:280px;height:4px;border-radius:3px;background:#171b26;margin:18px auto 0;overflow:hidden}',
    '#boot-mask .bar i{display:block;height:100%;width:30%;border-radius:3px;',
    'background:linear-gradient(90deg,var(--accent),var(--accent2));animation:slide 1.2s infinite}',
    '@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(340%)}}',
    '::-webkit-scrollbar{width:9px}',
    '::-webkit-scrollbar-thumb{background:rgba(255,255,255,.16);border-radius:9px}',
    '::-webkit-scrollbar-track{background:transparent}'
  ].join("\n");

  /* ==================== DOM 结构 ==================== */
  var BODY = [
    '<div id="app"><div id="stage">',
    '  <div class="layer ph" id="l-bg"></div>',
    '  <div class="layer" id="l-pic"></div>',
    '  <div id="spr-layer"></div>',
    '  <canvas id="l-avg"></canvas>',
    '  <div id="dialogue">',
    '    <div id="namebox"></div>',
    '    <div id="text"></div>',
    '    <div id="hint">▼</div>',
    '  </div>',
    '  <div id="ctrl">',
    '    <button id="c-auto">自动</button>',
    '    <button id="c-skip">快进</button>',
    '    <button id="c-hist">历史</button>',
    '    <button id="c-save">存档</button>',
    '    <button id="c-load">读档</button>',
    '    <button id="c-cfg">设置</button>',
    '    <button id="c-full">全屏</button>',
    '  </div>',
    '  <div class="ov on" id="title">',
    '    <div class="bg"></div>',
    '    <div class="inner">',
    '      <h1 id="t-name">STMG</h1>',
    '      <div class="ver" id="t-ver"></div>',
    '      <div class="menu">',
    '        <button id="t-start">开始游戏</button>',
    '        <button id="t-continue">继续游戏</button>',
    '        <button id="t-load">读取存档</button>',
    '        <button id="t-cfg">设置</button>',
    '      </div>',
    '    </div>',
    '    <div id="engine-state"></div>',
    '  </div>',
    '  <div class="ov" id="choose">',
    '    <div class="mask"></div>',
    '    <div class="choices" id="choice-list"></div>',
    '  </div>',
    '  <div class="ov" id="ask">',
    '    <div class="mask"></div>',
    '    <div class="askcard">',
    '      <p id="ask-prompt"></p>',
    '      <div class="askrow">',
    '        <input id="ask-input" maxlength="40" autocomplete="off">',
    '        <button id="ask-ok">确定</button>',
    '      </div>',
    '    </div>',
    '  </div>',
    '  <div class="ov" id="history">',
    '    <div class="mask"></div>',
    '    <div class="panel">',
    '      <h2>历史记录</h2>',
    '      <div class="body" id="hist-body"></div>',
    '      <div class="foot"><button class="btn pri" data-close>关闭</button></div>',
    '    </div>',
    '  </div>',
    '  <div class="ov" id="slots">',
    '    <div class="mask"></div>',
    '    <div class="panel">',
    '      <h2 id="slots-title">存档</h2>',
    '      <div class="body"><div class="slots" id="slots-body"></div></div>',
    '      <div class="foot"><button class="btn" data-close>关闭</button></div>',
    '    </div>',
    '  </div>',
    '  <div class="ov" id="config">',
    '    <div class="mask"></div>',
    '    <div class="panel">',
    '      <h2>设置</h2>',
    '      <div class="body">',
    '        <div class="field"><label>文字速度</label>',
    '          <input type="range" id="s-speed" min="6" max="90" step="2">',
    '          <span class="val" id="v-speed"></span></div>',
    '        <div class="field"><label>BGM 音量</label>',
    '          <input type="range" id="s-bgm" min="0" max="100"><span class="val" id="v-bgm"></span></div>',
    '        <div class="field"><label>音效音量</label>',
    '          <input type="range" id="s-se" min="0" max="100"><span class="val" id="v-se"></span></div>',
    '        <div class="field"><label>语音音量</label>',
    '          <input type="range" id="s-voice" min="0" max="100"><span class="val" id="v-voice"></span></div>',
    '        <div class="field"><label>自动等待</label>',
    '          <input type="range" id="s-wait" min="600" max="4000" step="100">',
    '          <span class="val" id="v-wait"></span></div>',
    '        <div class="tip">空格 / 回车 / 点击推进 · Ctrl 快进 · A 自动 · H 历史 · F11 全屏</div>',
    '      </div>',
    '      <div class="foot">',
    '        <button class="btn" id="cfg-reset">清空存档数据</button>',
    '        <button class="btn pri" data-close>关闭</button>',
    '      </div>',
    '    </div>',
    '  </div>',
    '  <div class="ov" id="ending">',
    '    <div class="mask"></div>',
    '    <div class="inner">',
    '      <h2>END</h2>',
    '      <div style="display:flex;gap:14px;justify-content:center">',
    '        <button class="btn pri" id="e-restart">再来一次</button>',
    '        <button class="btn" id="e-title">回到标题</button>',
    '      </div>',
    '    </div>',
    '  </div>',
    '  <div id="boot-mask">',
    '    <div>',
    '      <div class="bm-t" id="bm-t">正在启动引擎</div>',
    '      <div class="bm-s" id="bm-s">第一次要下载约 10MB 的 WebAssembly 引擎</div>',
    '      <div class="bar"><i></i></div>',
    '    </div>',
    '  </div>',
    '</div></div>'
  ].join("\n");

  /* ==================== 小工具 ==================== */
  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function hashHue(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
    return h;
  }
  function placeholder(el, label, path) {
    var h = hashHue(path || label);
    el.style.background = "linear-gradient(135deg,hsl(" + h + ",45%,28%),hsl("
      + ((h + 60) % 360) + ",50%,18%))";
    el.classList.add("ph");
    el.textContent = label + "\n" + (path || "");
  }
  function isStrLit(s) {
    s = String(s).trim();
    return s.length >= 2 && s[0] === '"' && s[s.length - 1] === '"'
      && s.slice(1, -1).indexOf('"') < 0;
  }
  function stripQuotes(s) {
    s = String(s).trim();
    return (s.length >= 2 && s[0] === '"' && s[s.length - 1] === '"') ? s.slice(1, -1) : s;
  }

  /* ---------------- md 内联标记 ---------------- */
  var MD_RE = new RegExp([
    "\\[color=(#[0-9a-fA-F]{3,8}|[A-Za-z]+)\\]([\\s\\S]*?)\\[/color\\]",
    "\\[size=(\\d+)\\]([\\s\\S]*?)\\[/size\\]",
    "\\{(?:ruby|注音):([^|]+)\\|([^}]+)\\}",
    "\\*\\*([\\s\\S]+?)\\*\\*",
    "~~([\\s\\S]+?)~~",
    "`([^`]+)`",
    "(?<!\\*)\\*([^*]+)\\*(?!\\*)"
  ].join("|"), "g");

  function mdRuns(text) {
    var runs = [], s = String(text), pos = 0, m;
    MD_RE.lastIndex = 0;
    function push(t, extra) {
      if (t !== "" && t != null) runs.push(Object.assign({ t: t }, extra || {}));
    }
    while ((m = MD_RE.exec(s)) !== null) {
      if (m.index > pos) push(s.slice(pos, m.index));
      pos = MD_RE.lastIndex;
      if (m[1] != null) push(m[2], { color: m[1] });
      else if (m[3] != null) push(m[4], { size: parseInt(m[3], 10) });
      else if (m[5] != null) { push(m[5]); push("(" + m[6] + ")", { size: 11, color: "#8b93a8" }); }
      else if (m[7] != null) push(m[7], { bold: true });
      else if (m[8] != null) push(m[8], { strike: true });
      else if (m[9] != null) push(m[9], { code: true });
      else if (m[10] != null) push(m[10], { italic: true });
    }
    if (pos < s.length) push(s.slice(pos));
    return runs;
  }
  function runsHTML(runs, limit) {
    var left = (limit == null ? Infinity : limit), out = "";
    for (var i = 0; i < runs.length; i++) {
      var r = runs[i];
      if (left <= 0) break;
      var t = r.t;
      if (t.length > left) { t = t.slice(0, left); left = 0; } else left -= t.length;
      var h = esc(t);
      if (r.code) h = '<span class="code">' + h + "</span>";
      var st = [];
      if (r.bold) st.push("font-weight:700");
      if (r.italic) st.push("font-style:italic");
      if (r.strike) st.push("text-decoration:line-through");
      if (r.color) st.push("color:" + r.color);
      if (r.size) st.push("font-size:" + r.size + "px");
      if (st.length) h = '<span style="' + st.join(";") + '">' + h + "</span>";
      out += h;
    }
    return out;
  }
  function runsLen(runs) {
    var n = 0;
    for (var i = 0; i < runs.length; i++) n += runs[i].t.length;
    return n;
  }

  /* ==================== 运行时状态 ==================== */
  var CFG = null;                 // 启动配置
  var ASSETS = {};                // 素材路径 -> URL
  var ENGINE = null;
  var MODE = "title";
  var BUSY = false;
  var runs = [], shown = 0, typer = null;
  var HISTORY = [], SAYN = 0, ANSWERS = [], REPLAY = null;
  var AUTO = false, SKIP = false, autoTimer = null;
  var sprites = {}, picOn = null;
  var WAITING = false, WAIT_SKIP = false;
  var CFGSET = { speed: 42, bgm: 70, se: 80, voice: 90, wait: 1400 };
  var AUDIO = { bgm: null, se: null, voice: null };
  var NAME_COLORS = ["#ff88bb", "#7fb3ff", "#6fd6a8", "#ffc44d",
    "#c79bff", "#ff9d7a", "#5fc9d6"];
  var AVG_PRIM = ["box", "circle"];
  var avgShapes = [];
  var stage, elBg, elPic, elSpr, elDlg, elName, elText, elHint, elCtrl, elAvg;

  function assetUrl(p) {
    if (!p) return "";
    var k = String(p).replace(/\\/g, "/");
    if (ASSETS && ASSETS[k]) return ASSETS[k];
    return "assets/" + k;
  }

  /* ==================== 引擎 ==================== */
  function RemoteEngine() { this.done = false; this.waiting = null; }
  RemoteEngine.prototype.next = function (ans) {
    var self = this;
    if (this.done) return Promise.resolve(null);
    return new Promise(function (res) {
      self.waiting = res;
      parent.postMessage({
        __stmg: 1, type: "next",
        answer: ans === undefined ? null : ans
      }, "*");
    });
  };
  RemoteEngine.prototype._deliver = function (ev) {
    if (this.waiting) { var w = this.waiting; this.waiting = null; w(ev); }
  };
  RemoteEngine.prototype.stop = function () {
    this.done = true;
    if (this.waiting) { var w = this.waiting; this.waiting = null; w(null); }
  };

  function LocalEngine(driver) { this.d = driver; this.done = false; }
  LocalEngine.prototype.next = async function (ans) {
    if (this.done) return null;
    while (true) {
      var ev = this.d.next(ans);
      ans = undefined;
      if (ev === null) { this.done = true; return null; }
      if (ev.t === "api_pending") {
        var res = await apiFetch(ev);
        this.d.resolveApi(ev.n, res.ok, res.result);
        if (!res.ok) toast("R.api 没成功：" + res.why);
        continue;
      }
      var ch = this.d.vfsChanges();
      if (ch) VFS.apply(ch);
      return ev;
    }
  };
  LocalEngine.prototype.stop = function () { this.done = true; this.d.stop(); };

  /* ---------- R.api：真正的异步 fetch ---------- */
  async function apiFetch(req) {
    var url0 = String((req && req.url) || "");
    var key = String((req && req.key) || "");
    var timeout = Number((req && req.timeout) || 10000) || 10000;
    if (!url0) return { ok: false, result: null, why: "R.api 没写 url" };
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
      var why = (e && e.message === "TIMEOUT") ? ("超过 " + Math.round(timeout / 1000) + " 秒没响应")
        : String((e && e.message) || e);
      return { ok: false, result: null, why: why };
    } finally {
      if (timer) clearTimeout(timer);
      if (job && job.catch) job.catch(function () {});
    }
  }

  /* ---------- 沙箱文件系统（stm.os 用） ---------- */
  var VFS = (function () {
    var DB = "stmg-vfs", STORE = "files", KEY = "vfs";
    var fs = { files: {}, disabled: false, _db: null, _timer: null };
    function norm(p) {
      var s = String(p == null ? "" : p).trim().replace(/\\/g, "/");
      var i = s.toLowerCase().indexOf("stmg-virtual:");
      if (i >= 0) s = s.slice(i + 14);
      else if (s.length > 1 && s[1] === ":") s = s.slice(2);
      var out = [];
      s.split("/").forEach(function (seg) {
        seg = seg.trim();
        if (!seg || seg === ".") return;
        if (seg === "..") { out.pop(); return; }
        out.push(seg);
      });
      return out.join("/");
    }
    function openDb() {
      return new Promise(function (res, rej) {
        if (fs._db) return res(fs._db);
        var rq;
        try { rq = indexedDB.open(DB, 1); } catch (e) { return rej(e); }
        rq.onupgradeneeded = function () {
          var db = rq.result;
          if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
        };
        rq.onsuccess = function () { fs._db = rq.result; res(rq.result); };
        rq.onerror = function () { rej(rq.error); };
      });
    }
    function persist() {
      fs._timer = null;
      if (fs.disabled) return;
      openDb().then(function (db) {
        var tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(fs.files, KEY);
      }).catch(function () {});
    }
    function save() {
      if (fs.disabled) return;
      if (fs._timer) clearTimeout(fs._timer);
      fs._timer = setTimeout(persist, 250);
    }
    return {
      files: fs.files,
      get disabled() { return fs.disabled; },
      load: function () {
        return openDb().then(function (db) {
          return new Promise(function (res, rej) {
            var rq = db.transaction(STORE, "readonly").objectStore(STORE).get(KEY);
            rq.onsuccess = function () { res(rq.result || null); };
            rq.onerror = function () { rej(rq.error); };
          });
        }).then(function (d) {
          if (d && typeof d === "object") Object.assign(fs.files, d);
        }).catch(function () { fs.disabled = true; });
      },
      dump: function () { try { return JSON.stringify(fs.files); } catch (e) { return "{}"; } },
      apply: function (ch) {
        if (!ch) return;
        if (ch.set) Object.keys(ch.set).forEach(function (k) { fs.files[k] = ch.set[k]; });
        (ch.del || []).forEach(function (k) { delete fs.files[k]; });
        save();
      }
    };
  })();

  /* ==================== 舞台 ==================== */
  function fit() {
    if (!stage) return;
    var w = CFG.w, h = CFG.h;
    var iw = window.innerWidth, ih = window.innerHeight;
    var k = Math.min(iw / w, ih / h);
    // 先平移回容器中心，再缩放：transform 不影响布局尺寸，不这么做舞台会偏到右下
    stage.style.transform = "translate(-50%,-50%) scale(" + Math.max(0.1, Math.min(1, k)) + ")";
  }

  /* ==================== 设置 ==================== */
  function loadCfg() {
    try {
      var d = JSON.parse(localStorage.getItem(CFG.key + ":cfg") || "{}");
      Object.keys(d).forEach(function (k) { if (k in CFGSET) CFGSET[k] = d[k]; });
    } catch (e) {}
  }
  function saveCfg() {
    try { localStorage.setItem(CFG.key + ":cfg", JSON.stringify(CFGSET)); } catch (e) {}
  }
  function applyCfg() {
    var m = [["speed", "字/秒"], ["bgm", "%"], ["se", "%"], ["voice", "%"]];
    m.forEach(function (p) {
      var s = $("s-" + p[0]), v = $("v-" + p[0]);
      if (s) s.value = CFGSET[p[0]];
      if (v) v.textContent = CFGSET[p[0]] + " " + p[1];
    });
    var s = $("s-wait"), v = $("v-wait");
    if (s) s.value = CFGSET.wait;
    if (v) v.textContent = (CFGSET.wait / 1000).toFixed(1) + " 秒";
    if (AUDIO.bgm) AUDIO.bgm.volume = CFGSET.bgm / 100;
    if (AUDIO.se) AUDIO.se.volume = CFGSET.se / 100;
    if (AUDIO.voice) AUDIO.voice.volume = CFGSET.voice / 100;
  }

  /* ==================== 图层 ==================== */
  function setBg(path) {
    if (!path) {
      elBg.classList.remove("on"); elBg.style.backgroundImage = "";
      elBg.className = "layer ph"; elPic.classList.remove("on");
      elPic.style.backgroundImage = ""; clearSprites(); return;
    }
    var url = assetUrl(path);
    elBg.className = "layer"; elBg.textContent = "";
    var img = new Image();
    img.onload = function () {
      elBg.style.backgroundImage = "url('" + url + "')"; elBg.classList.add("on");
    };
    img.onerror = function () { placeholder(elBg, "背景缺失", path); elBg.classList.add("on"); };
    img.src = url;
    elPic.classList.remove("on"); elPic.style.backgroundImage = ""; picOn = null;
    clearSprites();
  }
  function setPic(path) {
    if (!path) { elPic.classList.remove("on"); elPic.style.backgroundImage = ""; picOn = null; return; }
    var url = assetUrl(path); picOn = path;
    elPic.classList.remove("ph"); elPic.textContent = "";
    var img = new Image();
    img.onload = function () {
      elPic.style.backgroundImage = "url('" + url + "')"; elPic.classList.add("on");
    };
    img.onerror = function () { placeholder(elPic, "贴图缺失", path); elPic.classList.add("on"); };
    img.src = url;
  }
  function setSprite(path, tag, pos) {
    var el = sprites[tag];
    if (!el) { el = document.createElement("div"); elSpr.appendChild(el); sprites[tag] = el; }
    el.className = "spr " + (["left", "center", "right"].indexOf(pos) >= 0 ? pos : "center");
    if (!path) { el.classList.remove("on"); return; }
    var url = assetUrl(path);
    var img = new Image();
    img.onload = function () { el.style.backgroundImage = "url('" + url + "')"; el.classList.add("on"); };
    img.onerror = function () {
      el.style.backgroundImage = "linear-gradient(180deg,hsla(" + hashHue(path)
        + ",45%,40%,.55),hsla(" + hashHue(path) + ",45%,18%,.85))";
      el.classList.add("on");
    };
    img.src = url;
  }
  function clearSprites() {
    Object.keys(sprites).forEach(function (k) { sprites[k].classList.remove("on"); });
  }

  /* ==================== AVG 绘图层 ==================== */
  function avgTurtle(ops, color, width) {
    var x = 0, y = 0, head = 0, pen = true;
    var cc = String(color || "#ffffff");
    var cw = Math.max(1, parseInt(width || 3, 10) || 3);
    var strokes = [], circles = [], cur = null;
    function lineTo(nx, ny) {
      if (pen) {
        if (!cur) { cur = { c: cc, w: cw, pts: [x, y] }; strokes.push(cur); }
        cur.pts.push(nx, ny);
      } else cur = null;
      x = nx; y = ny;
    }
    (ops || []).forEach(function (op) {
      var name = String(op[0] || "").toLowerCase();
      var arg = op.length > 1 ? op[1] : null;
      if (name === "go" || name === "back") {
        var d = Number(arg || 0); if (name === "back") d = -d;
        var rad = head * Math.PI / 180;
        lineTo(x + d * Math.cos(rad), y + d * Math.sin(rad));
      } else if (name === "left") head += Number(arg || 0);
      else if (name === "right") head -= Number(arg || 0);
      else if (name === "goto") { var p = arg || [0, 0]; lineTo(Number(p[0]) || 0, Number(p[1]) || 0); }
      else if (name === "up") { pen = false; cur = null; }
      else if (name === "down") pen = true;
      else if (name === "color") { cc = String(arg || "#ffffff"); cur = null; }
      else if (name === "width") { cw = Math.max(1, parseInt(arg || 3, 10) || 1); cur = null; }
      else if (name === "circle") circles.push({ c: cc, w: cw, cx: x, cy: y, r: Math.abs(Number(arg) || 10) });
    });
    return { strokes: strokes, circles: circles };
  }
  function avgGeom(item) {
    var name = String(item.shape || "").toLowerCase();
    var color = item.color || "#ffffff";
    var width = item.width != null ? item.width : 3;
    var size = item.size != null ? item.size : 64;
    if (name === "box") {
      var h = size / 2;
      return { strokes: [{ c: color, w: Math.max(1, width | 0),
        pts: [-h, -h, h, -h, h, h, -h, h, -h, -h] }], circles: [] };
    }
    if (name === "circle")
      return { strokes: [], circles: [{ c: color, w: Math.max(1, width | 0), cx: 0, cy: 0, r: size / 2 }] };
    return avgTurtle(item.ops || [], color, width);
  }
  function drawAvg() {
    if (!elAvg) return;
    var ctx = elAvg.getContext("2d");
    ctx.clearRect(0, 0, elAvg.width, elAvg.height);
    avgShapes.forEach(function (item) {
      var geo = avgGeom(item);
      var ox = elAvg.width / 2 + Number(item.x || 0);
      var oy = elAvg.height / 2 - Number(item.y || 0);
      ctx.lineCap = "round"; ctx.lineJoin = "round";
      geo.strokes.forEach(function (st) {
        var p = st.pts;
        if (p.length < 4) return;
        ctx.beginPath();
        ctx.moveTo(ox + p[0], oy - p[1]);
        for (var i = 2; i < p.length - 1; i += 2) ctx.lineTo(ox + p[i], oy - p[i + 1]);
        ctx.strokeStyle = st.c; ctx.lineWidth = Math.max(1, st.w | 0); ctx.stroke();
      });
      geo.circles.forEach(function (c) {
        ctx.beginPath();
        ctx.arc(ox + c.cx, oy - c.cy, Math.max(1, c.r), 0, Math.PI * 2);
        ctx.strokeStyle = c.c; ctx.lineWidth = Math.max(1, c.w | 0); ctx.stroke();
      });
    });
  }

  /* ==================== 音频 ==================== */
  function playAudio(kind, path, loop) {
    if (AUDIO[kind]) { AUDIO[kind].pause(); AUDIO[kind] = null; }
    if (!path) return;
    var a = new Audio(assetUrl(path));
    if (kind === "bgm") a.loop = loop !== false;
    a.volume = (kind === "bgm" ? CFGSET.bgm : kind === "voice" ? CFGSET.voice : CFGSET.se) / 100;
    a.play().catch(function () {});
    AUDIO[kind] = a;
  }
  function stopAudio(what) {
    if (what === "bgm" || what === "music" || what === "all") {
      if (AUDIO.bgm) { AUDIO.bgm.pause(); AUDIO.bgm = null; }
    }
    if (what === "sound" || what === "se" || what === "all") {
      if (AUDIO.se) { AUDIO.se.pause(); AUDIO.se = null; }
    }
    if (what === "voice" || what === "all") {
      if (AUDIO.voice) { AUDIO.voice.pause(); AUDIO.voice = null; }
    }
  }

  /* ==================== 提示 ==================== */
  var toastEl = null, toastTimer = null;
  function toast(text) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.style.cssText = "position:absolute;right:22px;top:22px;max-width:46%;z-index:30;"
        + "padding:11px 18px;border-radius:11px;font-size:15px;color:#eef0f7;"
        + "background:rgba(16,18,26,.9);border:1px solid rgba(255,255,255,.14);"
        + "backdrop-filter:blur(10px);transition:opacity .3s;pointer-events:none";
      stage.appendChild(toastEl);
    }
    toastEl.textContent = text;
    toastEl.style.opacity = "1";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.style.opacity = "0"; }, 2600);
  }

  function waitFor(ms) {
    return new Promise(function (res) {
      var t0 = Date.now();
      WAITING = true;
      var tick = setInterval(function () {
        if (WAIT_SKIP || Date.now() - t0 >= ms) {
          WAIT_SKIP = false; WAITING = false;
          clearInterval(tick); res();
        }
      }, 50);
    });
  }

  /* ==================== 事件应用 ==================== */
  function apply(ev) {
    switch (ev.t) {
      case "bg": setBg(ev.path); break;
      case "picture": setPic(ev.path); break;
      case "sprite": setSprite(ev.path, ev.tag, ev.pos); break;
      case "bgm": playAudio("bgm", ev.path, ev.loop); break;
      case "se": playAudio("se", ev.path); break;
      case "voice": playAudio("voice", ev.path); break;
      case "stop": stopAudio(ev.what); break;
      case "avg":
        if (ev.action === "clear") avgShapes = [];
        else avgShapes.push(ev);
        drawAvg();
        break;
      case "hide":
        if (ev.what === "sprite") clearSprites();
        else if (ev.what === "all") { clearSprites(); setPic(""); }
        else if (ev.what === "picture") setPic("");
        else if (sprites[ev.what]) sprites[ev.what].classList.remove("on");
        break;
      case "toast": toast(ev.text); break;
      default: break;
    }
  }

  /* ==================== 主循环 ==================== */
  async function pump(ans) {
    if (BUSY) return;
    BUSY = true;
    var guard = 0;
    try {
      while (true) {
        if (++guard > 300000) { toast("剧本可能死循环了，已停下"); finish(); return; }
        var ev = await ENGINE.next(ans);
        ans = undefined;
        if (!ev) { finish(); return; }
        if (ev.t === "end") { finish(); return; }
        if (ev.t === "fatal") { toast(ev.message || "剧本跑出错了"); finish(); return; }
        if (ev.t === "wait") { await waitFor((ev.dur || 3) * 1000); continue; }
        if (ev.t === "say") {
          SAYN++;
          HISTORY.push({ who: ev.who, text: ev.text });
          if (REPLAY) {
            if (SAYN < REPLAY.says) continue;
            REPLAY = null;
          }
          showSay(ev);
          return;
        }
        if (ev.t === "choose") {
          if (REPLAY && REPLAY.answers.length) { ans = REPLAY.answers.shift()[1]; continue; }
          showChoose(ev);
          return;
        }
        if (ev.t === "question") {
          if (REPLAY && REPLAY.answers.length) { ans = REPLAY.answers.shift()[1]; continue; }
          showAsk(ev);
          return;
        }
        apply(ev);
      }
    } catch (e) {
      toast("剧本跑出错了：" + String((e && e.message) || e));
      finish();
    } finally {
      BUSY = false;
    }
  }

  function showSay(ev) {
    MODE = "play";
    elDlg.classList.add("on");
    elCtrl.classList.add("on");
    elHint.classList.remove("on");
    if (ev.who) {
      elName.textContent = ev.who;
      var i = Math.max(0, NAME_COLORS.indexOf(ev.who));
      elName.style.background = "linear-gradient(135deg," + NAME_COLORS[i % NAME_COLORS.length]
        + ",rgba(255,255,255,.35))";
      elName.classList.add("on");
    } else elName.classList.remove("on");
    runs = mdRuns(ev.text);
    shown = 0;
    typeStep();
  }
  function typeStep() {
    clearTimeout(typer);
    var total = runsLen(runs);
    if (shown >= total) { onTyped(); return; }
    shown = Math.min(total, shown + Math.max(1, Math.round(CFGSET.speed / 24)));
    elText.innerHTML = runsHTML(runs, shown);
    typer = setTimeout(typeStep, 1000 / 24);
  }
  function onTyped() {
    elHint.classList.add("on");
    if (AUTO || SKIP) {
      clearTimeout(autoTimer);
      autoTimer = setTimeout(function () { if (AUTO || SKIP) advance(); }, SKIP ? 60 : CFGSET.wait);
    }
  }
  function isTyping() { return shown < runsLen(runs); }
  function advance() {
    if (WAITING) { WAIT_SKIP = true; return; }
    if (MODE !== "play" || BUSY) return;
    if (isTyping()) {
      shown = runsLen(runs);
      elText.innerHTML = runsHTML(runs, shown);
      onTyped();
      return;
    }
    clearTimeout(autoTimer);
    pump(undefined);
  }
  function showChoose(ev) {
    MODE = "choose";
    var box = $("choice-list");
    box.innerHTML = "";
    ev.options.forEach(function (o) {
      var b = document.createElement("button");
      b.innerHTML = runsHTML(mdRuns(o), null);
      b.onclick = function () {
        $("choose").classList.remove("on");
        MODE = "play";
        ANSWERS.push(["choose", o]);
        pump(o);
      };
      box.appendChild(b);
    });
    $("choose").classList.add("on");
  }
  function showAsk(ev) {
    MODE = "ask";
    $("ask-prompt").innerHTML = runsHTML(mdRuns(ev.prompt), null);
    var inp = $("ask-input");
    inp.value = "";
    $("ask").classList.add("on");
    setTimeout(function () { inp.focus(); }, 60);
  }
  function submitAsk() {
    var v = $("ask-input").value.trim();
    if (!v) return;
    $("ask").classList.remove("on");
    MODE = "play";
    ANSWERS.push(["question", v]);
    pump(v);
  }
  function finish() {
    MODE = "ending";
    elDlg.classList.remove("on");
    elHint.classList.remove("on");
    elCtrl.classList.remove("on");
    stopAudio("all");
    $("ending").classList.add("on");
  }

  /* ==================== 存档 ==================== */
  function slotKey(n) { return CFG.key + ":save:" + n; }
  function readSlot(n) {
    try { return JSON.parse(localStorage.getItem(slotKey(n)) || "null"); } catch (e) { return null; }
  }
  function writeSave(n) {
    var cur = HISTORY.length ? HISTORY[HISTORY.length - 1] : { text: "" };
    try {
      localStorage.setItem(slotKey(n), JSON.stringify({
        answers: ANSWERS.slice(), says: SAYN, time: Date.now(),
        snap: String(cur.text).slice(0, 60), who: cur.who || ""
      }));
    } catch (e) {}
  }
  function renderSlots(mode) {
    var box = $("slots-body");
    box.innerHTML = "";
    var list = mode === "save" ? [1, 2, 3, 4, 5, 6] : [0, 1, 2, 3, 4, 5, 6];
    list.forEach(function (i) {
      var d = readSlot(i);
      var b = document.createElement("button");
      b.className = "slot" + (d ? "" : " empty");
      var title = i === 0 ? "自动存档" : "存档 " + i;
      if (d) {
        b.innerHTML = '<div class="n">' + title + '</div><div class="t">'
          + new Date(d.time).toLocaleString("zh-CN") + '</div><div class="d">'
          + (d.who ? esc(d.who) + "：" : "") + esc(d.snap) + "</div>";
      } else {
        b.innerHTML = '<div class="n">' + title + '</div><div class="t">空</div><div class="d">—</div>';
      }
      b.onclick = function () {
        if (mode === "save") {
          if (MODE !== "play" && MODE !== "choose") return;
          writeSave(i); renderSlots("save"); toast("已存档到 " + title);
        } else {
          if (!d) { toast(title + " 是空的"); return; }
          loadSave(i);
        }
      };
      box.appendChild(b);
    });
  }
  function openSlots(mode) {
    $("slots-title").textContent = mode === "save" ? "存档" : "读档";
    renderSlots(mode);
    elsHide();
    $("slots").classList.add("on");
  }
  function elsHide() {
    ["history", "slots", "config", "choose", "ask"].forEach(function (k) {
      $(k).classList.remove("on");
    });
  }
  function openHistory() {
    var box = $("hist-body");
    box.innerHTML = HISTORY.map(function (h) {
      return '<div class="hist-item' + (h.who ? "" : " narration") + '">'
        + (h.who ? '<span class="who">' + esc(h.who) + "</span>" : "")
        + runsHTML(mdRuns(h.text), null) + "</div>";
    }).join("");
    elsHide();
    $("history").classList.add("on");
    box.scrollTop = box.scrollHeight;
  }

  /* ==================== 开局 / 读档 ==================== */
  function clearStage() {
    elText.innerHTML = "";
    elName.classList.remove("on");
    sprites = {}; elSpr.innerHTML = "";
    avgShapes = [];
    if (elAvg) elAvg.getContext("2d").clearRect(0, 0, elAvg.width, elAvg.height);
    elBg.style.backgroundImage = ""; elBg.className = "layer ph";
    elPic.style.backgroundImage = ""; elPic.className = "layer";
    HISTORY = []; SAYN = 0;
    $("ending").classList.remove("on");
    $("title").classList.remove("on");
    elsHide();
  }

  async function newEngine() {
    if (CFG.mode === "remote") {
      parent.postMessage({ __stmg: 1, type: "restart" }, "*");
      return new RemoteEngine();
    }
    var drv = STMG_ENGINE.createDriver(CFG.scriptText, CFG.optionsText);
    try {
      await VFS.load();
      drv.loadVfs(VFS.dump());
      if (VFS.disabled) drv.setVfsEnabled(false);
    } catch (e) {}
    return new LocalEngine(drv);
  }

  async function newGame() {
    clearStage();
    ANSWERS.length = 0;
    elText.innerHTML = "正在准备引擎…";
    elDlg.classList.add("on");
    MODE = "play";
    ENGINE = await newEngine();
    elText.innerHTML = "";
    REPLAY = null;
    pump(undefined);
  }
  async function loadSave(n) {
    var d = readSlot(n);
    if (!d) return;
    clearStage();
    ANSWERS.length = 0;
    elText.innerHTML = "正在读档…";
    elDlg.classList.add("on");
    MODE = "play";
    ENGINE = await newEngine();
    elText.innerHTML = "";
    REPLAY = { answers: d.answers.slice(), says: d.says };
    // 重放模式下先把答案灌进引擎：第一个 next 传 undefined，pump 遇到选择自己消费
    pump(undefined);
  }

  /* ==================== 事件绑定 ==================== */
  function bindUI() {
    elDlg.onclick = function () { if (MODE === "play") advance(); };
    stage.addEventListener("click", function (e) {
      if (MODE === "play" && !e.target.closest("#ctrl") && !e.target.closest(".ov")
        && !e.target.closest("#dialogue")) advance();
    });
    $("c-auto").onclick = function (e) {
      AUTO = !AUTO; e.currentTarget.classList.toggle("act", AUTO);
      if (AUTO) { SKIP = false; $("c-skip").classList.remove("act"); advance(); }
      else clearTimeout(autoTimer);
    };
    $("c-skip").onclick = function (e) {
      SKIP = !SKIP; e.currentTarget.classList.toggle("act", SKIP);
      if (SKIP) { AUTO = false; $("c-auto").classList.remove("act"); advance(); }
      else clearTimeout(autoTimer);
    };
    $("c-hist").onclick = openHistory;
    $("c-save").onclick = function () { elsHide(); openSlots("save"); };
    $("c-load").onclick = function () { elsHide(); openSlots("load"); };
    $("c-cfg").onclick = function () { elsHide(); applyCfg(); $("config").classList.add("on"); };
    $("c-full").onclick = toggleFull;
    $("t-start").onclick = function () { newGame(); };
    $("t-continue").onclick = function () {
      var d = readSlot(0);
      if (d) loadSave(0); else toast("还没有自动存档");
    };
    $("t-load").onclick = function () { elsHide(); openSlots("load"); };
    $("t-cfg").onclick = function () { elsHide(); applyCfg(); $("config").classList.add("on"); };
    $("ask-ok").onclick = submitAsk;
    $("ask-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") submitAsk();
    });
    $("e-restart").onclick = function () { newGame(); };
    $("e-title").onclick = function () {
      stopAudio("all"); elsHide(); $("ending").classList.remove("on");
      MODE = "title"; $("title").classList.add("on");
    };
    Array.prototype.forEach.call(document.querySelectorAll("[data-close]"), function (b) {
      b.onclick = function () {
        b.closest(".ov").classList.remove("on");
        if (MODE === "play") elDlg.classList.add("on");
      };
    });
    ["speed", "bgm", "se", "voice", "wait"].forEach(function (k) {
      $("s-" + k).addEventListener("input", function (e) {
        CFGSET[k] = parseInt(e.target.value, 10); applyCfg(); saveCfg();
      });
    });
    $("cfg-reset").onclick = function () {
      if (!confirm("清空这个游戏的所有存档和设置？")) return;
      for (var i = 0; i <= 6; i++) localStorage.removeItem(slotKey(i));
      localStorage.removeItem(CFG.key + ":cfg");
      toast("已清空");
    };
    document.addEventListener("keydown", function (e) {
      if (e.key === "F11") { e.preventDefault(); toggleFull(); return; }
      if (MODE === "ask") return;
      if (e.key === "Escape") {
        var open = document.querySelector(".ov.on:not(#title):not(#ending)");
        if (open) { elsHide(); if (MODE === "play") elDlg.classList.add("on"); }
        else if (MODE === "play") { elsHide(); applyCfg(); $("config").classList.add("on"); }
        return;
      }
      if (MODE !== "play") return;
      if (e.key === " " || e.key === "Enter") { e.preventDefault(); advance(); }
      else if (e.key === "a" || e.key === "A") {
        AUTO = !AUTO; $("c-auto").classList.toggle("act", AUTO); if (AUTO) advance();
      } else if (e.key === "h" || e.key === "H") openHistory();
      else if (e.key === "Control") { SKIP = true; $("c-skip").classList.add("act"); advance(); }
    });
    document.addEventListener("keyup", function (e) {
      if (e.key === "Control") { SKIP = false; $("c-skip").classList.remove("act"); }
    });
    window.addEventListener("beforeunload", function () { if (MODE === "play") writeSave(0); });
    window.addEventListener("resize", fit);
  }
  function toggleFull() {
    if (!document.fullscreenElement) { if (stage.requestFullscreen) stage.requestFullscreen(); }
    else document.exitFullscreen();
  }

  /* ==================== 远程模式的消息接收 ==================== */
  function bindRemote() {
    window.addEventListener("message", function (e) {
      var d = e.data;
      if (!d || d.__stmg !== 1) return;
      if (d.type === "event") {
        if (ENGINE && ENGINE._deliver) ENGINE._deliver(d.ev);
      } else if (d.type === "done") {
        if (ENGINE) { ENGINE.done = true; if (ENGINE._deliver) ENGINE._deliver(null); }
      } else if (d.type === "fatal") {
        if (ENGINE) {
          ENGINE.done = true;
          if (ENGINE._deliver) ENGINE._deliver({ t: "fatal", message: d.message });
        }
      } else if (d.type === "stop") {
        if (ENGINE && ENGINE.stop) ENGINE.stop();
        finish();
      }
    });
    // 告诉父窗口：DOM 就绪，可以派事件了
    parent.postMessage({ __stmg: 1, type: "ready" }, "*");
  }

  /* ==================== 启动 ==================== */
  async function boot(cfg) {
    CFG = Object.assign({
      title: "STMG", ver: "v1.0.0", w: 1280, h: 720,
      font: '"Microsoft YaHei"', box: 26, fs: 19,
      key: "stmg:project", mode: "local",
      scriptText: "", optionsText: "", assets: {},
      engineLabel: "WebAssembly 引擎"
    }, cfg || {});

    stage = $("stage");
    elBg = $("l-bg"); elPic = $("l-pic"); elSpr = $("spr-layer");
    elDlg = $("dialogue"); elName = $("namebox"); elText = $("text");
    elHint = $("hint"); elCtrl = $("ctrl"); elAvg = $("l-avg");

    // 尺寸 / 字体 / 对话框高度
    var root = document.documentElement;
    root.style.setProperty("--w", CFG.w + "px");
    root.style.setProperty("--h", CFG.h + "px");
    root.style.setProperty("--box", (CFG.box || 26) + "%");
    root.style.setProperty("--fs", (CFG.fs || 19) + "px");
    root.style.setProperty("--game-font", CFG.font || '"Microsoft YaHei"');
    elAvg.width = CFG.w; elAvg.height = CFG.h;

    ASSETS = CFG.assets || {};

    $("t-name").textContent = CFG.title || "STMG";
    $("t-ver").textContent = (CFG.ver || "") + " · " + (CFG.engineLabel || "");

    loadCfg(); applyCfg(); bindUI(); fit();

    if (CFG.mode === "remote") {
      bindRemote();
      $("engine-state").textContent = "引擎：制作器（实时预览）";
      // 制作器里点「运行」是要马上看到画面，不是先看标题页
      if (CFG.autostart !== false) setTimeout(function () { newGame(); }, 60);
      return;
    }

    // 本地模式：自己把引擎拉起来
    $("engine-state").textContent = "引擎：WebAssembly 预热中…";
    var mask = $("boot-mask");
    mask.classList.add("on");
    try {
      await STMG_ENGINE.boot(function (s) {
        $("bm-s").textContent = s;
      });
      mask.classList.remove("on");
      $("engine-state").textContent = "引擎：WebAssembly 就绪";
    } catch (e) {
      mask.classList.remove("on");
      $("engine-state").textContent = "引擎加载失败：" + String((e && e.message) || e).slice(0, 180);
      toast("引擎没起来，看看目录里有没有 pyodide/ 文件夹");
    }
  }

  /* ==================== 导出 ==================== */
  window.STMG_PLAYER = {
    css: CSS,
    body: BODY,
    boot: boot,
    /* 制作器用：拿到运行时状态给外层看 */
    stats: function () { return { events: HISTORY.length, mode: MODE }; }
  };
})();
