// SnapEdit Studio WebUI — admin gate + editor workbench
let authed = false;
let currentFile = null;
let currentTool = null;
let tools = [];
let lastResultUrl = null;
let lastResultB64 = null;
let viewMode = 'after';

const $ = id => document.getElementById(id);

// ---------------- auth ----------------
async function init() {
  await checkAuth();
  if (authed) {
    bindUploadControls();
    loadTools();
    buildApiDoc();
  }
}

async function checkAuth() {
  try {
    const r = await fetch('/api/auth/status');
    const j = await r.json();
    authed = !!j.authenticated;
  } catch (e) {
    authed = false;
  }
  $('view-login').style.display = authed ? 'none' : 'grid';
  $('view-app').style.display = authed ? 'flex' : 'none';
  if (!authed) $('admin-password').focus();
  return authed;
}

function showLogin(msg) {
  authed = false;
  $('view-login').style.display = 'grid';
  $('view-app').style.display = 'none';
  const err = $('login-error');
  if (msg) {
    err.textContent = msg;
    err.classList.add('shake');
    setTimeout(() => err.classList.remove('shake'), 320);
  }
  $('admin-password').focus();
}

async function logout() {
  try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (e) {}
  location.reload();
}

// login form wiring
$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('login-error');
  const btn = $('login-btn');
  const pw = $('admin-password').value;
  if (!pw) { err.textContent = '请输入密码'; return; }
  btn.disabled = true;
  btn.textContent = '验证中…';
  err.textContent = '';
  try {
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pw })
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || 'password');
    $('admin-password').value = '';
    await checkAuth();
    bindUploadControls();
    bindUploadControls();
    loadTools();
    buildApiDoc();
    setStatus('已登录 — 上传图片开始编辑');
  } catch (ex) {
    err.textContent = (ex.message === 'password' || ex.message === 'wrong password') ? '密码错误，请重试' : '登录失败: ' + ex.message;
    err.classList.add('shake');
    setTimeout(() => err.classList.remove('shake'), 320);
  } finally {
    btn.disabled = false;
    btn.textContent = '进入工作台';
  }
});

$('pwd-toggle').addEventListener('click', () => {
  const i = $('admin-password');
  i.type = i.type === 'password' ? 'text' : 'password';
});

// ---------------- tools ----------------
async function loadTools() {
  try {
    const res = await fetch('/v1/tools');
    if (res.status === 401) { showLogin('会话已过期，请重新登录'); return; }
    const data = await res.json();
    tools = data.tools;
    $('tool-count').textContent = tools.length;
    const grid = $('tool-grid');
    grid.innerHTML = '';
    tools.forEach(t => {
      const card = document.createElement('div');
      card.className = 'tool-card';
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');
      card.innerHTML = `<div class="tc-icon">${iconFor(t.id)}</div>
        <div class="tc-name">${t.name}</div>
        <div class="tc-desc">${t.description || ''}</div>`;
      card.onclick = () => selectTool(t, card);
      card.onkeydown = (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); selectTool(t, card); } };
      grid.appendChild(card);
    });
  } catch (e) {
    setStatus('加载工具失败: ' + e.message, 'err');
  }
}

function iconFor(id) {
  const map = {
    remove_background: '✂️', remove_object: '🧹', enhance: '✨', restore: '🕰️',
    anime: '🎨', retouch: '💄', sky: '🌇', passport: '🪪', filter: '🌈', text_erase: '🧽'
  };
  return map[id] || '🛠️';
}

function selectTool(t, card) {
  currentTool = t;
  document.querySelectorAll('.tool-card').forEach(c => c.classList.remove('active'));
  if (card) card.classList.add('active');
  const fields = $('param-fields');
  fields.innerHTML = '';
  const params = t.params || {};
  $('params').style.display = 'block';
  Object.entries(params).forEach(([k, spec]) => {
    const div = document.createElement('div');
    div.className = 'param-field';
    const label = document.createElement('label');
    if (spec.type === 'boolean') {
      const input = document.createElement('input');
      input.type = 'checkbox'; input.checked = !!spec.default; input.id = 'p-' + k;
      label.textContent = k;
      div.appendChild(label);
      div.appendChild(input);
    } else if (spec.type === 'integer' || spec.type === 'number') {
      const input = document.createElement('input');
      input.type = 'range'; input.min = spec.min || 1; input.max = spec.max || 10; input.step = spec.step || 1;
      input.value = spec.default ?? 3; input.id = 'p-' + k;
      const val = document.createElement('span');
      val.className = 'pv'; val.id = 'v-' + k; val.textContent = input.value;
      label.innerHTML = `<span>${k}</span>`;
      label.appendChild(val);
      input.oninput = () => { $('v-' + k).textContent = input.value; };
      div.appendChild(label);
      div.appendChild(input);
    } else {
      const input = document.createElement('input');
      input.type = 'text'; input.value = spec.default || ''; input.id = 'p-' + k;
      label.textContent = k;
      div.appendChild(label);
      div.appendChild(input);
    }
    fields.appendChild(div);
  });
}

function collectParams() {
  const out = {};
  if (!currentTool) return out;
  Object.keys(currentTool.params || {}).forEach(k => {
    const el = $('p-' + k);
    if (!el) return;
    const spec = currentTool.params[k];
    if (spec.type === 'boolean') out[k] = el.checked;
    else if (spec.type === 'integer' || spec.type === 'number') out[k] = parseInt(el.value, 10) || Number(el.value);
    else out[k] = el.value;
  });
  return out;
}

// ---------------- upload ----------------
function bindUploadControls() {
  const zone = $('dropzone');
  const input = $('file-input');
  if (!zone || !input || zone.dataset.bound === '1') return;
  zone.dataset.bound = '1';

  zone.addEventListener('click', (event) => {
    if (event.target === input) return;
    input.click();
  });
  zone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      input.click();
    }
  });
  zone.addEventListener('dragenter', (event) => {
    event.preventDefault();
    zone.classList.add('drag');
  });
  zone.addEventListener('dragover', (event) => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
    zone.classList.add('drag');
  });
  zone.addEventListener('dragleave', (event) => {
    if (!zone.contains(event.relatedTarget)) zone.classList.remove('drag');
  });
  zone.addEventListener('drop', handleDrop);
  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    if (file) handleFile(file);
    input.value = '';
  });
}

function handleDrop(e) {
  e.preventDefault();
  e.stopPropagation();
  $('dropzone').classList.remove('drag');
  const files = e.dataTransfer && e.dataTransfer.files;
  if (files && files.length) handleFile(files[0]);
}
function handleFile(file) {
  if (!file || !file.type.startsWith('image/')) { setStatus('请选择图片文件', 'err'); return; }
  currentFile = file;
  $('dz-inner').innerHTML = `<div class="dz-title">${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB</div>
    <div class="dz-hint">已就绪，选择右侧工具开始处理</div>`;
  setStatus(`已加载 ${file.name}`);
  const url = URL.createObjectURL(file);
  lastResultUrl = null; lastResultB64 = null;
  $('viewer').style.display = 'flex';
  $('view-img').src = url;
  $('tab-after').classList.remove('active'); $('tab-after').setAttribute('aria-selected', 'false');
  $('tab-before').classList.add('active'); $('tab-before').setAttribute('aria-selected', 'true');
  viewMode = 'before';
}

async function runTool() {
  if (!currentFile) { setStatus('先上传图片', 'err'); return; }
  if (!currentTool) { setStatus('先选择工具', 'err'); return; }
  const fd = new FormData();
  fd.append('image', currentFile);
  fd.append('params_json', JSON.stringify(collectParams()));
  setStatus(`${currentTool.name} 处理中…`, 'busy');
  try {
    const res = await fetch('/v1/tools/' + currentTool.id, { method: 'POST', body: fd });
    if (res.status === 401) { showLogin('会话已过期，请重新登录'); return; }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    let outUrl = data.url || null;
    let outB64 = data.b64_json || data.image_b64 || null;
    if (!outUrl && !outB64) throw new Error('返回结果异常');
    lastResultUrl = outUrl;
    lastResultB64 = outB64;
    $('viewer').style.display = 'flex';
    setView('after');
    const dl = $('download-link');
    if (outUrl) dl.href = outUrl;
    else dl.href = 'data:image/png;base64,' + outB64;
    let meta = `${currentTool.name}`;
    if (data.elapsed_seconds) meta += ` · ${data.elapsed_seconds}s`;
    if (data.mode) meta += ` · ${data.mode}`;
    if (data.style) meta += ` · ${data.style}`;
    if (data.background) meta += ` · ${data.background}`;
    $('meta-row').innerHTML = `<b>✓ 完成</b> ${meta}`;
    setStatus(`✓ ${currentTool.name} 完成`, 'ok');
  } catch (e) {
    setStatus('处理失败: ' + e.message, 'err');
  }
}

function setView(mode) {
  viewMode = mode;
  $('tab-after').classList.toggle('active', mode === 'after');
  $('tab-after').setAttribute('aria-selected', mode === 'after');
  $('tab-before').classList.toggle('active', mode === 'before');
  $('tab-before').setAttribute('aria-selected', mode === 'before');
  if (mode === 'after') {
    if (lastResultUrl) $('view-img').src = lastResultUrl;
    else if (lastResultB64) $('view-img').src = 'data:image/png;base64,' + lastResultB64;
  } else {
    if (currentFile) $('view-img').src = URL.createObjectURL(currentFile);
  }
}

function setStatus(msg, kind) {
  const s = $('status');
  s.className = 'status' + (kind === 'busy' ? ' busy' : kind === 'err' ? ' err' : '');
  s.textContent = msg;
}

// ---------------- API doc ----------------
function toggleApiDoc() {
  const m = $('api-modal');
  m.style.display = m.style.display === 'none' ? 'grid' : 'none';
}

function buildApiDoc() {
  $('api-doc').textContent = `# SnapEdit Studio — OpenAI 兼容 API（Token 认证）

Base URL: http://<host>:8000

## 认证（必须）
所有 /v1/* 接口需要请求头：
  Authorization: Bearer <API_TOKEN>
Token 在服务端环境变量配置：API_TOKENS（逗号分隔多个）或 API_TOKEN。

## 列出模型
GET /v1/models

## 图片编辑（OpenAI images/edits 兼容）
POST /v1/images/edits
  multipart/form-data:
    image   (file, 必填)
    model   (string, 默认 snapedit/remove_background)
            snapedit/remove_background / remove_object / enhance / restore
            snapedit/anime / retouch / sky / passport / filter / text_erase
    prompt  (string, 可选；可传 JSON 参数 {"sky":"sunset","strength":4})
    mask    (file, 可选，用于 remove_object/text_erase 掩码)
    response_format (url | b64_json)

## 直接工具调用
POST /v1/tools/{tool_id}
  multipart/form-data:
    image  (file)   mask (file, 可选)   params_json (string, JSON 参数)

## 流水线（多工具链）
POST /v1/pipeline
  image (file)
  steps_json (string): [{"tool":"remove_background"},{"tool":"enhance","params":{"strength":4}}]

## 示例 curl
curl -X POST http://localhost:8000/v1/images/edits \\
  -H "Authorization: Bearer <API_TOKEN>" \\
  -F image=@photo.jpg \\
  -F model=snapedit/enhance \\
  -F prompt='{"strength":4}' \\
  -F response_format=url

## 工具列表
GET /v1/tools

## Python（OpenAI SDK 兼容）
from openai import OpenAI
client = OpenAI(base_url="http://<host>:8000/v1", api_key="<API_TOKEN>")
# 或 requests:
import requests, base64
r = requests.post("http://<host>:8000/v1/images/edits",
    headers={"Authorization": "Bearer <API_TOKEN>"},
    files={"image": open("a.jpg","rb")},
    data={"model":"snapedit/remove_background","response_format":"b64_json"})
img_b64 = r.json()["data"][0]["b64_json"]
`;
}

init();
