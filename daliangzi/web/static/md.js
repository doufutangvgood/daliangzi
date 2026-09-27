/* 极简 Markdown 渲染器。
 *
 * 不引 CDN —— 本地工具断网也要能用。
 * 先转义 HTML 再做行内格式化，避免模型输出里的尖括号破坏页面。
 */

(function (global) {
  'use strict';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function inline(s) {
    return s
      // 行内代码先处理，避免里面的 ** 被当粗体
      .replace(/`([^`]+)`/g, function (_, code) { return '<code>' + code + '</code>'; })
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  }

  function render(src) {
    if (!src) return '';

    var lines = escapeHtml(src).split('\n');
    var out = [];
    var i = 0;

    function flushParagraph(buf) {
      if (buf.length) {
        out.push('<p>' + inline(buf.join(' ')) + '</p>');
        buf.length = 0;
      }
    }

    var para = [];

    while (i < lines.length) {
      var line = lines[i];
      var trimmed = line.trim();

      /* 代码块 */
      if (/^```/.test(trimmed)) {
        flushParagraph(para);
        var code = [];
        i++;
        while (i < lines.length && !/^```/.test(lines[i].trim())) {
          code.push(lines[i]);
          i++;
        }
        i++;
        out.push('<pre><code>' + code.join('\n') + '</code></pre>');
        continue;
      }

      /* 标题 */
      var h = trimmed.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        flushParagraph(para);
        var level = h[1].length;
        out.push('<h' + level + '>' + inline(h[2]) + '</h' + level + '>');
        i++;
        continue;
      }

      /* 分隔线 */
      if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
        flushParagraph(para);
        out.push('<hr>');
        i++;
        continue;
      }

      /* 引用 */
      if (/^&gt;\s?/.test(trimmed)) {
        flushParagraph(para);
        var quote = [];
        while (i < lines.length && /^\s*&gt;\s?/.test(lines[i])) {
          quote.push(lines[i].replace(/^\s*&gt;\s?/, ''));
          i++;
        }
        out.push('<blockquote>' + inline(quote.join('<br>')) + '</blockquote>');
        continue;
      }

      /* 列表 */
      var ul = trimmed.match(/^[-*+]\s+(.*)$/);
      var ol = trimmed.match(/^\d+[.)]\s+(.*)$/);
      if (ul || ol) {
        flushParagraph(para);
        var ordered = !!ol;
        var items = [];
        while (i < lines.length) {
          var t = lines[i].trim();
          var m = ordered ? t.match(/^\d+[.)]\s+(.*)$/) : t.match(/^[-*+]\s+(.*)$/);
          if (!m) break;
          items.push('<li>' + inline(m[1]) + '</li>');
          i++;
        }
        out.push('<' + (ordered ? 'ol' : 'ul') + '>' + items.join('') + '</' + (ordered ? 'ol' : 'ul') + '>');
        continue;
      }

      /* 空行 = 段落分隔 */
      if (!trimmed) {
        flushParagraph(para);
        i++;
        continue;
      }

      para.push(trimmed);
      i++;
    }

    flushParagraph(para);
    return out.join('\n');
  }

  global.LDMarkdown = { render: render, escapeHtml: escapeHtml };
})(window);
