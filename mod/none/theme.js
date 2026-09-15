/* ==========================================================================
   网页版行为 —— 可选文件，不需要就直接删掉。

   这份脚本跑在一个**受限沙箱**里，拿不到 localStorage / fetch / eval，
   碰不到存档，也改不了地址栏。你能用的只有下面这个 STMGTheme 对象：

     STMGTheme.register({
       name: "我的美化包",              // 显示用

       css: "#namebox{...}",            // 可选：顺手塞一段样式，等价于 theme.css

       onReady(api)  { },               // 页面 DOM 好了（引擎还没启动）
       onTitle(api)  { },               // 每次回到标题画面
       onSay(api, line) { },            // 每句台词开始显示；line = {who, text}
       onChoose(api, opts) { },         // 选择支出现；opts 是选项文字数组
       onEnding(api) { },               // 进入结局画面
     });

   api 里能用的东西：

     api.stage          #stage 元素
     api.el(sel)        在 #stage 里 querySelector（只找画面内的东西）
     api.layer(name)    取/建一个装饰层：绝对定位、pointer-events:none，
                        不会挡住点击，适合放粒子、边框、装饰图
     api.palette()      当前配色 {accent, accent2, ink, box, boxAlpha}
     api.rect()         画面尺寸 {w, h}（注意是基准分辨率，不是屏幕像素）
     api.on(name, fn)   在 #stage 上监听事件（click / pointermove / touchstart…）
     api.off(name, fn)  取消监听
     api.watch(name, fn)在 window 上监听（keydown / resize…）
     api.log(msg)       打日志

   注意：台词内容、选项内容都只读，别去改它们；引擎的推进由引擎自己管。
   ========================================================================== */

STMGTheme.register({
  name: "示例美化包",

  onReady(api) {
    var layer = api.layer("deco");
    var r = api.rect();
    layer.innerHTML = "";
    api.log("美化包已就绪：" + r.w + "x" + r.h);
  },

  onSay(api, line) {
    // 例子：说台词时给名字框闪一下
    var box = api.el("#namebox");
    if (box) {
      box.style.transition = "none";
      box.style.filter = "brightness(1.25)";
      setTimeout(function () { box.style.filter = ""; }, 120);
    }
  },
});
