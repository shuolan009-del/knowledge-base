/* ==========================================================================
   掌柜智库 · 前端站点  (app.js)   —— 多页共享脚本
   零构建 · 原生 JS · 无第三方依赖
   --------------------------------------------------------------------------
   站点页面：index.html / import.html / chat.html / workflow.html
   本脚本被四个页面共用，采用「按页初始化」：每个模块先自检必要元素，
   不存在则直接跳过，因此任一页面缺失某个模块的 DOM 也不会报错。

   模块划分：
     0. CONFIG        —— 集中式后端地址配置（可被 URL 参数 / 本地设置覆盖）
     1. utils         —— 通用工具
     2. nav           —— 导航（真实跳转 + 当前页高亮）、滚动揭示
     3. health        —— 双服务健康检查
     4. importModule  —— 建库：上传 + 任务进度 + 节点可视化（仅 import.html）
     5. chatModule    —— 对话检索：流式 / 历史 / 清空 / 配图（仅 chat.html）
     6. authModule    —— 纯前端登录门禁（checkAuth / submitLogin / logout）
     7. userMenu      —— 登录后右上角用户区（头像 / 用户名 / 状态 / 退出）
     8. settings      —— 服务地址设置弹窗
   ========================================================================== */

(() => {
  'use strict';

  /* ======================================================================
     0. CONFIG —— 后端地址集中配置
     ====================================================================== */
  const CONFIG = {
    importBase: 'http://127.0.0.1:8000', // 导入服务
    queryBase: 'http://127.0.0.1:8001',  // 查询服务
    pollInterval: 2000,                  // 任务状态轮询间隔 (ms)
    healthInterval: 5000,                // 健康检查间隔 (ms)
    storageKeys: {
      import: 'kb.importBase',
      query: 'kb.queryBase',
      session: 'kb_session_id',
      auth: 'kb.auth',
    },
  };

  /**
   * 前端登录门禁的默认账号（⚠️ 纯前端，仅供演示/内网使用，无真实鉴权）。
   * 日后接入真实后端时，只需替换 authModule 中的校验与持久化实现。
   */
  const AUTH = {
    user: 'admin',
    pass: 'kb2024',
    okValue: 'ok',
  };

  /** 解析最终生效的地址：URL 参数 > localStorage > 默认值 */
  function resolveBases() {
    const params = new URLSearchParams(location.search);
    const lsImport = localStorage.getItem(CONFIG.storageKeys.import);
    const lsQuery = localStorage.getItem(CONFIG.storageKeys.query);
    return {
      import: (params.get('import') || lsImport || CONFIG.importBase).replace(/\/+$/, ''),
      query: (params.get('query') || lsQuery || CONFIG.queryBase).replace(/\/+$/, ''),
    };
  }
  let BASES = resolveBases();

  /* ======================================================================
     1. utils
     ====================================================================== */
  const $ = (sel, root = document) => root.querySelector(sel);

  function escapeHtml(str) {
    return String(str == null ? '' : str)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function nowTime() {
    return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }

  function formatTime(ts) {
    if (!ts) return nowTime();
    const d = new Date(Number(ts) * 1000);
    if (Number.isNaN(d.getTime())) return nowTime();
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }

  function formatSize(bytes) {
    if (bytes == null) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  }

  function dedupeKeepOrder(arr) {
    const seen = new Set();
    const out = [];
    for (const x of Array.isArray(arr) ? arr : []) {
      const v = String(x || '');
      if (!v || seen.has(v)) continue;
      seen.add(v);
      out.push(v);
    }
    return out;
  }

  /* ======================================================================
     2. nav —— 导航 / 当前页高亮 / 滚动揭示
     ====================================================================== */
  function currentPageFile() {
    const file = (location.pathname.split('/').pop() || '').toLowerCase();
    return file || 'index.html';
  }

  /** 根据当前 URL 给导航中的对应链接加高亮 */
  function markActiveNav() {
    const file = currentPageFile();
    document.querySelectorAll('.nav-links a, .mobile-menu a').forEach((a) => {
      const href = (a.getAttribute('href') || '').split('/').pop().toLowerCase();
      const isActive = href === file;
      a.classList.toggle('is-active', isActive);
      if (isActive) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
  }

  function initNav() {
    const nav = $('#nav');
    const burger = $('#btnBurger');
    const mobileMenu = $('#mobileMenu');

    if (nav) {
      const onScroll = () => nav.classList.toggle('is-scrolled', window.scrollY > 8);
      onScroll();
      window.addEventListener('scroll', onScroll, { passive: true });
    }

    if (burger && mobileMenu) {
      burger.addEventListener('click', () => {
        const open = burger.getAttribute('aria-expanded') === 'true';
        burger.setAttribute('aria-expanded', String(!open));
        mobileMenu.hidden = open;
      });
      mobileMenu.querySelectorAll('a').forEach((a) =>
        a.addEventListener('click', () => {
          burger.setAttribute('aria-expanded', 'false');
          mobileMenu.hidden = true;
        })
      );
    }

    markActiveNav();
  }

  let revealObserver = null;

  function initReveal() {
    const els = Array.from(document.querySelectorAll('.reveal'));
    if (!('IntersectionObserver' in window)) {
      els.forEach((el) => el.classList.add('is-visible'));
      return;
    }
    revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, i) => {
          if (!entry.isIntersecting) return;
          const delay = Math.min(i * 70, 210);
          setTimeout(() => entry.target.classList.add('is-visible'), delay);
          revealObserver.unobserve(entry.target);
        });
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.12 }
    );
    els.forEach((el) => revealObserver.observe(el));
  }

  /**
   * 内容曾被隐藏（登录门禁）时 IntersectionObserver 可能不会再次回调；
   * 解锁后需要把尚未揭示的元素重新处理一遍。
   *
   * ⚠️ 关键点：observe() 对「已在观察列表中的目标」是无操作，直接再调用一次
   * 不会触发新的回调 —— 这正是「登录后首屏元素 opacity 仍为 0」的原因。
   * 因此这里先 unobserve 再决定：视口内的元素立即（错峰）揭示，
   * 视口外的重新 observe，交由滚动触发。
   */
  function refreshReveals() {
    const pending = document.querySelectorAll('.reveal:not(.is-visible)');
    if (!revealObserver) {
      pending.forEach((el) => el.classList.add('is-visible'));
      return;
    }
    const vh = window.innerHeight || document.documentElement.clientHeight;
    let i = 0;
    pending.forEach((el) => {
      const r = el.getBoundingClientRect();
      const inView = r.top < vh * 0.92 && r.bottom > 0;
      revealObserver.unobserve(el); // 必须先移除，才能强制重新计算相交状态
      if (inView) {
        const delay = Math.min(i++ * 70, 210);
        setTimeout(() => el.classList.add('is-visible'), delay);
      } else {
        revealObserver.observe(el);
      }
    });
  }

  /* ======================================================================
     3. health —— 双服务健康检查（芯片位于页脚）
     ====================================================================== */
  function setChip(el, ok, label) {
    if (!el) return;
    el.innerHTML = `<i class="dot ${ok ? 'dot-ok' : 'dot-err'}"></i>${escapeHtml(label)} ${ok ? '已连接' : '未连接'}`;
  }

  function initHealth() {
    const pillImport = $('#pillImport');
    const pillQuery = $('#pillQuery');
    const apiPill = chatModule.getApiPill();

    async function check(base, path) {
      try {
        const res = await fetch(`${base}${path}`, { method: 'GET' });
        return res.ok;
      } catch (_) {
        return false;
      }
    }

    async function run() {
      const [impOk, qryOk] = await Promise.all([
        check(BASES.import, '/import.html'),
        check(BASES.query, '/health'),
      ]);
      setChip(pillImport, impOk, '导入服务');
      setChip(pillQuery, qryOk, '查询服务');
      if (apiPill) {
        apiPill.textContent = qryOk ? 'API: 已连接' : 'API: 未连接';
        apiPill.classList.toggle('is-ok', qryOk);
      }
    }

    run();
    setInterval(run, CONFIG.healthInterval);
  }

  /* ======================================================================
     4. importModule —— 建库（仅 import.html；内部自检，缺元素即跳过）
     ====================================================================== */

  // 导入流水线标准节点（用于把后端返回的中文标签映射成规整的步骤条）
  const IMPORT_STAGES = [
    { key: 'upload', label: '上传文件', match: ['上传'] },
    { key: 'check', label: '检查文件', match: ['检查'] },
    { key: 'parse', label: '文档解析', match: ['pdf', '解析', '转换'] },
    { key: 'image', label: '图片处理', match: ['图片'] },
    { key: 'split', label: '文档切分', match: ['切分', '分段', 'split'] },
    { key: 'name', label: '主体识别', match: ['名称', '主体', '识别'] },
    { key: 'embed', label: '向量生成', match: ['向量生成', 'embed', 'bge', '向量'] },
    { key: 'milvus', label: '导入向量库', match: ['导入向量库', '向量库', 'milvus', '入库'] },
  ];

  /** 把一条中文节点标签映射到标准阶段索引（取最长关键词命中）。返回 null 表示未匹配。 */
  function matchStage(label, usedKeys) {
    const s = String(label || '').toLowerCase();
    let best = null;
    let bestLen = 0;
    IMPORT_STAGES.forEach((stage, idx) => {
      if (usedKeys.has(stage.key)) return;
      for (const kw of stage.match) {
        if (s.includes(kw.toLowerCase()) && kw.length > bestLen) {
          best = idx;
          bestLen = kw.length;
        }
      }
    });
    return best;
  }

  /** 计算每个标准阶段的状态：done / running / pending，并收集未匹配的额外标签。 */
  function computeStages(doneList, runningList) {
    const done = Array.isArray(doneList) ? doneList : [];
    const running = Array.isArray(runningList) ? runningList : [];
    const states = IMPORT_STAGES.map(() => 'pending');
    const used = new Set();
    const extrasDone = [];
    const extrasRunning = [];

    done.forEach((lbl) => {
      const idx = matchStage(lbl, used);
      if (idx == null) extrasDone.push(lbl);
      else { states[idx] = 'done'; used.add(IMPORT_STAGES[idx].key); }
    });
    running.forEach((lbl) => {
      const idx = matchStage(lbl, used);
      if (idx == null) extrasRunning.push(lbl);
      else { if (states[idx] !== 'done') states[idx] = 'running'; used.add(IMPORT_STAGES[idx].key); }
    });

    return { states, extrasDone, extrasRunning };
  }

  const importModule = (() => {
    let dropZone, fileInput, btnPick, taskList, taskEmpty, taskSummary, btnClearTasks;
    let taskCount = 0;
    let activeCount = 0;

    function updateSummary() {
      if (!taskSummary || !taskEmpty) return;
      if (taskCount === 0) {
        taskSummary.textContent = '尚未上传任务';
        taskEmpty.hidden = false;
      } else {
        taskSummary.textContent = activeCount > 0
          ? `${taskCount} 个任务 · ${activeCount} 个处理中`
          : `${taskCount} 个任务 · 全部完成`;
        taskEmpty.hidden = true;
      }
    }

    function createTaskCard(file) {
      const el = document.createElement('div');
      el.className = 'task-card';
      el.innerHTML = `
        <div class="task-top">
          <div class="task-file">
            <div class="task-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div>
            <div class="task-size">${formatSize(file.size)}</div>
          </div>
          <span class="badge badge-uploading">上传中…</span>
        </div>
        <div class="progress-track"><div class="progress-fill is-active" style="width:8%"></div></div>
        <div class="stepper"></div>
        <details class="log-box">
          <summary>节点日志</summary>
          <ul class="log-list"><li class="is-empty">等待服务返回进度…</li></ul>
        </details>
      `;
      taskList.prepend(el);
      return el;
    }

    function setBadge(el, kind, text) {
      const badge = el.querySelector('.badge');
      if (badge) { badge.className = `badge badge-${kind}`; badge.textContent = text; }
    }

    function setProgress(el, pct, active) {
      const fill = el.querySelector('.progress-fill');
      if (!fill) return;
      fill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
      fill.classList.toggle('is-active', !!active);
      if (!active) fill.style.backgroundColor = 'var(--brand)';
    }

    function renderStepper(el, doneList, runningList) {
      const { states, extrasDone, extrasRunning } = computeStages(doneList, runningList);
      const box = el.querySelector('.stepper');
      if (!box) return 0;
      box.innerHTML = '';

      IMPORT_STAGES.forEach((stage, idx) => {
        const state = states[idx];
        const span = document.createElement('span');
        span.className = `step ${state === 'done' ? 'is-done' : state === 'running' ? 'is-running' : ''}`;
        span.innerHTML = `<span class="step-ico">${state === 'done' ? '✓' : ''}</span>${escapeHtml(stage.label)}`;
        box.appendChild(span);
      });
      // 后端返回但不在标准流水线内的节点，照样展示，保证零遗漏
      extrasDone.forEach((lbl) => {
        const span = document.createElement('span');
        span.className = 'step is-done';
        span.innerHTML = `<span class="step-ico">✓</span>${escapeHtml(lbl)}`;
        box.appendChild(span);
      });
      extrasRunning.forEach((lbl) => {
        const span = document.createElement('span');
        span.className = 'step is-running';
        span.innerHTML = `<span class="step-ico"></span>${escapeHtml(lbl)}`;
        box.appendChild(span);
      });

      return states.filter((s) => s === 'done').length + extrasDone.length;
    }

    function renderLogs(el, doneList, runningList) {
      const ul = el.querySelector('.log-list');
      const summary = el.querySelector('.log-box summary');
      if (!ul) return;
      const done = Array.isArray(doneList) ? doneList : [];
      const running = Array.isArray(runningList) ? runningList : [];
      if (summary) summary.textContent = `节点日志（完成 ${done.length} · 进行中 ${running.length}）`;
      ul.innerHTML = '';
      const lines = [
        ...done.map((t) => ({ text: String(t), running: false })),
        ...running.map((t) => ({ text: String(t), running: true })),
      ];
      if (lines.length === 0) {
        ul.innerHTML = '<li class="is-empty">等待服务返回进度…</li>';
        return;
      }
      for (const line of lines) {
        const li = document.createElement('li');
        li.className = line.running ? 'is-running' : '';
        li.textContent = line.text;
        ul.appendChild(li);
      }
    }

    async function uploadFile(file) {
      const card = createTaskCard(file);
      taskCount += 1;
      activeCount += 1;
      updateSummary();
      setProgress(card, 12, true);

      const formData = new FormData();
      formData.append('files', file);

      try {
        const res = await fetch(`${BASES.import}/upload`, { method: 'POST', body: formData });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const taskId = (data.task_ids && data.task_ids[0]) || null;
        if (!taskId) throw new Error('未返回 task_id');

        setBadge(card, 'processing', '处理中…');
        setProgress(card, 20, true);
        pollStatus(taskId, card);
      } catch (err) {
        console.error('[upload]', err);
        setBadge(card, 'failed', '失败');
        setProgress(card, 0, false);
        const fill = card.querySelector('.progress-fill');
        if (fill) fill.style.backgroundColor = 'var(--err)';
        activeCount = Math.max(0, activeCount - 1);
        updateSummary();
      }
    }

    function pollStatus(taskId, card) {
      const timer = setInterval(async () => {
        try {
          const res = await fetch(`${BASES.import}/status/${taskId}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();

          const doneCount = renderStepper(card, data.done_list, data.running_list);
          renderLogs(card, data.done_list, data.running_list);
          const pct = Math.round((doneCount / IMPORT_STAGES.length) * 92) + 6;

          if (data.status === 'completed') {
            clearInterval(timer);
            setBadge(card, 'completed', '已完成');
            setProgress(card, 100, false);
            activeCount = Math.max(0, activeCount - 1);
            updateSummary();
          } else if (data.status === 'failed') {
            clearInterval(timer);
            setBadge(card, 'failed', '失败');
            setProgress(card, pct, false);
            const fill = card.querySelector('.progress-fill');
            if (fill) fill.style.backgroundColor = 'var(--err)';
            activeCount = Math.max(0, activeCount - 1);
            updateSummary();
          } else {
            setProgress(card, pct, true);
          }
        } catch (err) {
          console.error('[poll]', err);
        }
      }, CONFIG.pollInterval);
    }

    function handleFiles(files) {
      Array.from(files || []).forEach((f) => {
        if (!/\.(pdf|md)$/i.test(f.name)) {
          alert(`暂不支持该文件类型：${f.name}\n仅支持 .pdf / .md`);
          return;
        }
        uploadFile(f);
      });
    }

    function init() {
      dropZone = $('#dropZone');
      if (!dropZone) return; // 本页没有建库模块 → 跳过
      fileInput = $('#fileInput');
      btnPick = $('#btnPick');
      taskList = $('#taskList');
      taskEmpty = $('#taskEmpty');
      taskSummary = $('#taskSummary');
      btnClearTasks = $('#btnClearTasks');

      dropZone.addEventListener('click', () => fileInput && fileInput.click());
      dropZone.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (fileInput) fileInput.click(); }
      });
      if (btnPick) btnPick.addEventListener('click', () => fileInput && fileInput.click());
      if (fileInput) {
        fileInput.addEventListener('change', (e) => {
          handleFiles(e.target.files);
          fileInput.value = '';
        });
      }

      ['dragenter', 'dragover'].forEach((ev) =>
        dropZone.addEventListener(ev, (e) => {
          e.preventDefault();
          dropZone.classList.add('is-drag');
        })
      );
      ['dragleave', 'drop'].forEach((ev) =>
        dropZone.addEventListener(ev, (e) => {
          e.preventDefault();
          if (ev === 'dragleave' && dropZone.contains(e.relatedTarget)) return;
          dropZone.classList.remove('is-drag');
        })
      );
      dropZone.addEventListener('drop', (e) => handleFiles(e.dataTransfer.files));

      // 阻止页面其它区域拖放时浏览器直接打开文件
      ['dragover', 'drop'].forEach((ev) =>
        window.addEventListener(ev, (e) => { if (e.target !== dropZone) e.preventDefault(); })
      );

      if (btnClearTasks && taskList) {
        btnClearTasks.addEventListener('click', () => {
          taskList.querySelectorAll('.task-card').forEach((card) => {
            if (card.querySelector('.badge-completed') || card.querySelector('.badge-failed')) card.remove();
          });
          taskCount = taskList.querySelectorAll('.task-card').length;
          activeCount = taskList.querySelectorAll('.badge-uploading, .badge-processing').length;
          updateSummary();
        });
      }

      updateSummary();
    }

    return { init };
  })();

  /* ======================================================================
     5. chatModule —— 对话检索（仅 chat.html；内部自检）
     消息容器 id 为 chatLog（历史遗留问题：曾与 #chat 区块 id 冲突）
     ====================================================================== */
  const chatModule = (() => {
    let chatEl, inputEl, sendBtn, apiPill, btnClear, streamToggle;

    let sessionId = localStorage.getItem(CONFIG.storageKeys.session);
    if (!sessionId) {
      sessionId = 'sess-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(CONFIG.storageKeys.session, sessionId);
    }

    const isImageUrl = (url) => {
      try {
        return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(new URL(url).pathname);
      } catch (_) {
        return /\.(png|jpe?g|gif|webp|bmp|svg)(\?|#|$)/i.test(url || '');
      }
    };
    const normalizeUrl = (raw) => String(raw || '').trim().replace(/\s/g, '%20');

    function extractUrlsLoose(text) {
      const matches = String(text || '').match(/(https?:\/\/[^\s]+)/g) || [];
      const trimTail = (u) => u.replace(/[)\]}'">，。,;；\]】）＞]+$/g, '');
      const trimHead = (u) => u.replace(/^[<([{'"]+|^[＜（【\[]+/g, '');
      return dedupeKeepOrder(matches.map((m) => trimHead(trimTail(m))).filter(Boolean));
    }

    function parseAnswerAndImages(text) {
      const raw = String(text || '');
      const re = /【\s*图片\s*】|\[\s*图片\s*\]/g;
      let m, lastIdx = -1, lastLen = 0;
      while ((m = re.exec(raw)) !== null) { lastIdx = m.index; lastLen = m[0].length; }
      if (lastIdx === -1) return { text: raw, images: [] };

      const before = raw.slice(0, lastIdx).trimEnd();
      const after = raw.slice(lastIdx + lastLen).trim();
      const urls = [];
      after.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).forEach((line) => {
        if (line.startsWith('http://') || line.startsWith('https://')) urls.push(line);
        else urls.push(...extractUrlsLoose(line));
      });
      return { text: before, images: dedupeKeepOrder(urls.map(normalizeUrl).filter(isImageUrl)) };
    }

    function renderAnswer(containerEl, answerText, candidateImageUrls) {
      if (!containerEl) return;
      const { text, images: blockImages } = parseAnswerAndImages(answerText);
      const candidates = (Array.isArray(candidateImageUrls) ? candidateImageUrls : [])
        .map(normalizeUrl).filter(isImageUrl);
      const loose = extractUrlsLoose(answerText).map(normalizeUrl).filter(isImageUrl);
      const images = dedupeKeepOrder([...blockImages, ...candidates, ...loose]);

      containerEl.textContent = '';
      const textEl = document.createElement('div');
      textEl.className = 'answer-text';
      textEl.textContent = (text || '').trim() || '（已完成，但未返回答案）';
      containerEl.appendChild(textEl);

      if (images.length) {
        const wrap = document.createElement('div');
        wrap.className = 'answer-images';
        images.forEach((url) => {
          const img = document.createElement('img');
          img.loading = 'lazy';
          img.src = url;
          img.alt = '参考图片';
          img.referrerPolicy = 'no-referrer';
          img.addEventListener('error', () => { img.style.display = 'none'; });
          wrap.appendChild(img);

          const link = document.createElement('a');
          link.href = url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = url;
          wrap.appendChild(link);
        });
        containerEl.appendChild(wrap);
      }
    }

    function scrollToBottom() { if (chatEl) chatEl.scrollTop = chatEl.scrollHeight; }

    function addUserMsg(text, ts) {
      const el = document.createElement('div');
      el.className = 'msg user';
      el.innerHTML = `
        <div class="avatar">我</div>
        <div class="msg-body">
          <div class="bubble">${escapeHtml(text)}</div>
          <div class="meta">${formatTime(ts)}</div>
        </div>`;
      chatEl.appendChild(el);
      scrollToBottom();
    }

    function addBotHistory(text, ts, imageUrls) {
      const el = document.createElement('div');
      el.className = 'msg bot';
      el.innerHTML = `
        <div class="avatar bot">智库</div>
        <div class="msg-body">
          <div class="bubble"><div class="answer"></div></div>
          <div class="meta">${formatTime(ts)}</div>
        </div>`;
      chatEl.appendChild(el);
      renderAnswer(el.querySelector('.answer'), text || '', imageUrls || []);
      scrollToBottom();
    }

    function addBotSkeleton() {
      const el = document.createElement('div');
      el.className = 'msg bot';
      el.innerHTML = `
        <div class="avatar bot">智库</div>
        <div class="msg-body" style="min-width:200px">
          <div class="bubble">
            <span class="typing"><span class="tdot"></span><span class="tdot"></span><span class="tdot"></span></span>
            <details class="progress-block" open>
              <summary>阶段进度（等待中）</summary>
              <ul><li>正在准备…</li></ul>
            </details>
          </div>
          <div class="meta">${nowTime()}</div>
        </div>`;
      chatEl.appendChild(el);
      scrollToBottom();
      return el;
    }

    const STATUS_MAP = { processing: '处理中', completed: '已完成', failed: '失败', pending: '等待中' };

    function renderProgress(botEl, doneList, runningList, status) {
      const details = botEl.querySelector('details.progress-block');
      if (!details) return;
      const summary = details.querySelector('summary');
      const ul = details.querySelector('ul');
      const done = Array.isArray(doneList) ? doneList : [];
      const running = Array.isArray(runningList) ? runningList : [];
      if (summary) summary.textContent = `阶段进度（完成 ${done.length} · 进行中 ${running.length} · 状态：${STATUS_MAP[status] || status || '未知'}）`;
      if (!ul) return;
      ul.innerHTML = '';
      const lines = [
        ...done.map((x) => ({ t: x, cls: 'is-done' })),
        ...running.map((x) => ({ t: x, cls: 'is-run' })),
      ];
      if (!lines.length) { ul.innerHTML = '<li>暂无进度</li>'; return; }
      lines.forEach((l) => {
        const li = document.createElement('li');
        li.className = l.cls;
        li.textContent = l.t;
        ul.appendChild(li);
      });
    }

    function finishTyping(botEl) {
      const t = botEl.querySelector('.typing');
      if (t) t.remove();
      const p = botEl.querySelector('details.progress-block');
      if (p) p.removeAttribute('open');
    }

    function finalizeAnswer(botEl, answer, error, imageUrls) {
      const bubble = botEl.querySelector('.bubble');
      const progress = botEl.querySelector('details.progress-block');
      const err = (error || '').trim();
      bubble.textContent = '';
      const box = document.createElement('div');
      box.className = 'answer';
      if (err) box.textContent = `抱歉，本次处理失败：\n${err}`;
      else renderAnswer(box, answer || '', imageUrls || []);
      bubble.appendChild(box);
      if (progress) bubble.appendChild(progress);
    }

    async function loadHistory() {
      if (!chatEl) return;
      try {
        const res = await fetch(`${BASES.query}/history/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        const items = Array.isArray(data.items) ? data.items : [];
        if (!items.length) return;
        const nodes = Array.from(chatEl.querySelectorAll('.msg'));
        for (let i = 1; i < nodes.length; i++) nodes[i].remove(); // 保留欢迎语
        items.forEach((item) => {
          if (item.role === 'user') addUserMsg(item.text || '', item.ts);
          else addBotHistory(item.text || '', item.ts, item.image_urls || []);
        });
        scrollToBottom();
      } catch (_) { /* 后端不可用时静默 */ }
    }

    async function submitQuery(text) {
      const isStream = streamToggle.checked;
      const res = await fetch(`${BASES.query}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text, session_id: sessionId, is_stream: isStream }),
      });
      if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
      return res.json();
    }

    async function onSend() {
      const text = (inputEl.value || '').trim();
      if (!text) return;
      inputEl.value = '';
      inputEl.style.height = 'auto';
      addUserMsg(text);
      const botEl = addBotSkeleton();
      sendBtn.disabled = true;
      const isStream = streamToggle.checked;

      try {
        const data = await submitQuery(text);
        renderProgress(botEl, [], [], 'pending');

        if (!isStream) {
          renderProgress(botEl, data.done_list || [], [], 'completed');
          finishTyping(botEl);
          finalizeAnswer(botEl, data.answer, data.error, data.image_urls || []);
          sendBtn.disabled = false;
          return;
        }

        const { session_id: sid } = data;
        const bubble = botEl.querySelector('.bubble');
        let answerEl = bubble.querySelector('.answer');
        if (!answerEl) {
          answerEl = document.createElement('div');
          answerEl.className = 'answer';
          bubble.insertBefore(answerEl, bubble.firstChild);
        }

        const es = new EventSource(`${BASES.query}/stream/${sid}`);
        let raw = '';
        const closeAll = () => { finishTyping(botEl); try { es.close(); } catch (_) {} sendBtn.disabled = false; };

        es.addEventListener('ready', () => {
          try { renderProgress(botEl, [], [], 'processing'); } catch (_) {}
        });

        es.addEventListener('progress', (e) => {
          try {
            const d = JSON.parse(e.data || '{}');
            renderProgress(botEl, d.done_list, d.running_list, d.status);
            if (d && d.status === 'completed') closeAll();
          } catch (_) {}
        });

        es.addEventListener('delta', (e) => {
          try {
            const d = JSON.parse(e.data || '{}');
            if (d.delta) {
              raw += d.delta;
              renderAnswer(answerEl, raw, []);
              scrollToBottom();
            }
          } catch (_) {}
        });

        ['final', 'final_answer'].forEach((evt) =>
          es.addEventListener(evt, (e) => {
            finishTyping(botEl);
            try {
              const d = JSON.parse(e.data || '{}');
              const finalText = (d && typeof d.answer === 'string' && d.answer.trim()) ? d.answer : (raw || '');
              renderAnswer(answerEl, finalText, d.image_urls || []);
            } catch (_) {
              renderAnswer(answerEl, raw, []);
            }
            try { es.close(); } catch (_) {}
            sendBtn.disabled = false;
          })
        );

        es.addEventListener('error', (e) => {
          finishTyping(botEl);
          let msg = 'SSE 连接中断/失败';
          try { if (e && e.data) msg = JSON.parse(e.data).error || msg; } catch (_) {}
          raw += `\n\n（错误：${msg}）`;
          renderAnswer(answerEl, raw, []);
          try { es.close(); } catch (_) {}
          sendBtn.disabled = false;
        });
      } catch (e) {
        console.error('[query]', e);
        finishTyping(botEl);
        const bubble = botEl.querySelector('.bubble');
        const progress = botEl.querySelector('details.progress-block');
        bubble.innerHTML = `<div class="answer">请求失败：${escapeHtml(e.message || e)}</div>`;
        if (progress) bubble.appendChild(progress);
        sendBtn.disabled = false;
      }
    }

    async function clearHistory() {
      if (!confirm('确定要清空当前会话的历史记录吗？此操作不可恢复。')) return;
      try {
        const res = await fetch(`${BASES.query}/history/${sessionId}`, { method: 'DELETE' });
        if (!res.ok) alert('服务端清空失败，仅清空本地显示');
      } catch (_) {
        alert('服务端清空失败，仅清空本地显示');
      }
      const nodes = Array.from(chatEl.querySelectorAll('.msg'));
      for (let i = 1; i < nodes.length; i++) nodes[i].remove();
      scrollToBottom();
    }

    function autoGrow() {
      inputEl.style.height = 'auto';
      inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + 'px';
    }

    function init() {
      chatEl = $('#chatLog');       // ⚠️ 唯一消息容器 id（不要再叫 chat）
      if (!chatEl) return;          // 本页没有对话模块 → 跳过
      inputEl = $('#input');
      sendBtn = $('#send');
      apiPill = $('#apiPill');
      btnClear = $('#btnClear');
      streamToggle = $('#streamToggle');

      if (sendBtn) sendBtn.addEventListener('click', onSend);
      if (inputEl) {
        inputEl.addEventListener('input', autoGrow);
        inputEl.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); }
        });
      }
      if (btnClear) btnClear.addEventListener('click', clearHistory);

      loadHistory();
      setTimeout(() => inputEl && inputEl.focus(), 300);
    }

    function reload() { loadHistory(); }

    return { init, reload, getApiPill: () => apiPill };
  })();

  /* ======================================================================
     6. authModule —— 登录门禁已取消（2026-10-13 禾语农产品平台改造）
     ----------------------------------------------------------------------
     按平台要求，禾语农产品知识库允许直接访问，不再有前端登录门禁：
       - isAuthed() 恒 true；applyState() 恒为已授权态（用户区常驻）
       - 原「退出登录」语义改为「返回禾语农产品门户」（平台统一入口）
     历史实现（前端常量账号 + localStorage 门禁）已废弃，保留函数签名
     以便未来如需恢复门禁时低成本回退。
     ====================================================================== */
  const authModule = (() => {
    let form, userEl, passEl, errEl, card;

    function isAuthed() {
      return true; // 登录门禁已取消：允许直接访问
    }

    /** 授权态 → <html> class + 右上角用户区显隐（内容显隐完全由 CSS 决定） */
    function applyState(authed) {
      const root = document.documentElement;
      root.classList.toggle('is-authed', true);
      root.classList.remove('is-locked');
      const userMenu = $('#userMenu');
      if (userMenu) userMenu.hidden = false;
      if (authed !== false) refreshReveals();
    }

    function showError(msg) {
      if (!errEl) return;
      errEl.textContent = msg;
      errEl.classList.add('is-show');
      if (card) {
        card.classList.remove('is-shake');
        void card.offsetWidth; // 强制重排以重启动画
        card.classList.add('is-shake');
      }
    }

    function clearError() {
      if (errEl) { errEl.textContent = ''; errEl.classList.remove('is-show'); }
      if (card) card.classList.remove('is-shake');
    }

    function checkAuth() { applyState(isAuthed()); }

    /** 登录已取消：保留入口以防未来恢复；当前直接放行 */
    function submitLogin(e) {
      if (e) e.preventDefault();
      applyState(true);
    }

    /** 「退出登录」已取消：改为返回禾语农产品智能商管平台门户 */
    function logout() {
      try { localStorage.removeItem(CONFIG.storageKeys.auth); } catch (_) {}
      window.open('http://127.0.0.1:5174/', '_blank', 'noopener');
    }

    /** 带二次确认的「返回门户」（供用户区菜单 / 设置弹窗调用） */
    function requestLogout(msg) {
      if (!confirm(msg || '确定要返回禾语农产品智能商管平台门户吗？')) return;
      logout();
    }

    function init() {
      form = $('#loginForm');
      userEl = $('#loginUser');
      passEl = $('#loginPass');
      errEl = $('#loginError');
      card = $('.login-card');

      checkAuth();
      if (form) form.addEventListener('submit', submitLogin);
      [userEl, passEl].forEach((el) => el && el.addEventListener('input', clearError));
    }

    return { init, isAuthed, submitLogin, logout, requestLogout, applyState };
  })();

  /* ======================================================================
     7. userMenu —— 登录后右上角用户区
     ====================================================================== */
  function initUserMenu() {
    const wrap = $('#userMenu');
    const trigger = $('#userTrigger');
    const dropdown = $('#userDropdown');
    const logoutBtn = $('#btnLogoutMenu');
    if (!wrap || !trigger || !dropdown) return;

    const name = AUTH.user || 'user';
    // 用 data 属性填充，允许触发按钮与下拉菜单里同时出现用户名/头像，且不产生重复 id
    document.querySelectorAll('[data-user-name]').forEach((el) => { el.textContent = name; });
    document.querySelectorAll('[data-user-avatar]').forEach((el) => { el.textContent = name.charAt(0).toUpperCase(); });

    const close = () => {
      dropdown.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
    };
    const toggle = () => {
      const open = trigger.getAttribute('aria-expanded') === 'true';
      trigger.setAttribute('aria-expanded', String(!open));
      dropdown.hidden = open;
    };

    trigger.addEventListener('click', (e) => { e.stopPropagation(); toggle(); });
    dropdown.addEventListener('click', (e) => e.stopPropagation());
    document.addEventListener('click', (e) => { if (!wrap.contains(e.target)) close(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });

    if (logoutBtn) logoutBtn.addEventListener('click', () => { close(); authModule.requestLogout(); });
  }

  /* ======================================================================
     8. settings —— 服务地址设置弹窗
     ====================================================================== */
  function initSettings() {
    const mask = $('#settingsMask');
    const btnOpen = $('#btnSettings');
    const btnClose = $('#btnCloseSettings');
    const btnSave = $('#btnSaveSettings');
    const btnReset = $('#btnResetSettings');
    const cfgImport = $('#cfgImport');
    const cfgQuery = $('#cfgQuery');
    const btnLogout = $('#btnLogout');
    if (!mask || !btnOpen) return;

    function open() {
      if (cfgImport) cfgImport.value = localStorage.getItem(CONFIG.storageKeys.import) || '';
      if (cfgQuery) cfgQuery.value = localStorage.getItem(CONFIG.storageKeys.query) || '';
      mask.hidden = false;
    }
    function close() { mask.hidden = true; }

    btnOpen.addEventListener('click', open);
    if (btnClose) btnClose.addEventListener('click', close);
    mask.addEventListener('click', (e) => { if (e.target === mask) close(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !mask.hidden) close(); });

    if (btnSave) {
      btnSave.addEventListener('click', () => {
        const imp = (cfgImport.value || '').trim();
        const qry = (cfgQuery.value || '').trim();
        imp ? localStorage.setItem(CONFIG.storageKeys.import, imp) : localStorage.removeItem(CONFIG.storageKeys.import);
        qry ? localStorage.setItem(CONFIG.storageKeys.query, qry) : localStorage.removeItem(CONFIG.storageKeys.query);
        BASES = resolveBases();
        close();
        chatModule.reload();
      });
    }

    if (btnReset) {
      btnReset.addEventListener('click', () => {
        localStorage.removeItem(CONFIG.storageKeys.import);
        localStorage.removeItem(CONFIG.storageKeys.query);
        if (cfgImport) cfgImport.value = '';
        if (cfgQuery) cfgQuery.value = '';
      });
    }

    if (btnLogout) {
      btnLogout.addEventListener('click', () => { close(); authModule.requestLogout(); });
    }
  }

  /* ======================================================================
     启动（按页初始化：各模块自检元素，缺则跳过）
     ====================================================================== */
  function boot() {
    initNav();
    initReveal();        // 先建立揭示观察器，避免登录态切换时误判
    initUserMenu();
    authModule.init();   // 登录门禁：同步 <html> 状态 class 与用户区显隐
    initSettings();
    importModule.init(); // 非建库页自动跳过
    chatModule.init();   // 非对话页自动跳过
    initHealth();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  // 供调试使用
  window.__KB__ = { CONFIG, AUTH, auth: authModule, get bases() { return BASES; } };
})();
