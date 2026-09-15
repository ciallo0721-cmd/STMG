/* 「樱花飘落」示例美化包 —— 网页版行为（落樱粒子）。
   这段脚本跑在受限沙箱里：没有 localStorage、没有 fetch、没有 eval，
   只能用 STMGTheme 给的 api。发布为 HTML 时会内联进 index.html。 */

STMGTheme.register({
  name: "樱花飘落",

  onReady(api) {
    var layer = api.layer("sakura");
    var box = api.rect();
    var N = 24;
    var petals = [];

    layer.innerHTML = "";
    for (var i = 0; i < N; i++) {
      var el = document.createElement("div");
      el.className = "deco-petal";
      var size = 6 + Math.random() * 8;
      el.style.width = size + "px";
      el.style.height = size + "px";
      el.style.opacity = (0.3 + Math.random() * 0.5).toFixed(2);
      layer.appendChild(el);
      petals.push({
        el: el,
        x: Math.random() * box.w,
        y: Math.random() * box.h,
        vy: 0.22 + Math.random() * 0.6,
        vx: -0.3 + Math.random() * 0.6,
        rot: Math.random() * 360,
        spin: -1.1 + Math.random() * 2.2
      });
    }

    function step() {
      for (var i = 0; i < petals.length; i++) {
        var p = petals[i];
        p.y += p.vy;
        p.x += p.vx;
        p.rot += p.spin;
        if (p.y > box.h + 20) { p.y = -20; p.x = Math.random() * box.w; }
        if (p.x < -30) { p.x = box.w + 20; }
        if (p.x > box.w + 30) { p.x = -20; }
        p.el.style.transform = "translate(" + p.x.toFixed(1) + "px," + p.y.toFixed(1)
          + "px) rotate(" + p.rot.toFixed(1) + "deg)";
      }
      requestAnimationFrame(step);
    }
    step();
    api.log("落樱粒子已启动：" + petals.length + " 片");
  },

  onSay(api, line) {
    // 有人说话的时候，名字框轻轻亮一下
    var box = api.el("#namebox");
    if (!box) { return; }
    box.style.filter = "brightness(1.2)";
    setTimeout(function () { box.style.filter = ""; }, 130);
  }
});
