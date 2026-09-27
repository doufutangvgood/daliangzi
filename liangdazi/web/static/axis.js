/* 立场坐标轴 —— 手写 SVG 谱系图。
 *
 * 现有开源工具都用饼图/柱状图/嵌套树，没有「给立场画一条谱系轴」的现成方案，
 * 也没有仍在维护的 likert 组件。这里是「混乱粉笔」那套呈现的核心。
 *
 * ── 几何设计（这一版是重写过的，前一版有标签重叠的缺陷）──
 *
 *   轴线 ─────●───────●────────●─────●───────●─────
 *            │╲      │        │     │        │
 *            │ ╲     │        │     │        │        ← 引线
 *          [标签]  [标签]   [标签] [标签]   [标签]      ← 标签行（按泳道分层避让）
 *
 * 关键点：**圆贴近轴线排成一行，标签一律排在圆的外侧（远离轴线的一边）。**
 * 前一版把标签放在圆和轴线之间，于是标签必然和更靠轴的圆撞在一起。
 * 现在标签按「行」占位，用贪心算法选泳道和层号，保证同行不重叠。
 */

(function (global) {
  'use strict';

  var SVG_NS = 'http://www.w3.org/2000/svg';

  /*
   * 宽度不用固定值。
   * 之前用固定 viewBox 1000 宽 + width:100%，在窄容器里会被等比缩到 0.5 倍，
   * 12px 的字变成 6px，完全没法看。现在按容器实际像素宽度 1:1 建坐标系，
   * 字号就是真实字号，窗口变窄时标签自动往更多行里避让（图会变高）。
   */
  var MIN_W = 620;
  var PAD_X = 14;

  var CIRCLE_OFFSET = 30;   // 圆心离轴线的距离
  var LABEL_BASE = 62;      // 第一行标签离轴线的距离
  var LABEL_STEP = 29;      // 相邻标签行的间距
  var LABEL_LINE = 15;      // 标签内部两行文字的间距
  var TOP_PAD = 78;         // 轴名 + 两极标签占用的顶部空间
  var MAX_DEPTH = 8;

  var COLORS = {
    up:   { fill: 'rgba(90,159,224,.16)',  stroke: '#5a9fe0' },
    down: { fill: 'rgba(212,122,196,.16)', stroke: '#d47ac4' }
  };

  function el(name, attrs) {
    var node = document.createElementNS(SVG_NS, name);
    for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) {
        node.setAttribute(k, attrs[k]);
      }
    }
    return node;
  }

  /* 中文按字号宽估、ASCII 按 0.55 倍估 */
  function textWidth(s, size) {
    var w = 0;
    for (var i = 0; i < s.length; i++) {
      w += s.charCodeAt(i) > 255 ? size : size * 0.55;
    }
    return w;
  }

  function truncate(s, maxChars) {
    return s.length > maxChars ? s.slice(0, maxChars - 1) + '…' : s;
  }

  /**
   * 分配泳道与行号。
   *
   * 泳道 -1 = 轴上方，+1 = 轴下方。同一泳道内，第 d 行占用 [x - half, x + half]。
   * 按 x 从左到右贪心：为每个节点挑「行号最小」的可行位；
   * 同行号时选更空的那条泳道，让上下两侧的标签量大致平衡。
   */
  function assignRows(nodes, W) {
    var sorted = nodes.slice().sort(function (a, b) { return a.x - b.x; });
    var extent = { '-1': [], '1': [] };

    sorted.forEach(function (node) {
      var cx = PAD_X + node.x * (W - PAD_X * 2);
      var half = Math.max(
        textWidth(node.labelText, 12.5),
        textWidth(node.pctText, 11)
      ) / 2 + 7;

      var best = null;
      [-1, 1].forEach(function (lane) {
        var rows = extent[String(lane)];
        for (var d = 0; d <= MAX_DEPTH; d++) {
          var right = rows[d];
          if (right === undefined || right < cx - half) {
            // 行号优先；同一行号时选更空的一侧
            var score = d * 100000 + (right === undefined ? -1 : right);
            if (best === null || score < best.score) {
              best = { lane: lane, row: d, score: score };
            }
            break;
          }
        }
      });

      if (best === null) best = { lane: -1, row: MAX_DEPTH };

      extent[String(best.lane)][best.row] = cx + half;
      node.lane = best.lane;
      node.row = best.row;
      node.cx = cx;
    });

    return sorted;
  }

  function render(container, data, options) {
    var opts = options || {};
    var metric = opts.metric || 'pct';      // pct | weighted_pct
    var onSelect = opts.onSelect || function () {};

    container.innerHTML = '';

    var stances = (data.stances || []).filter(function (s) {
      return (s.count || 0) > 0 && typeof s.x === 'number';
    });

    if (!stances.length) {
      container.innerHTML =
        '<div class="empty">还没有坐标轴数据。先跑完「④ 立场坐标轴」这一步。</div>';
      return;
    }

    // 1:1 像素坐标系，字号即真实字号
    var W = Math.max(MIN_W, Math.round(container.clientWidth) || 900);

    var maxCount = Math.max.apply(null, stances.map(function (s) { return s.count || 1; }));

    stances.forEach(function (s) {
      s.pctText = (metric === 'weighted_pct' ? s.weighted_pct : s.pct).toFixed(1) + '%';
      s.labelText = truncate(s.canonical, W < 760 ? 8 : 11);
      s.r = 6 + 12 * Math.sqrt((s.count || 0) / maxCount);
    });

    assignRows(stances, W);

    var maxUp = 0, maxDown = 0;
    stances.forEach(function (s) {
      if (s.lane < 0) maxUp = Math.max(maxUp, s.row);
      else maxDown = Math.max(maxDown, s.row);
    });

    var axisY = TOP_PAD + LABEL_BASE + maxUp * LABEL_STEP;
    var height = axisY + LABEL_BASE + maxDown * LABEL_STEP + 26;

    var svg = el('svg', {
      'class': 'axis-svg',
      width: W,
      height: height,
      viewBox: '0 0 ' + W + ' ' + height
    });
    svg.style.width = W + 'px';
    svg.style.height = height + 'px';

    /* ---- 渐变轴线 ---- */
    var defs = el('defs', {});
    var grad = el('linearGradient', { id: 'axisGrad', x1: '0', y1: '0', x2: '1', y2: '0' });
    [['0%', '#5a9fe0'], ['52%', '#414c5c'], ['100%', '#d47ac4']].forEach(function (pair) {
      grad.appendChild(el('stop', { offset: pair[0], 'stop-color': pair[1] }));
    });
    defs.appendChild(grad);
    svg.appendChild(defs);

    /* ---- 轴名 ---- */
    var nameText = el('text', {
      'class': 'axis-name', x: W / 2, y: 18, 'text-anchor': 'middle'
    });
    nameText.textContent = (data.axis && data.axis.name) || '立场坐标轴';
    svg.appendChild(nameText);

    /* ---- 两极标签 ---- */
    var ax = data.axis || {};
    function pole(x, anchor, label, desc) {
      if (!label) return;
      var t = el('text', {
        'class': 'pole-label', x: x, y: 44, 'text-anchor': anchor
      });
      t.textContent = label;
      svg.appendChild(t);
      if (desc) {
        var d = el('text', {
          'class': 'pole-desc', x: x, y: 62, 'text-anchor': anchor
        });
        d.textContent = truncate(desc, 24);
        svg.appendChild(d);
      }
    }
    pole(PAD_X, 'start', ax.left_pole, ax.left_desc);
    pole(W - PAD_X, 'end', ax.right_pole, ax.right_desc);

    /* ---- 轴线 ---- */
    svg.appendChild(el('line', {
      x1: PAD_X, y1: axisY, x2: W - PAD_X, y2: axisY,
      stroke: 'url(#axisGrad)', 'stroke-width': 1.5
    }));

    /* ---- 刻度 ---- */
    for (var i = 0; i <= 10; i++) {
      var tx = PAD_X + (i / 10) * (W - PAD_X * 2);
      svg.appendChild(el('line', {
        x1: tx, y1: axisY - 3.5, x2: tx, y2: axisY + 3.5,
        stroke: '#2e3745', 'stroke-width': 1
      }));
    }

    /* ---- 立场节点 ---- */
    stances.forEach(function (s) {
      var palette = s.lane < 0 ? COLORS.up : COLORS.down;
      var circleY = axisY + s.lane * CIRCLE_OFFSET;
      var labelY = axisY + s.lane * (LABEL_BASE + s.row * LABEL_STEP);
      // 名称靠圆、百分比在外侧
      var pctY = labelY + s.lane * LABEL_LINE;

      var group = el('g', { 'class': 'node' });
      group.setAttribute('data-canonical', s.canonical);

      // 轴线 → 圆：虚线，表示这是轴上的位置
      group.appendChild(el('line', {
        x1: s.cx, y1: axisY, x2: s.cx, y2: circleY,
        stroke: '#232a37', 'stroke-width': 1, 'stroke-dasharray': '2 3'
      }));

      // 圆 → 标签：细实线引线
      group.appendChild(el('line', {
        x1: s.cx, y1: circleY, x2: s.cx, y2: labelY - s.lane * 6,
        stroke: '#2b3342', 'stroke-width': 1
      }));

      group.appendChild(el('circle', {
        cx: s.cx, cy: circleY, r: s.r,
        fill: palette.fill, stroke: palette.stroke, 'stroke-width': 1.5
      }));

      var label = el('text', {
        'class': 'node-label', x: s.cx, y: labelY, 'text-anchor': 'middle'
      });
      label.textContent = s.labelText;
      group.appendChild(label);

      var pct = el('text', {
        'class': 'node-pct', x: s.cx, y: pctY, 'text-anchor': 'middle'
      });
      pct.textContent = s.pctText;
      group.appendChild(pct);

      var tip = el('title', {});
      var lines = [s.canonical + ' · ' + s.pctText];
      if (s.core_logic) lines.push(s.core_logic);
      lines.push('条数 ' + s.count + ' · 点赞加权 ' + (s.weighted_pct || 0) + '%');
      if (typeof s.x === 'number') {
        lines.push('轴位 ' + s.x.toFixed(3) +
          (s.left_affinity != null
            ? '（左端贴合 ' + s.left_affinity + ' / 右端贴合 ' + s.right_affinity + '）'
            : ''));
      }
      if (s.evidence && s.evidence.length) lines.push('「' + s.evidence[0] + '」');
      tip.textContent = lines.join('\n');
      group.appendChild(tip);

      group.addEventListener('click', function () { onSelect(s); });
      svg.appendChild(group);
    });

    container.appendChild(svg);
  }

  global.LDAxis = { render: render };
})(window);
