/* ==========================================================================
   STMG 制作器 · 项目存储层
   · IndexedDB 存项目（文本存字符串，素材存 Blob，都不走 base64，省内存）
   · 手写 zip 读写：解开需要 deflate（DecompressionStream），打包一律 store
   · 没有任何第三方依赖
   ========================================================================== */
(function () {
  "use strict";

  var DB_NAME = "stmg-maker";
  var DB_VER = 1;
  var STORE = "projects";
  var META = "meta";

  var IMG_EXT = { png: 1, jpg: 1, jpeg: 1, webp: 1, bmp: 1, gif: 1, avif: 1 };
  var AUD_EXT = { ogg: 1, mp3: 1, wav: 1, opus: 1, m4a: 1, flac: 1, aac: 1 };
  var TXT_EXT = { stm: 1, py: 1, txt: 1, md: 1, json: 1, css: 1, js: 1, bat: 1, stmdec: 1 };

  function ext(p) {
    var m = /\.([^.\/]+)$/.exec(String(p || ""));
    return m ? m[1].toLowerCase() : "";
  }
  function kindOf(p) {
    var e = ext(p);
    if (e === "stm" || e === "stmdec") return "stm";
    if (e === "py") return "py";
    if (IMG_EXT[e]) return "img";
    if (AUD_EXT[e]) return "aud";
    if (TXT_EXT[e]) return "txt";
    return "bin";
  }
  function isAsset(p) {
    var k = kindOf(p);
    return k === "img" || k === "aud";
  }

  /* ==================== IndexedDB ==================== */
  var _db = null;
  function openDB() {
    if (_db) return Promise.resolve(_db);
    return new Promise(function (res, rej) {
      var rq;
      try { rq = indexedDB.open(DB_NAME, DB_VER); }
      catch (e) { rej(e); return; }
      rq.onupgradeneeded = function () {
        var db = rq.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "id" });
        if (!db.objectStoreNames.contains(META)) db.createObjectStore(META);
      };
      rq.onsuccess = function () { _db = rq.result; res(_db); };
      rq.onerror = function () { rej(rq.error || new Error("IndexedDB 打不开")); };
      rq.onblocked = function () { rej(new Error("IndexedDB 被别的标签页占着")); };
    });
  }

  function tx(store, mode) {
    return openDB().then(function (db) {
      return db.transaction(store, mode).objectStore(store);
    });
  }
  function req(r) {
    return new Promise(function (res, rej) {
      r.onsuccess = function () { res(r.result); };
      r.onerror = function () { rej(r.error); };
    });
  }

  var Store = {
    init: function () { return openDB().then(function () { return true; }); },

    list: function () {
      return tx(STORE, "readonly").then(function (s) { return req(s.getAll()); })
        .then(function (rows) {
          return (rows || []).map(function (r) {
            return { id: r.id, name: r.name, updated: r.updated,
                     files: Object.keys(r.files || {}).length };
          }).sort(function (a, b) { return (b.updated || 0) - (a.updated || 0); });
        });
    },

    load: function (id) {
      return tx(STORE, "readonly").then(function (s) { return req(s.get(id)); })
        .then(function (r) { return r || null; });
    },

    save: function (proj) {
      proj.updated = Date.now();
      return tx(STORE, "readwrite").then(function (s) { return req(s.put(proj)); });
    },

    remove: function (id) {
      return tx(STORE, "readwrite").then(function (s) { return req(s.delete(id)); });
    },

    getMeta: function (k, dflt) {
      return tx(META, "readonly").then(function (s) { return req(s.get(k)); })
        .then(function (v) { return v === undefined ? dflt : v; })
        .catch(function () { return dflt; });
    },
    setMeta: function (k, v) {
      return tx(META, "readwrite").then(function (s) { return req(s.put(v, k)); })
        .catch(function () {});
    }
  };

  /* ==================== CRC32 / zip 打包 ==================== */
  var CRC_TABLE = (function () {
    var t = new Uint32Array(256);
    for (var i = 0; i < 256; i++) {
      var c = i;
      for (var j = 0; j < 8; j++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[i] = c >>> 0;
    }
    return t;
  })();

  function crc32(buf) {
    var c = 0xFFFFFFFF;
    for (var i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  function dosTime(d) {
    var y = Math.max(1980, d.getFullYear());
    return {
      time: ((d.getHours() & 31) << 11) | ((d.getMinutes() & 63) << 5) | ((d.getSeconds() / 2) & 31),
      date: (((y - 1980) & 127) << 9) | (((d.getMonth() + 1) & 15) << 5) | (d.getDate() & 31)
    };
  }

  /* entries: [{name, data:Uint8Array}]  ->  Uint8Array（zip 二进制） */
  function makeZip(entries) {
    var enc = new TextEncoder();
    var now = dosTime(new Date());
    var chunks = [], central = [], offset = 0;

    entries.forEach(function (en) {
      var nameBuf = enc.encode(en.name.replace(/\\/g, "/"));
      var data = en.data instanceof Uint8Array ? en.data : new Uint8Array(en.data);
      var crc = crc32(data);

      var lh = new Uint8Array(30 + nameBuf.length);
      var dv = new DataView(lh.buffer);
      dv.setUint32(0, 0x04034b50, true);
      dv.setUint16(4, 20, true);            // version needed
      dv.setUint16(6, 0x0800, true);        // UTF-8 文件名
      dv.setUint16(8, 0, true);             // method = store
      dv.setUint16(10, now.time, true);
      dv.setUint16(12, now.date, true);
      dv.setUint32(14, crc, true);
      dv.setUint32(18, data.length, true);
      dv.setUint32(22, data.length, true);
      dv.setUint16(26, nameBuf.length, true);
      dv.setUint16(28, 0, true);
      lh.set(nameBuf, 30);
      chunks.push(lh, data);

      var ch = new Uint8Array(46 + nameBuf.length);
      var cv = new DataView(ch.buffer);
      cv.setUint32(0, 0x02014b50, true);
      cv.setUint16(4, 20, true);
      cv.setUint16(6, 20, true);
      cv.setUint16(8, 0x0800, true);
      cv.setUint16(10, 0, true);
      cv.setUint16(12, now.time, true);
      cv.setUint16(14, now.date, true);
      cv.setUint32(16, crc, true);
      cv.setUint32(20, data.length, true);
      cv.setUint32(24, data.length, true);
      cv.setUint16(28, nameBuf.length, true);
      cv.setUint32(42, offset, true);
      ch.set(nameBuf, 46);
      central.push(ch);

      offset += lh.length + data.length;
    });

    var cenSize = central.reduce(function (a, c) { return a + c.length; }, 0);
    var eocd = new Uint8Array(22);
    var ev = new DataView(eocd.buffer);
    ev.setUint32(0, 0x06054b50, true);
    ev.setUint16(8, entries.length, true);
    ev.setUint16(10, entries.length, true);
    ev.setUint32(12, cenSize, true);
    ev.setUint32(16, offset, true);

    var total = offset + cenSize + 22;
    var out = new Uint8Array(total);
    var p = 0;
    chunks.concat(central, [eocd]).forEach(function (c) { out.set(c, p); p += c.length; });
    return out;
  }

  /* ==================== zip 解包 ==================== */
  function u16(dv, o) { return dv.getUint16(o, true); }
  function u32(dv, o) { return dv.getUint32(o, true); }

  async function inflateRaw(bytes) {
    if (typeof DecompressionStream === "undefined")
      throw new Error("这个浏览器不支持解压 zip（缺少 DecompressionStream），请换新版 Chrome / Edge");
    var ds = new DecompressionStream("deflate-raw");
    var stream = new Blob([bytes]).stream().pipeThrough(ds);
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }

  /* 解 zip -> [{name, data:Uint8Array}] */
  async function readZip(buffer) {
    var buf = new Uint8Array(buffer);
    var dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
    // 从尾部往前找 EOCD
    var eocd = -1;
    for (var i = buf.length - 22; i >= 0 && i > buf.length - 66000; i--) {
      if (u32(dv, i) === 0x06054b50) { eocd = i; break; }
    }
    if (eocd < 0) throw new Error("不像 zip 文件（找不到目录结尾）");

    var count = u16(dv, eocd + 10);
    var cdOff = u32(dv, eocd + 16);
    var entries = [];
    var p = cdOff;

    for (var k = 0; k < count; k++) {
      if (u32(dv, p) !== 0x02014b50) break;
      var method = u16(dv, p + 10);
      var csize = u32(dv, p + 20);
      var nameLen = u16(dv, p + 28);
      var extraLen = u16(dv, p + 30);
      var cmtLen = u16(dv, p + 32);
      var lho = u32(dv, p + 42);
      var name = new TextDecoder("utf-8").decode(buf.subarray(p + 46, p + 46 + nameLen));

      var lnl = u16(dv, lho + 26);
      var lel = u16(dv, lho + 28);
      var dataOff = lho + 30 + lnl + lel;
      var raw = buf.subarray(dataOff, dataOff + csize);

      var data;
      if (method === 0) data = raw;
      else if (method === 8) data = await inflateRaw(raw);
      else throw new Error("不支持的压缩方式（method=" + method + "）：" + name);

      if (!/\/$/.test(name)) entries.push({ name: name, data: data });
      p += 46 + nameLen + extraLen + cmtLen;
    }
    return entries;
  }

  /* ==================== 项目对象 ==================== */
  function newId() {
    return "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }

  var TEMPLATE_BLANK = [
    '<',
    'Size=1280x720',
    'title="未命名剧本"',
    'Ver="1.0.0"',
    'Pack="com.example.stmg"',
    'Lang="cn"',
    'Font="Microsoft YaHei"',
    '>',
    '<',
    'Start:',
    '<-- 这是正文。台词写在引号里，缩进四格代表进分支 -->',
    '',
    '"故事从这里开始。"',
    '',
    '<-- 变量第一次出现要用 SET 定义 -->',
    'SET 好感度 = 0',
    '',
    '<-- 想加角色就写： 角色A"台词" -->',
    'S.character("角色A")',
    '角色A"你好，这是第一句台词。"',
    '',
    '<-- 选项：一行里每个引号串都是一个选项 -->',
    'Choose:',
    '    "继续"',
    '    "算了"',
    '',
    'If "继续":',
    '    SET 好感度 = 好感度 + 1',
    '    角色A"你选了继续，好感度 +1。"',
    '',
    'If "算了":',
    '    角色A"那就算了。"',
    '',
    'S.hide("all")',
    '"剧本到这里结束。点右上角「运行」随时看效果。"',
    '>',
    '<',
    '"感谢游玩"',
    '>'
  ].join("\n");

  var TEMPLATE_DEMO = [
    '<',
    'Size=1280x720',
    'title="我的第一个 STMG"',
    'Ver="1.0.0"',
    'Pack="com.example.demo"',
    'Lang="cn"',
    'Font="Microsoft YaHei"',
    '>',
    '<',
    'Start:',
    'S.character("小菲")',
    '',
    '"（演示：变量、选项、条件、立绘、音效各来一遍）"',
    '',
    'SET 好感度 = 0',
    '',
    '小菲"初次见面！你叫什么名字？"',
    'STM.Q = "请输入你的名字"',
    'Question:',
    '',
    '小菲"**" + STM.ANSWER + "**……我记住啦。"',
    '',
    'Choose:',
    '    "夸她可爱":"夸奖"',
    '    "装没听见":"冷场"',
    '',
    'If "夸奖":',
    '    SET 好感度 = 好感度 + 20',
    '    小菲"哼，算你有眼光喵。"',
    '',
    'If "冷场":',
    '    SET 好感度 = 好感度 - 10',
    '    小菲"……你是不是不会聊天。"',
    '',
    'If 好感度 >= 10:',
    '    "好感度到了 " + str(好感度) + "，她看起来挺高兴。"',
    'Else:',
    '    "气氛有点僵。"',
    '',
    'STM.display("演示结束：好感度 " + str(好感度))',
    '小菲"下次再来玩喵！"',
    '>',
    '<',
    '"- 完 -"',
    '>'
  ].join("\n");

  var TEMPLATE_OPTIONS = [
    '<',
    'About = "在这里写一句简介"',
    'Enc = "change-me-please"',
    'dec = "*.stm,*.png,*.jpg,*.mp3,*.wav,*.ogg"',
    'AllowNet = "false"',
    '>'
  ].join("\n");

  function blankProject(name, tpl) {
    var id = newId();
    return {
      id: id,
      name: name || "未命名项目",
      updated: Date.now(),
      files: {
        "script.stm": { type: "text", text: tpl === "demo" ? TEMPLATE_DEMO : TEMPLATE_BLANK },
        "options.stm": { type: "text", text: TEMPLATE_OPTIONS }
      }
    };
  }

  /* 从 zip 条目还原项目 */
  function projectFromEntries(entries, name) {
    var proj = { id: newId(), name: name || "导入的项目", updated: Date.now(), files: {} };
    var td = new TextDecoder("utf-8");
    var hasScript = false;

    entries.forEach(function (en) {
      var nm = en.name.replace(/\\/g, "/").replace(/^\.?\//, "");
      // 跳过 macOS 打包产生的垃圾
      if (!nm || nm.indexOf("__MACOSX/") === 0 || /(^|\/)\._/.test(nm)) return;
      if (/\/$/.test(nm)) return;

      var k = kindOf(nm);
      if (k === "text" || k === "txt" || k === "stm" || k === "py") {
        proj.files[nm] = { type: "text", text: td.decode(en.data) };
      } else {
        var type = "application/octet-stream";
        var e = ext(nm);
        if (e === "png") type = "image/png";
        else if (e === "jpg" || e === "jpeg") type = "image/jpeg";
        else if (e === "webp") type = "image/webp";
        else if (e === "gif") type = "image/gif";
        else if (e === "mp3") type = "audio/mpeg";
        else if (e === "ogg") type = "audio/ogg";
        else if (e === "wav") type = "audio/wav";
        else if (e === "m4a") type = "audio/mp4";
        else if (e === "flac") type = "audio/flac";
        proj.files[nm] = { type: "bin", blob: new Blob([en.data], { type: type }) };
      }
      if (/(^|\/)script(\.[a-z]{2,3})?\.stm$/.test(nm)) hasScript = true;
    });

    // 压缩包里只有一层目录（xxx/script.stm）时，把这层壳剥掉
    var names = Object.keys(proj.files);
    if (names.length) {
      var first = names[0].split("/");
      if (first.length > 1) {
        var root = first[0] + "/";
        var all = names.every(function (n) { return n.indexOf(root) === 0; });
        if (all) {
          var stripped = {};
          names.forEach(function (n) { stripped[n.slice(root.length)] = proj.files[n]; });
          proj.files = stripped;
          names = Object.keys(stripped);
          hasScript = names.some(function (n) { return /^script\.[a-z]{2,3}\.stm$/.test(n) || n === "script.stm"; });
        }
      }
    }

    if (!hasScript) {
      // 没有 script.stm 就当个新项目，把导入的东西塞进素材区，别让人一脸懵
      if (!proj.files["script.stm"])
        proj.files["script.stm"] = { type: "text", text: TEMPLATE_BLANK };
    }
    return proj;
  }

  /* 项目 -> zip 条目（网页版导出 / 项目包导出共用） */
  function projectEntries(proj) {
    var td = new TextEncoder();
    var list = [];
    Object.keys(proj.files).sort().forEach(function (p) {
      var f = proj.files[p];
      if (!f) return;
      if (f.type === "text") list.push({ name: p, data: td.encode(f.text || "") });
      else if (f.blob) list.push({ name: p, data: null, blob: f.blob });
    });
    return list;
  }

  /* 异步把 blob 转成 Uint8Array */
  async function materialize(entries) {
    var out = [];
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (e.data) out.push(e);
      else if (e.blob) out.push({ name: e.name, data: new Uint8Array(await e.blob.arrayBuffer()) });
    }
    return out;
  }

  function human(n) {
    var u = ["B", "KB", "MB", "GB"];
    var i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return (i === 0 ? n : n.toFixed(1)) + " " + u[i];
  }

  /* ==================== 对外 ==================== */
  window.STMGStore = Store;
  window.STMGFS = {
    kindOf: kindOf, isAsset: isAsset, ext: ext,
    makeZip: makeZip, readZip: readZip,
    newId: newId,
    blankProject: blankProject,
    projectFromEntries: projectFromEntries,
    projectEntries: projectEntries,
    materialize: materialize,
    human: human,
    TEMPLATE_BLANK: TEMPLATE_BLANK,
    TEMPLATE_DEMO: TEMPLATE_DEMO,
    TEMPLATE_OPTIONS: TEMPLATE_OPTIONS
  };
})();
