/* ==========================================================================
   STMG 制作器 · 代码编辑器
   纯手写：高亮层 <pre> 叠在 <textarea> 底下，两边字体行高严格对齐。
   不引 CodeMirror / Monaco —— 整个制作器要能离线裸跑，多一个 CDN 就多一处白屏。

   对外：
     const ed = new STMGEditor(rootEl, {onChange, onCursor});
     ed.setValue(text) / ed.getValue() / ed.setLang("stm"|"py"|"text")
     ed.gotoLine(n) / ed.setMarkers([{line, level}]) / ed.focus()
     ed.findNext(q, opts) / ed.replaceRange(a, b, text)
   ========================================================================== */
(function () {
  "use strict";

  /* ---------------- 词法表 ---------------- */
  var STM_KW = {
    set: 1, if: 1, else: 1, elif: 1, endif: 1, endchoose: 1,
    choose: 1, question: 1, repeat: 1, while: 1, return: 1,
    call: 1, include: 1, start: 1
  };
  var NS = { s: 1, stm: 1, r: 1, stmg: 1, avg: 1 };
  var PY_KW = {};
  ("def class return if elif else for while in not and or import from as with "
    + "try except finally raise pass break continue lambda yield global nonlocal "
    + "None True False is del assert async await").split(" ")
    .forEach(function (k) { PY_KW[k] = 1; });
  var PY_FN = {};
  ("print len range str int float bool list dict set tuple sum min max abs round "
    + "sorted enumerate zip type isinstance format open repr map filter any all "
    + "getattr setattr hasattr join split strip replace math os json time random")
    .split(" ").forEach(function (k) { PY_FN[k] = 1; });

  var IDENT = /[A-Za-z_\u4e00-\u9fff]/;
  var IDENT2 = /[A-Za-z0-9_\u4e00-\u9fff]/;

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
  function span(cls, text) {
    return cls ? '<span class="' + cls + '">' + esc(text) + "</span>" : esc(text);
  }

  /* ---------------- 单行高亮：剧情 / Python ---------------- */
  function hlLine(line, mode) {
    var out = "", i = 0, n = line.length;
    while (i < n) {
      var c = line[i];

      // 注释：STMG 是 <-- -->，Python 是 #
      if (c === "<" && line.substr(i, 3) === "<--") {
        out += span("tok-com", line.slice(i)); break;
      }
      if (mode === "py" && c === "#") {
        out += span("tok-com", line.slice(i)); break;
      }

      // 字符串（不跨行；STMG 台词也走这里）
      if (c === '"' || c === "'") {
        var j = i + 1;
        while (j < n && line[j] !== c) { if (line[j] === "\\") j++; j++; }
        j = Math.min(n, j + 1);
        out += span("tok-str", line.slice(i, j));
        i = j; continue;
      }

      // 数字
      if (c >= "0" && c <= "9") {
        var k = i;
        while (k < n && /[0-9._]/.test(line[k])) k++;
        out += span("tok-num", line.slice(i, k));
        i = k; continue;
      }

      // 标识符（英文 / 中文都算）
      if (IDENT.test(c)) {
        var e = i;
        while (e < n && IDENT2.test(line[e])) e++;
        var w = line.slice(i, e);
        var low = w.toLowerCase();
        var prev = i > 0 ? line[i - 1] : "";
        var cls = "";

        if (mode === "py") {
          if (PY_KW[w]) cls = "tok-kw";
          else if (PY_FN[w]) cls = "tok-api";
          else if (prev === ".") cls = "tok-api";
        } else {
          var after = line[e];
          if (after === ":" && !prev) cls = "tok-tag";          // Start: 这种标签
          else if (STM_KW[low] && prev !== ".") cls = "tok-kw";
          else if (NS[low] && prev !== ".") cls = "tok-ns";
          else if (prev === ".") cls = "tok-api";
          else if (after === '"') cls = "tok-tag";              // 角色1"台词"
          else if (after === ":" && /^\s*$/.test(line.slice(0, i))) cls = "tok-tag";
        }
        out += span(cls, w);
        i = e; continue;
      }

      // 运算符 / 结构符
      if ("=<>+-*/%!&|,;:()[]{}".indexOf(c) >= 0) {
        out += span("tok-op", c); i++; continue;
      }

      out += esc(c); i++;
    }
    return out;
  }

  /* ---------------- 块内高亮：Key = "Value" ---------------- */
  function hlBlock(line) {
    var m = /^(\s*)([A-Za-z_]\w*)(\s*=\s*)(.*)$/.exec(line);
    if (m) {
      var v = m[4], vh;
      if (/^["']/.test(v)) vh = span("tok-str", v);
      else if (/^-?\d+(\.\d+)?$/.test(v.trim())) vh = span("tok-num", v);
      else vh = span("tok-var", v);
      return esc(m[1]) + span("tok-head", m[2]) + esc(m[3]) + vh;
    }
    if (/^\s*(python|py)\s*:/i.test(line))
      return span("tok-kw", line);
    return span("tok-op", line);
  }

  /* ---------------- 整篇高亮 ----------------
     按行分状态：
       code  普通剧情行
       block 头部 < ... > 里的键值
       py    <  python: N ... > 里的 Python 代码
       fence 分隔块用的单行 < 或 >                         */
  function highlight(src, lang) {
    if (lang === "text") return esc(src);
    var lines = String(src).split("\n");
    var out = [];
    var inBlock = false, isPy = false, pyStarted = false;

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i], t = line.trim();

      if (!inBlock) {
        if (/^<[A-Za-z]*$/.test(t)) {           // < 或 <Start
          inBlock = true; isPy = false; pyStarted = false;
          out.push(span("tok-op", line));
          continue;
        }
        out.push(hlLine(line, lang === "py" ? "py" : "stm"));
        continue;
      }

      // 在块里
      if (/^<\/?[A-Za-z]*>$/.test(t)) {          // 收块
        inBlock = false; isPy = false; pyStarted = false;
        out.push(span("tok-op", line));
        continue;
      }
      if (!pyStarted && /^\s*(python|py)\s*:/i.test(line)) {
        isPy = true; pyStarted = true;
        out.push(hlBlock(line));
        continue;
      }
      if (isPy) out.push(hlLine(line, "py"));
      else out.push(hlBlock(line));
    }
    return out.join("\n");
  }

  /* ====================================================================== */
  function STMGEditor(root, opts) {
    opts = opts || {};
    this.root = root;
    this.gutter = root.querySelector(".gutter");
    this.pre = root.querySelector(".highlight");
    this.ta = root.querySelector("#code");
    this.lang = "text";
    this.onChange = opts.onChange || function () {};
    this.onCursor = opts.onCursor || function () {};
    this.markers = {};
    this._gutterN = 0;
    this._raf = 0;
    this._lastVal = "";

    var inner = document.createElement("div");
    inner.className = "gutter-inner";
    this.gutter.textContent = "";
    this.gutter.appendChild(inner);
    this.gutterInner = inner;

    var self = this;
    this.ta.addEventListener("input", function () {
      self._queueRender();
      if (self.ta.value !== self._lastVal) {
        self._lastVal = self.ta.value;
        self.onChange(self.ta.value);
      }
    });
    this.ta.addEventListener("scroll", function () { self.syncScroll(); }, { passive: true });
    this.ta.addEventListener("keydown", function (e) { self._key(e); });
    this.ta.addEventListener("click", function () { self._cursor(); });
    this.ta.addEventListener("keyup", function () { self._cursor(); });
    document.addEventListener("selectionchange", function () {
      if (document.activeElement === self.ta) self._cursor();
    });
    this.ta.addEventListener("blur", function () { self._cursor(true); });
  }

  STMGEditor.prototype.setLang = function (lang) {
    this.lang = lang || "text";
    this.render();
  };

  STMGEditor.prototype.setValue = function (text) {
    this.ta.value = text == null ? "" : String(text);
    this._lastVal = this.ta.value;
    this.ta.scrollTop = 0; this.ta.scrollLeft = 0;
    try { this.ta.setSelectionRange(0, 0); } catch (e) {}
    this.render();
    this._cursor();
  };

  STMGEditor.prototype.getValue = function () { return this.ta.value; };

  STMGEditor.prototype.focus = function () { this.ta.focus(); };

  STMGEditor.prototype._queueRender = function () {
    var self = this;
    if (this._raf) return;
    this._raf = requestAnimationFrame(function () {
      self._raf = 0;
      self.render();
    });
  };

  STMGEditor.prototype.render = function () {
    var v = this.ta.value;
    this.pre.innerHTML = highlight(v, this.lang) + "\n";
    this._renderGutter(v.split("\n").length);
    this.syncScroll();
  };

  STMGEditor.prototype._renderGutter = function (n) {
    var g = this.gutterInner;
    while (g.childElementCount > n) g.removeChild(g.lastChild);
    while (g.childElementCount < n) {
      var d = document.createElement("div");
      d.className = "ln";
      g.appendChild(d);
    }
    for (var i = 0; i < n; i++) {
      var el = g.children[i];
      var no = i + 1;
      if (el.textContent !== String(no)) el.textContent = no;
      var mk = this.markers[no];
      var want = "ln" + (mk === "error" ? " err" : mk === "warn" ? " warn" : "");
      if (el.className !== want) el.className = want;
    }
    this._gutterN = n;
  };

  STMGEditor.prototype.syncScroll = function () {
    var x = this.ta.scrollLeft, y = this.ta.scrollTop;
    this.pre.style.transform = "translate(" + (-x) + "px," + (-y) + "px)";
    this.gutterInner.style.transform = "translateY(" + (-y) + "px)";
  };

  STMGEditor.prototype.setMarkers = function (list) {
    var m = {};
    (list || []).forEach(function (it) {
      var ln = it.line | 0;
      if (!ln) return;
      if (it.level === "error") m[ln] = "error";
      else if (!m[ln]) m[ln] = "warn";
    });
    this.markers = m;
    this._renderGutter(this.ta.value.split("\n").length);
  };

  /* ---------------- 光标 / 行列 ---------------- */
  STMGEditor.prototype._pos = function () {
    var v = this.ta.value, s = this.ta.selectionStart;
    var before = v.slice(0, s);
    var line = before.split("\n").length;
    var col = s - before.lastIndexOf("\n");
    return { line: line, col: col, start: s, end: this.ta.selectionEnd };
  };

  STMGEditor.prototype._cursor = function (blur) {
    var p = this._pos();
    // 当前行高亮
    if (this._curEl) this._curEl.classList.remove("cur");
    var el = this.gutterInner.children[p.line - 1];
    if (el && document.activeElement === this.ta) { el.classList.add("cur"); this._curEl = el; }
    this.onCursor(p, !!blur);
  };

  STMGEditor.prototype.gotoLine = function (n, col) {
    var lines = this.ta.value.split("\n");
    n = Math.max(1, Math.min(lines.length, n | 0));
    var idx = 0;
    for (var i = 0; i < n - 1; i++) idx += lines[i].length + 1;
    idx += (col ? Math.max(0, col - 1) : 0);
    this.ta.focus();
    this.ta.setSelectionRange(idx, idx);
    // 让目标行落在视野中间
    var lh = 21;
    this.ta.scrollTop = Math.max(0, (n - 1) * lh - this.ta.clientHeight / 2 + 40);
    this.syncScroll();
    this._cursor();
  };

  STMGEditor.prototype.setSelection = function (a, b) {
    this.ta.focus();
    this.ta.setSelectionRange(a, b);
    this._cursor();
  };

  STMGEditor.prototype.replaceRange = function (a, b, text) {
    var v = this.ta.value;
    this.ta.value = v.slice(0, a) + text + v.slice(b);
    this.ta.setSelectionRange(a + text.length, a + text.length);
    this._lastVal = this.ta.value;
    this.render();
    this.onChange(this.ta.value);
    this._cursor();
  };

  /* ---------------- 查找 ---------------- */
  STMGEditor.prototype.findNext = function (q, opt) {
    if (!q) return null;
    opt = opt || {};
    var v = this.ta.value;
    var from = opt.from != null ? opt.from : this.ta.selectionEnd;
    var hay = opt.caseSensitive ? v : v.toLowerCase();
    var needle = opt.caseSensitive ? q : q.toLowerCase();
    var i;
    if (opt.regex) {
      try {
        var re = new RegExp(q, opt.caseSensitive ? "g" : "gi");
        re.lastIndex = from;
        var m = re.exec(v);
        if (!m && opt.wrap !== false) { re.lastIndex = 0; m = re.exec(v); }
        if (!m) return null;
        i = m.index;
        this.setSelection(i, i + m[0].length);
        return i;
      } catch (e) { return null; }
    }
    i = hay.indexOf(needle, from);
    if (i < 0 && opt.wrap !== false) i = hay.indexOf(needle, 0);
    if (i < 0) return null;
    this.setSelection(i, i + q.length);
    return i;
  };

  /* ---------------- 键盘 ---------------- */
  STMGEditor.prototype._key = function (e) {
    var ta = this.ta;

    if (e.key === "Tab") {
      e.preventDefault();
      var s = ta.selectionStart, en = ta.selectionEnd, v = ta.value;
      if (s !== en && v.slice(s, en).indexOf("\n") >= 0) {
        this._indentBlock(!e.shiftKey);
      } else if (e.shiftKey) {
        this._outdentLine();
      } else {
        this.replaceRange(s, en, "    ");
      }
      return;
    }

    if (e.key === "Enter") {
      // 自动缩进：跟上一行对齐，If/Choose/Repeat/While 后面再加一级
      var p = this._pos();
      var lineStart = ta.value.lastIndexOf("\n", p.start - 1) + 1;
      var curLine = ta.value.slice(lineStart, p.start);
      var indent = (/^\s*/.exec(curLine) || [""])[0];
      if (/:\s*$/.test(curLine) && !/^\s*$/.test(curLine)) indent += "    ";
      e.preventDefault();
      this.replaceRange(p.start, p.end, "\n" + indent);
      return;
    }

    if (e.key === "Backspace" && ta.selectionStart === ta.selectionEnd) {
      // 4 空格缩进按一下退一级
      var pos = ta.selectionStart, val = ta.value;
      var ls = val.lastIndexOf("\n", pos - 1) + 1;
      var head = val.slice(ls, pos);
      if (head.length && /^ +$/.test(head) && head.length % 4 === 0) {
        e.preventDefault();
        this.replaceRange(pos - 4, pos, "");
        return;
      }
    }
  };

  STMGEditor.prototype._indentBlock = function (add) {
    var ta = this.ta, v = ta.value;
    var s = ta.selectionStart, e = ta.selectionEnd;
    var ls = v.lastIndexOf("\n", s - 1) + 1;
    var le = v.indexOf("\n", e);
    if (le < 0) le = v.length;
    var block = v.slice(ls, le);
    var out = block.split("\n").map(function (ln) {
      if (add) return "    " + ln;
      return ln.replace(/^ {1,4}/, "");
    }).join("\n");
    this.ta.value = v.slice(0, ls) + out + v.slice(le);
    ta.setSelectionRange(ls, ls + out.length);
    this._lastVal = ta.value;
    this.render();
    this.onChange(ta.value);
  };

  STMGEditor.prototype._outdentLine = function () {
    var ta = this.ta, v = ta.value, pos = ta.selectionStart;
    var ls = v.lastIndexOf("\n", pos - 1) + 1;
    var m = /^ {1,4}/.exec(v.slice(ls));
    if (!m) return;
    this.replaceRange(ls, ls + m[0].length, "");
  };

  /* ---------------- 导出 ---------------- */
  window.STMGEditor = STMGEditor;
  window.STMG_HL = { highlight: highlight, hlLine: hlLine, esc: esc };

})();
