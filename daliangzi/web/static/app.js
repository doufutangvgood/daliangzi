/* 大量子 前端逻辑。零依赖，零构建。 */

(function () {
  'use strict';

  var state = {
    runId: null,
    data: null,
    metric: 'pct',
    previewPayload: null,
    currentPrompt: 'stage1_标签',
    stream: null
  };

  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return window.LDMarkdown.escapeHtml(s == null ? '' : s); };

  /* ---------------------------------------------------------------- 工具 */

  function api(path, options) {
    var opts = options || {};
    if (opts.json) {
      opts.method = opts.method || 'POST';
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(opts.json);
      delete opts.json;
    }
    return fetch(path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) {
        if (!res.ok) {
          throw new Error(body.error || ('HTTP ' + res.status));
        }
        return body;
      });
    });
  }

  function note(kind, text) {
    return '<div class="note ' + kind + '">' + text + '</div>';
  }

  function money(v) {
    if (v === 0) return '0';
    return v < 0.01 ? v.toFixed(4) : v.toFixed(2);
  }

  function toast(msg, kind) {
    var host = $('analyzeResult');
    if (!host) return;
    host.insertAdjacentHTML('afterbegin', note(kind || 'info', esc(msg)));
  }

  /* ---------------------------------------------------------------- 标签页 */

  function setView(name) {
    document.querySelectorAll('.tab').forEach(function (t) {
      t.classList.toggle('active', t.dataset.view === name);
    });
    document.querySelectorAll('.view').forEach(function (v) {
      v.classList.toggle('active', v.id === 'view-' + name);
    });
  }

  document.querySelectorAll('.tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      if (!tab.disabled) setView(tab.dataset.view);
    });
  });

  function enableTab(name, on) {
    var tab = document.querySelector('.tab[data-view="' + name + '"]');
    if (tab) tab.disabled = !on;
  }

  /* ---------------------------------------------------------------- 设置 */

  function loadStatus() {
    return api('/api/status').then(function (s) {
      var pill = $('keyStatus');
      if (s.has_key) {
        pill.className = 'pill ok';
        pill.textContent = s.masked_key + ' · ' + s.model;
      } else {
        pill.className = 'pill warn';
        pill.textContent = '未配置 API Key';
      }
      $('envPath').textContent = s.env_file;
      $('setModel').value = s.model;
      $('setBatch').value = s.batch_size;
      $('setConcurrency').value = s.concurrency;
      state.status = s;
      return s;
    });
  }

  $('btnSettings').addEventListener('click', function () {
    $('settingsModal').style.display = 'flex';
    $('settingsMsg').innerHTML = '';
  });

  $('btnCloseSettings').addEventListener('click', function () {
    $('settingsModal').style.display = 'none';
  });

  $('settingsModal').addEventListener('click', function (e) {
    if (e.target === $('settingsModal')) $('settingsModal').style.display = 'none';
  });

  $('btnSaveSettings').addEventListener('click', function () {
    var body = {
      model: $('setModel').value,
      batch_size: $('setBatch').value,
      concurrency: $('setConcurrency').value
    };
    var key = $('setKey').value.trim();
    if (key) body.api_key = key;

    api('/api/settings', { json: body }).then(function () {
      $('setKey').value = '';
      $('settingsMsg').innerHTML = note('ok', '已保存。');
      return loadStatus();
    }).catch(function (err) {
      $('settingsMsg').innerHTML = note('err', esc(err.message));
    });
  });

  $('btnTestKey').addEventListener('click', function () {
    var btn = this;
    btn.disabled = true;
    $('settingsMsg').innerHTML = note('info', '<span class="spinner"></span>正在测试…');
    api('/api/settings/test', { json: {} }).then(function (r) {
      $('settingsMsg').innerHTML = note('ok', '连通正常。模型回复：<span class="mono">' + esc(r.reply) + '</span>');
    }).catch(function (err) {
      $('settingsMsg').innerHTML = note('err', esc(err.message));
    }).finally(function () {
      btn.disabled = false;
    });
  });

  /* ---------------------------------------------------------------- 导入 */

  $('btnUpload').addEventListener('click', function () { $('fileInput').click(); });

  $('fileInput').addEventListener('change', function () {
    var file = this.files[0];
    if (!file) return;
    $('fileName').textContent = file.name + ' · ' + (file.size / 1024).toFixed(1) + ' KB';
    var reader = new FileReader();
    reader.onload = function () {
      $('rawText').value = reader.result;
      $('importHint').textContent = '已读入，点「解析预览」看看字段识别对不对。';
      $('btnImport').disabled = false;
    };
    reader.readAsText(file, 'utf-8');
  });

  $('rawText').addEventListener('input', function () {
    $('btnImport').disabled = !this.value.trim();
  });

  $('btnPreview').addEventListener('click', function () {
    var text = $('rawText').value;
    if (!text.trim()) { alert('先粘贴或上传内容。'); return; }
    $('previewBody').innerHTML = note('info', '<span class="spinner"></span>解析中…');
    $('previewCard').style.display = 'block';

    api('/api/preview', { json: { text: text, filename: $('fileName').textContent.split(' · ')[0] } })
      .then(function (r) {
        state.previewPayload = r;
        renderPreview(r);
        $('btnImport').disabled = false;
      })
      .catch(function (err) {
        $('previewBody').innerHTML = note('err', esc(err.message));
      });
  });

  function renderPreview(r) {
    var m = r.mapping || {};
    var html = '';

    html += note('ok', '识别为 <b>' + esc(r.source_format) + '</b> 格式，共 <b>' + r.total_records + '</b> 条原始记录。');
    if (r.warnings && r.warnings.length) {
      html += note('warn', r.warnings.map(esc).join('<br>'));
    }

    html += '<div class="row tight" style="margin:12px 0">';
    ['text', 'likes', 'author', 'created_at'].forEach(function (semantic) {
      var label = { text: '评论正文', likes: '点赞数', author: '作者', created_at: '时间' }[semantic];
      var fields = r.available_fields || [];
      var options = ['<option value="">（无）</option>'].concat(fields.map(function (f) {
        return '<option value="' + esc(f) + '"' + (m[semantic] === f ? ' selected' : '') + '>' + esc(f) + '</option>';
      })).join('');
      html += '<label class="field"><span>' + label + '</span><select data-semantic="' + semantic + '">' + options + '</select></label>';
    });
    html += '</div>';

    var c = r.clean || {};
    html += '<table class="data"><tr><th>原始</th><th>去空</th><th>去太短</th><th>去灌水</th><th>去广告</th><th>去重复</th><th>保留</th></tr><tr>' +
      '<td class="num">' + (c['原始条数'] || 0) + '</td>' +
      '<td class="num">' + (c['去空'] || 0) + '</td>' +
      '<td class="num">' + (c['去太短'] || 0) + '</td>' +
      '<td class="num">' + (c['去灌水'] || 0) + '</td>' +
      '<td class="num">' + (c['去广告'] || 0) + '</td>' +
      '<td class="num">' + (c['去重复'] || 0) + '</td>' +
      '<td class="num"><b>' + (c['保留'] || 0) + '</b></td></tr></table>';

    if (r.preview && r.preview.length) {
      html += '<p class="hint" style="margin-top:16px">清洗后前几条：</p>';
      r.preview.slice(0, 5).forEach(function (cm) {
        html += '<blockquote style="margin:4px 0;padding:6px 12px;border-left:2px solid #2e3745;color:#8b97a8">' +
          esc(cm.text) + (cm.likes ? ' <span class="mono faint">♥ ' + cm.likes + '</span>' : '') + '</blockquote>';
      });
    }

    $('previewBody').innerHTML = html;

    // 手动改字段映射 → 即时重算预览
    $('previewBody').querySelectorAll('select[data-semantic]').forEach(function (sel) {
      sel.addEventListener('change', function () {
        var mapping = {};
        $('previewBody').querySelectorAll('select[data-semantic]').forEach(function (s) {
          if (s.value) mapping[s.dataset.semantic] = s.value;
        });
        api('/api/preview', {
          json: {
            text: $('rawText').value,
            filename: $('fileName').textContent.split(' · ')[0],
            mapping: mapping
          }
        }).then(function (r2) {
          state.previewPayload = r2;
          var c2 = r2.clean || {};
          var table = $('previewBody').querySelector('table.data');
          if (table) {
            table.rows[1].innerHTML =
              '<td class="num">' + (c2['原始条数'] || 0) + '</td>' +
              '<td class="num">' + (c2['去空'] || 0) + '</td>' +
              '<td class="num">' + (c2['去太短'] || 0) + '</td>' +
              '<td class="num">' + (c2['去灌水'] || 0) + '</td>' +
              '<td class="num">' + (c2['去广告'] || 0) + '</td>' +
              '<td class="num">' + (c2['去重复'] || 0) + '</td>' +
              '<td class="num"><b>' + (c2['保留'] || 0) + '</b></td>';
          }
        });
      });
    });
  }

  $('btnImport').addEventListener('click', function () {
    var text = $('rawText').value;
    if (!text.trim()) { alert('没有内容。'); return; }

    var mapping = {};
    var selects = $('previewBody') ? $('previewBody').querySelectorAll('select[data-semantic]') : [];
    selects.forEach(function (s) { if (s.value) mapping[s.dataset.semantic] = s.value; });

    var btn = this;
    btn.disabled = true;
    btn.textContent = '导入中…';

    api('/api/import', {
      json: {
        text: text,
        filename: $('fileName').textContent.split(' · ')[0] || '',
        event_name: $('eventName').value.trim() || '未命名事件',
        platform: $('platform').value,
        mapping: Object.keys(mapping).length ? mapping : null
      }
    }).then(function (r) {
      state.runId = r.run_id;
      return loadRuns().then(function () { return r; });
    }).then(function (r) {
      toast('导入成功：' + r.count + ' 条评论。现在去「分析」页。', 'ok');
      setView('analyze');
      return loadRun(state.runId);
    }).then(function () {
      return refreshEstimate();
    }).catch(function (err) {
      $('previewBody').innerHTML = note('err', esc(err.message));
      $('previewCard').style.display = 'block';
    }).finally(function () {
      btn.disabled = false;
      btn.textContent = '导入';
    });
  });

  /* ---------------------------------------------------------------- 历史 */

  function loadRuns() {
    return api('/api/runs').then(function (r) {
      var host = $('runList');
      if (!r.runs.length) {
        host.innerHTML = '<div class="empty">还没有分析记录。<br>先在右边导入一批评论。</div>';
        return;
      }
      host.innerHTML = r.runs.map(function (run) {
        var done = run.stage_done != null
          ? run.stage_done
          : Object.keys(run.stages).filter(function (k) { return run.stages[k]; }).length;
        var total = run.stage_total || 6;
        return '<div class="run-item' + (run.run_id === state.runId ? ' active' : '') + '" data-run="' + esc(run.run_id) + '">' +
          '<div class="name">' + esc(run.event_name) +
          (run.is_demo ? ' <span class="pill" style="font-size:10px">演示</span>' : '') + '</div>' +
          '<div class="meta">' + run.comment_count + ' 条 · ' + done + '/' + total + ' 阶段</div>' +
          '</div>';
      }).join('');

      host.querySelectorAll('.run-item').forEach(function (item) {
        item.addEventListener('click', function () {
          selectRun(item.dataset.run);
        });
      });
    });
  }

  function selectRun(runId) {
    state.runId = runId;
    loadRuns();
    loadRun(runId).then(function () {
      if (state.data && state.data.stats && state.data.stats.stances && state.data.stats.stances.length) {
        setView('stances');
      } else {
        setView('analyze');
      }
      return refreshEstimate();
    });
  }

  function loadRun(runId) {
    return api('/api/runs/' + encodeURIComponent(runId)).then(function (d) {
      state.data = d;
      var hasStances = d.stats && d.stats.stances && d.stats.stances.length > 0;
      var hasReport = !!(d.report && d.report.trim());

      enableTab('stances', !!hasStances);
      enableTab('report', hasReport);

      $('analyzeEmpty').style.display = 'none';
      $('analyzeBody').style.display = 'block';

      $('stancesEmpty').style.display = hasStances ? 'none' : 'block';
      $('stancesBody').style.display = hasStances ? 'block' : 'none';

      $('reportEmpty').style.display = hasReport ? 'none' : 'block';
      $('reportBody').style.display = hasReport ? 'block' : 'none';

      renderRedoToggles(d);
      if (hasStances) renderStances(d);
      if (hasReport) renderReport(d);
      return d;
    });
  }

  function renderRedoToggles(d) {
    var labels = state.status.stage_labels || {};
    var order = ['labels', 'canonical', 'axis', 'jury', 'report'];
    $('redoToggles').innerHTML = order.map(function (stage) {
      var exists = d.has && d.has[stage];
      return '<label class="field" style="flex:0 0 auto;margin:0">' +
        '<span style="margin:0"><input type="checkbox" data-redo="' + stage + '"> ' +
        esc(labels[stage] || stage) + (exists ? ' <span class="faint">(已有)</span>' : '') +
        '</span></label>';
    }).join('');
  }

  function getRedo() {
    var redo = [];
    $('redoToggles').querySelectorAll('input[data-redo]:checked').forEach(function (cb) {
      redo.push(cb.dataset.redo);
    });
    return redo;
  }

  /* ---------------------------------------------------------------- 成本 */

  function getSampleLimit() {
    var el = $('sampleLimit');
    var v = parseInt(el && el.value, 10);
    return isNaN(v) || v < 0 ? 0 : v;
  }

  function refreshEstimate() {
    if (!state.runId) return Promise.resolve();
    $('estimateRows').innerHTML = '<p class="dim mono">估算中…</p>';
    return api('/api/estimate', {
      json: { run_id: state.runId, redo: getRedo(), sample_limit: getSampleLimit() }
    })
      .then(function (est) {
        $('estimateNote').innerHTML = esc(est.note) +
          (est.cache_note ? '<br><span class="faint">' + esc(est.cache_note) + '</span>' : '') +
          (est.sampled
            ? '<br><span style="color:#e8b04b">将抽样：从 ' + est.imported_count +
              ' 条中随机抽 ' + est.comment_count + ' 条分析。</span>'
            : '');
        var thinkingLabel = {
          disabled: '关',
          low: '低',
          high: '高',
          max: '最高'
        };
        var rows = est.rows.map(function (r) {
          var think = thinkingLabel[r.thinking] || r.thinking || '默认';
          var thinkCell = r.thinking === 'disabled'
            ? '<span class="faint">关（省钱）</span>'
            : '<span class="dim">' + esc(think) + '</span>';
          return '<tr><td>' + esc(r.label) + '</td>' +
            '<td>' + thinkCell + '</td>' +
            '<td class="num">' + r.tokens.toLocaleString() + '</td>' +
            '<td class="num">' + (r.reused ? '<span class="faint">复用，0</span>' : money(r.cost) + ' 元') + '</td></tr>';
        }).join('');
        $('estimateRows').innerHTML =
          '<table class="data"><tr><th>阶段</th><th>思考</th>' +
          '<th style="text-align:right">约 token</th><th style="text-align:right">约花费</th></tr>' +
          rows +
          '<tr><td><b>合计</b></td><td class="faint">' + est.batches + ' 批（前 ' + (est.cold_wave || 1) + ' 批无缓存）</td>' +
          '<td class="num faint"></td>' +
          '<td class="num"><b class="mono" style="color:#4fd6d2">' + money(est.total) + ' 元</b></td></tr></table>' +
          '<p class="hint" style="margin-top:8px">基于 ' + est.comment_count + ' 条评论估算，仅供参考。实际费用以 DeepSeek 账单为准。<br>' +
          '「思考」列是 DeepSeek 的思考模式强度 —— 大批量机械抽取的阶段关掉它能省下可观的输出费用，因为思维链 token 按输出价计费。</p>';
      })
      .catch(function (err) {
        $('estimateRows').innerHTML = note('err', esc(err.message));
      });
  }

  $('btnReestimate').addEventListener('click', refreshEstimate);

  /* 试跑：只跑阶段一，抽 30 条，花几分钱先看捞取质量。
     产物会保留，全量跑时直接复用，不重复付费。 */
  $('btnTrial').addEventListener('click', function () {
    if (!state.runId) { alert('先导入评论。'); return; }
    var btn = this;
    btn.disabled = true;

    $('trialCard').style.display = 'block';
    $('trialMeta').innerHTML = '<span class="spinner"></span>试跑中…（抽 30 条只跑捞标签这一步）';
    $('trialRows').innerHTML = '';
    $('trialTerms').innerHTML = '';

    api('/api/analyze', {
      json: {
        run_id: state.runId,
        redo: ['labels'],
        sample_limit: 30,
        stop_after: 'labels'
      }
    }).then(function (r) {
      // 复用进度流，跑完自动去拉标签明细
      startStream(r.job_id, function (summary) {
        showTrial();
      });
    }).catch(function (err) {
      $('trialMeta').innerHTML = note('err', esc(err.message));
    }).finally(function () { btn.disabled = false; });
  });

  function showTrial() {
    api('/api/runs/' + encodeURIComponent(state.runId) + '/labels?limit=30&only_labelled=0')
      .then(function (d) {
        var pct = d.total_comments
          ? Math.round(100 * d.labelled / d.total_comments) : 0;
        var emptyRate = d.labelled ? Math.round(100 * d.empty / d.labelled) : 0;
        var nOpinions = d.distinct_opinions != null ? d.distinct_opinions : d.distinct_terms;

        $('trialMeta').innerHTML = note('ok',
          '已核对 <b>' + d.labelled + '</b> / ' + d.total_comments + ' 条（' + pct + '%），'
          + '提炼出 <b>' + nOpinions + '</b> 个不同的观点，'
          + '<b>' + d.with_labels + '</b> 条有观点、<b>' + d.empty + '</b> 条没提炼出观点（' + emptyRate + '%）。'
          + (emptyRate > 50
              ? '<br><span style="color:#e8b04b">没提炼出观点的比例偏高。'
                + '真正没有观点的评论（纯表情、纯玩梗、纯复读）占比通常在三成以内 —— '
                + '如果明显更高，可能是提示词太保守，可以到「提示词」页把 stage1 的语气放松一点。</span>'
              : ''));

        $('trialTerms').innerHTML = (d.top_opinions && d.top_opinions.length)
          ? '<div class="faint" style="margin-bottom:6px">提炼出的观点（部分）：</div>' +
            '<div class="aliases">' + d.top_opinions.slice(0, 30).map(function (t) {
              return '<span class="alias">' + esc(t) + '</span>';
            }).join('') + '</div>'
          : '';

        $('trialRows').innerHTML = d.rows.map(function (r) {
          var ops = (r.labels || []).map(function (l) {
            var term = l.term ? ' <span class="faint mono">[' + esc(l.term) + ']</span>' : '';
            return '<span class="pill cyan">' + esc(l.opinion || l.term || '') + '</span>'
              + term
              + (l.stance ? ' <span class="faint mono">' + esc(l.stance) + '</span>' : '');
          }).join(' &nbsp; ');
          return '<div style="padding:9px 0;border-bottom:1px solid #232a37">' +
            '<div style="margin-bottom:5px">' + esc(r.text) +
            (r.likes ? ' <span class="mono faint">♥' + r.likes + '</span>' : '') + '</div>' +
            '<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">' +
            (ops || '<span class="faint mono">（没提炼出观点）</span>') + '</div>' +
            '</div>';
        }).join('');
      })
      .catch(function (err) {
        $('trialMeta').innerHTML = note('err', esc(err.message));
      });
  }

  $('btnDryRun').addEventListener('click', function () {
    if (!state.runId) { alert('先导入评论。'); return; }
    var btn = this;
    btn.disabled = true;
    $('dryRunCard').style.display = 'block';
    $('dryRunBody').innerHTML = '<div><span class="spinner"></span>构造中…</div>';

    api('/api/dry-run', { json: { run_id: state.runId, stage: 'labels' } })
      .then(function (d) {
        $('dryRunNote').textContent = d.note || '';
        $('dryRunMeta').innerHTML =
          'POST <span style="color:#4fd6d2">' + esc(d.url) + '</span><br>' +
          'Authorization: ' + esc(d.headers.Authorization) + '<br>' +
          'model=' + esc(d.model) + ' · thinking=' + esc(d.thinking) +
          ' · 本批 ' + d.batch_size + ' 条';
        $('dryRunBody').innerHTML = '<pre style="margin:0;white-space:pre-wrap;word-break:break-all">' +
          esc(JSON.stringify(d.payload, null, 2)) + '</pre>';
      })
      .catch(function (err) {
        $('dryRunBody').innerHTML = '<div class="err">' + esc(err.message) + '</div>';
      })
      .finally(function () { btn.disabled = false; });
  });

  // 勾选/取消重跑范围、改抽样上限时，预估要跟着变
  document.addEventListener('change', function (e) {
    if (e.target && e.target.matches && e.target.matches('input[data-redo]')) {
      refreshEstimate();
    }
  });
  document.addEventListener('input', function (e) {
    if (e.target && e.target.id === 'sampleLimit') {
      clearTimeout(state.sampleTimer);
      state.sampleTimer = setTimeout(refreshEstimate, 350);
    }
  });

  /* ---------------------------------------------------------------- 分析 */

  $('btnAnalyze').addEventListener('click', function () {
    if (!state.runId) { alert('先导入评论。'); return; }
    var btn = this;
    btn.disabled = true;

    $('progressCard').style.display = 'block';
    $('logBox').innerHTML = '';
    $('progressBar').style.width = '0%';
    $('progressPct').textContent = '0%';
    $('progressTitle').textContent = '分析中…';
    $('analyzeResult').innerHTML = '';

    api('/api/analyze', {
      json: {
        run_id: state.runId,
        redo: getRedo(),
        sample_limit: getSampleLimit()
      }
    })
      .then(function (r) { startStream(r.job_id); })
      .catch(function (err) {
        addLog('启动失败：' + err.message, 'err');
        $('progressTitle').textContent = '启动失败';
        btn.disabled = false;
      });
  });

  function addLog(message, cls) {
    var box = $('logBox');
    var div = document.createElement('div');
    if (cls) div.className = cls;
    var time = new Date().toTimeString().slice(0, 8);
    div.textContent = '[' + time + '] ' + message;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function startStream(jobId, onDone) {
    if (state.stream) state.stream.close();
    var es = new EventSource('/api/analyze/stream?job_id=' + encodeURIComponent(jobId));
    state.stream = es;

    es.onmessage = function (event) {
      var data;
      try { data = JSON.parse(event.data); } catch (e) { return; }

      if (data.type === 'progress') {
        $('progressBar').style.width = data.percent + '%';
        $('progressPct').textContent = data.percent + '%';
        $('progressMsg').textContent = data.message;
        addLog(data.message);

      } else if (data.type === 'done') {
        es.close();
        state.stream = null;
        $('progressBar').style.width = '100%';
        $('progressPct').textContent = '100%';
        $('progressTitle').textContent = '完成';
        addLog('完成。花费约 ' + money(data.summary.cost) + ' 元，用时 ' + data.summary.elapsed + ' 秒。', 'ok');

        var s = data.summary;
        $('analyzeResult').innerHTML = note('ok',
          '本次实际花费 <b>' + money(s.cost) + ' 元</b>，用时 ' + s.elapsed + ' 秒。' +
          (s.stance_count ? '生成 <b>' + s.stance_count + '</b> 个立场类别。' : '') +
          (s.reused && s.reused.length ? '<br>复用了已有阶段：' + s.reused.map(esc).join('、') : '') +
          (s.sampling && s.sampling.sampled
            ? '<br>本次为抽样运行：' + esc(s.sampling.note) : ''));

        $('btnAnalyze').disabled = false;

        if (onDone) {
          onDone(s);
        } else {
          loadRuns().then(function () { return loadRun(state.runId); }).then(function () {
            setView('stances');
          });
        }

      } else if (data.type === 'error') {
        es.close();
        state.stream = null;
        $('progressTitle').textContent = '出错了';
        addLog(data.error, 'err');
        $('analyzeResult').innerHTML = note('err', '分析失败：' + esc(data.error));
        $('btnAnalyze').disabled = false;
      }
    };

    es.onerror = function () {
      // 流断了但任务可能还在跑；不关闭，让浏览器自动重连
      addLog('连接中断，正在重连…', 'err');
    };
  }

  /* ---------------------------------------------------------------- 立场 */

  function renderStances(d) {
    var stats = d.stats || {};
    var stances = stats.stances || [];
    var axis = d.axis || {};

    $('axisHint').innerHTML = axis.axis && axis.axis.note
      ? esc(axis.axis.note)
      : '位置由模型判断的立场对立程度决定，点标签可以看明细。';

    drawAxis();

    $('metricCount').classList.toggle('active', state.metric === 'pct');
    $('metricLikes').classList.toggle('active', state.metric === 'weighted_pct');

    var c = stats;
    $('statGrid').innerHTML = [
      ['分析评论', c.total_comments || 0, '条'],
      ['捞到标签', c.armed_comments || 0, '条'],
      ['无标签', c.unarmed_comments || 0, '条'],
      ['立场类别', stances.length, '个'],
      ['标签归属', c.total_assignments || 0, '次'],
      ['多立场评论', c.multi_label_comments || 0, '条']
    ].map(function (row) {
      return '<div class="stat"><div class="k">' + row[0] + '</div>' +
        '<div class="v">' + row[1].toLocaleString() + '<span class="u">' + row[2] + '</span></div></div>';
    }).join('');

    var notesHtml = '';
    (c.notes || []).forEach(function (n) { notesHtml += note('warn', esc(n)); });
    (d.canonical && d.canonical.merge_notes ? [d.canonical.merge_notes] : []).forEach(function (n) {
      notesHtml += note('info', '<b>合并说明：</b>' + esc(n));
    });
    (d.canonical && d.canonical.notes || []).forEach(function (n) { notesHtml += note('warn', esc(n)); });
    (axis.notes || []).forEach(function (n) { notesHtml += note('warn', esc(n)); });
    (d.label_notes || []).forEach(function (n) { notesHtml += note('warn', esc(n)); });
    $('statNotes').innerHTML = notesHtml;

    renderStanceList(stances);
  }

  function drawAxis() {
    if (!state.data) return;
    var stances = (state.data.stats || {}).stances || [];
    var axis = state.data.axis || {};
    window.LDAxis.render($('axisHost'), {
      axis: axis.axis || {},
      stances: stances
    }, {
      metric: state.metric,
      onSelect: function (s) {
        var target = document.querySelector('.stance[data-canonical="' + CSS.escape(s.canonical) + '"]');
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  }

  // 坐标轴按容器实际宽度 1:1 渲染，所以容器尺寸变了要重画。
  // 不重画的话，窗口拉宽后图还是旧的窄版，右边一大片空白。
  var axisResizeTimer = null;
  var axisWidth = 0;
  if (window.ResizeObserver) {
    var ro = new ResizeObserver(function (entries) {
      var w = Math.round(entries[0].contentRect.width);
      if (!w || Math.abs(w - axisWidth) < 24) return;   // 小幅抖动不重画
      axisWidth = w;
      clearTimeout(axisResizeTimer);
      axisResizeTimer = setTimeout(drawAxis, 160);
    });
    ro.observe($('axisHost'));
  }

  $('metricCount').addEventListener('click', function () { state.metric = 'pct'; renderStances(state.data); });
  $('metricLikes').addEventListener('click', function () { state.metric = 'weighted_pct'; renderStances(state.data); });

  function renderStanceList(stances) {
    var colors = ['#5a9fe0', '#d47ac4', '#e8b04b', '#6bc98a', '#4fd6d2', '#e06c75', '#8b97a8'];
    $('stanceList').innerHTML = stances.map(function (s, i) {
      var empty = !s.count;
      // aliases 是观点短句，terms 是这一派常说的圈内词
      var opinions = (s.aliases || []).slice(0, 12).map(function (a) {
        return '<span class="alias">' + esc(a) + '</span>';
      }).join('');
      var moreOps = (s.aliases || []).length > 12
        ? '<span class="faint mono">等 ' + s.aliases.length + ' 个观点</span>' : '';
      var slang = (s.terms || []).slice(0, 10).map(function (t) {
        return '<span class="alias" style="color:#4fd6d2;background:rgba(79,214,210,.08);border-color:rgba(79,214,210,.25)">' +
          esc(t) + '</span>';
      }).join('');

      var evidence = (s.evidence || []).slice(0, 3).map(function (e) {
        return '<blockquote>' + esc(e) + '</blockquote>';
      }).join('');

      return '<div class="stance" data-canonical="' + esc(s.canonical) + '"' +
        (empty ? ' style="opacity:.55" ' : ' style="border-left-color:' + colors[i % colors.length] + '"') + '>' +
        '<div class="head">' +
        '<span class="name">' + esc(s.canonical) + '</span>' +
        (empty
          ? '<span class="pill faint">本次样本中未出现</span>'
          : '<span class="pill cyan">' + (s.pct || 0).toFixed(1) + '%</span>' +
            '<span class="pill">' + (s.count || 0) + ' 条</span>' +
            '<span class="pill">构成 ' + (s.share || 0).toFixed(1) + '%</span>') +
        (s.weighted_pct ? '<span class="pill">点赞加权 ' + s.weighted_pct.toFixed(1) + '%</span>' : '') +
        (typeof s.x === 'number'
          ? '<span class="pill faint">轴位 ' + s.x.toFixed(2) +
            (s.left_affinity != null
              ? ' <span title="左端贴合 / 右端贴合">(' + s.left_affinity + '/' + s.right_affinity + ')</span>'
              : '') +
            '</span>'
          : '') +
        '</div>' +
        '<p class="logic">' + esc(s.core_logic || '') + '</p>' +
        (opinions ? '<div class="aliases">' + opinions + moreOps + '</div>' : '') +
        (slang ? '<div class="aliases" style="margin-top:6px">' +
          '<span class="faint" style="font-size:11px;margin-right:4px">圈内词</span>' + slang + '</div>' : '') +
        evidence +
        '</div>';
    }).join('');
  }

  /* ---------------------------------------------------------------- 报告 */

  function renderReport(d) {
    var jury = d.jury || {};
    var html = '';

    function propRow(p) {
      var scores = Object.keys(p.scores || {}).map(function (k) {
        var v = p.scores[k];
        var color = v >= 70 ? '#6bc98a' : (v <= 35 ? '#e06c75' : '#8b97a8');
        return '<span class="pill" style="color:' + color + ';border-color:' + color + '">' + esc(k) + ' ' + v + '</span>';
      }).join(' ');
      return '<div style="padding:10px 0;border-bottom:1px solid #232a37">' +
        '<div style="margin-bottom:6px">' + esc(p.text) + '</div>' +
        '<div style="display:flex;gap:6px;flex-wrap:wrap">' + scores + '</div>' +
        '<div class="mono faint" style="font-size:11px;margin-top:6px">' +
        '均值 ' + p.mean + ' · 标准差 ' + p.stdev + ' · 区间 ' + p.lowest + '~' + p.highest + '</div>' +
        '</div>';
    }

    if (jury.consensus && jury.consensus.length) {
      html += '<h4 style="color:#6bc98a;margin:16px 0 4px">✓ 共识（所有立场都认同）</h4>';
      html += jury.consensus.map(propRow).join('');
    }
    if (jury.cleavage && jury.cleavage.length) {
      html += '<h4 style="color:#e06c75;margin:20px 0 4px">✗ 撕裂点（立场间分歧最大）</h4>';
      html += jury.cleavage.map(propRow).join('');
    }
    (jury.notes || []).forEach(function (n) { html += note('warn', esc(n)); });
    if (!html) html = '<p class="faint">还没有陪审团数据。</p>';

    $('juryBody').innerHTML = html;
    $('reportBodyMd').innerHTML = window.LDMarkdown.render(d.report || '');
  }

  $('btnExport').addEventListener('click', function () {
    if (!state.runId) return;
    window.location.href = '/api/export/' + encodeURIComponent(state.runId) + '.md';
  });

  $('btnCopy').addEventListener('click', function () {
    if (!state.data || !state.data.report) return;
    navigator.clipboard.writeText(state.data.report).then(function () {
      var btn = $('btnCopy');
      var old = btn.textContent;
      btn.textContent = '已复制';
      setTimeout(function () { btn.textContent = old; }, 1500);
    });
  });

  /* ---------------------------------------------------------------- 提示词 */

  function loadPrompts() {
    return api('/api/prompts').then(function (r) {
      $('promptList').innerHTML = r.prompts.map(function (p) {
        return '<button data-name="' + esc(p.name) + '"' + (p.name === state.currentPrompt ? ' class="active"' : '') + '>' +
          esc(p.name) + '</button>';
      }).join('');

      $('promptList').querySelectorAll('button').forEach(function (btn) {
        btn.addEventListener('click', function () {
          state.currentPrompt = btn.dataset.name;
          loadPrompts();
        });
      });

      return api('/api/prompts/' + encodeURIComponent(state.currentPrompt));
    }).then(function (p) {
      $('promptEditor').value = p.content;
      $('promptStatus').textContent = '';
    });
  }

  $('btnSavePrompt').addEventListener('click', function () {
    var btn = this;
    btn.disabled = true;
    api('/api/prompts/' + encodeURIComponent(state.currentPrompt), {
      method: 'PUT',
      json: { content: $('promptEditor').value }
    }).then(function (r) {
      $('promptStatus').innerHTML = '<span style="color:#6bc98a">已保存（指纹 ' + esc(r.fingerprint) + '）。改完记得在「分析」页勾选对应阶段重跑。</span>';
    }).catch(function (err) {
      $('promptStatus').innerHTML = '<span style="color:#e06c75">' + esc(err.message) + '</span>';
    }).finally(function () {
      btn.disabled = false;
    });
  });

  /* ---------------------------------------------------------------- 启动 */

  loadStatus().then(loadRuns).then(loadPrompts).then(function () {
    return loadStatus();
  }).catch(function (err) {
    console.error(err);
  });

})();
