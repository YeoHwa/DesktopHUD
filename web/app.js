'use strict';
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const api = () => window.pywebview.api;
const glyph = code => `<i class="g">${String.fromCharCode(parseInt(code, 16))}</i>`;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtTime = s => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
const DAYS = ['일', '월', '화', '수', '목', '금', '토'];

const S = { menu: null, games: [], gameFilter: '전체', messengers: [], web: [], media: null, mediaAt: 0, volDrag: false, busy: {}, favs: [] };

function setBar(id, pct, low) {
  const el = typeof id === 'string' ? $(id) : id;
  el.firstElementChild.style.width = `${Math.max(0, Math.min(100, pct || 0))}%`;
  el.classList.toggle('low', !!low);
}
function setSeg(id, value) { $$(`#${id} button`).forEach(b => b.classList.toggle('on', b.dataset.v === value)); }
let toastTimer;
function notify(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => t.hidden = true, 3500); }
function confirmBar(msg) {
  return new Promise(res => {
    $('#cmsg').textContent = msg; $('#confirm').hidden = false;
    $('#cyes').onclick = () => { $('#confirm').hidden = true; res(true); };
    $('#cno').onclick = () => { $('#confirm').hidden = true; res(false); };
  });
}

/* ---------------- 시계 ---------------- */
function tickClock() {
  const d = new Date();
  $('#clock').textContent = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  $('#date').textContent = `${d.getMonth() + 1}월 ${d.getDate()}일 ${DAYS[d.getDay()]}`;
}

/* ---------------- 소리 출력 버튼 (설정에서 고른 두 장치) ---------------- */
function renderAudioButtons() {
  const box = $('#snd');
  if (!S.favs.length) { box.innerHTML = '<button disabled>출력 장치 없음</button>'; return; }
  box.innerHTML = S.favs.slice(0, 2).map(f =>
    `<button data-v="${esc(f.id)}" title="${esc(f.label)}">${glyph(f.icon === 'headset' ? 'E7F6' : 'E7F5')}${esc(f.label)}</button>`).join('');
  $$('#snd button').forEach(b => b.onclick = async () => {
    if (S.busy.snd) return;
    S.busy.snd = true; setSeg('snd', b.dataset.v); b.classList.add('busy');
    const now = await api().set_audio(b.dataset.v);
    b.classList.remove('busy'); S.busy.snd = false; setSeg('snd', now);
    notify(now === b.dataset.v ? `${b.textContent.trim()}(으)로 전환했어요` : '출력 장치를 바꾸지 못했어요');
  });
}

/* ---------------- 상태 (2초마다) ---------------- */
async function pollStatus() {
  try {
    const st = await api().status();
    const s = st.stats;
    $('#cpu').textContent = `${s.cpu}%`; setBar('#cpub', s.cpu);
    $('#gpu').textContent = s.gpu == null ? '-' : `${s.gpu}%`; setBar('#gpub', s.gpu);
    $('#ram').textContent = `${s.ramUsed}G`; setBar('#ramb', s.ramPct, s.ramPct > 90);
    const b = st.battery;
    if (b.ok && b.percent != null) {
      $('#mname').textContent = (b.name || '마우스').replace(' LIGHTSPEED', '');
      $('#bat').textContent = `${b.percent}%`;
      setBar('#batbar', b.percent, b.percent <= 15);
      $('#bath').textContent = b.charging ? '충전 중' : (b.hours ? `${b.hours}시간` : '');
      $('#chg').hidden = !b.charging;
    } else {
      $('#bat').textContent = '--'; setBar('#batbar', 0); $('#chg').hidden = true;
      $('#mname').textContent = '마우스';
      $('#bath').textContent = {
        noapp: 'G HUB / Razer 마우스 찾는 중',
        nodevice: b.source === 'G HUB' ? '무선 마우스가 꺼져 있어요' : '무선 마우스 없음',
        off: '배터리 표시 꺼짐',
      }[b.status] || '마우스 찾는 중';
    }
    if (!S.busy.snd) setSeg('snd', st.audio);
    if (!S.busy.mod) setSeg('mod', st.mode);
    if (!S.volDrag && st.volume.level != null) {
      $('#vol').value = st.volume.level; $('#volv').textContent = st.volume.muted ? '음소거' : st.volume.level;
      $('#volbtn').innerHTML = glyph(st.volume.muted ? 'E74F' : 'E767');
    }
    const lc = $('#livecnt'); lc.hidden = !st.live; lc.textContent = `${st.live} LIVE`;
    S.quick = st.quick;
    if (S.menu === 'sys') renderSys();
  } catch (e) { console.error(e); }
}

/* ---------------- 음악 ---------------- */
async function pollMedia() {
  try { S.media = await api().media(); S.mediaAt = performance.now(); renderMedia(); } catch (e) { console.error(e); }
}
function renderMedia() {
  const m = S.media;
  if (!m || !m.ok || !m.title) {
    $('#title').textContent = '재생 중인 곡이 없어요'; $('#artist').textContent = 'YouTube Music을 열어 보세요';
    $('#art').style.backgroundImage = ''; $('#art').innerHTML = glyph('E8D6');
    $('#pp').innerHTML = glyph('E768'); $('#cur').textContent = '0:00'; $('#dur').textContent = '0:00'; setBar('#progbar', 0);
    $('#plabel').textContent = '지금 재생 중';
    return;
  }
  $('#plabel').textContent = m.isYouTubeMusic ? 'YouTube Music' : '지금 재생 중';
  $('#title').textContent = m.title; $('#title').title = m.title;
  $('#artist').textContent = [m.artist, m.album].filter(Boolean).join(' · ') || ' ';
  if (m.thumb) { $('#art').style.backgroundImage = `url(${m.thumb})`; $('#art').innerHTML = ''; }
  else { $('#art').style.backgroundImage = ''; $('#art').innerHTML = glyph('E8D6'); }
  $('#pp').innerHTML = glyph(m.playing ? 'E769' : 'E768');
  tickProgress();
}
function tickProgress() {
  const m = S.media;
  if (!m || !m.ok || !m.title) return;
  if (!(m.duration > 0)) { $('#cur').textContent = 'LIVE'; $('#dur').textContent = ''; setBar('#progbar', 100); return; }
  const pos = Math.min(m.duration, m.position + (m.playing ? (performance.now() - S.mediaAt) / 1000 : 0));
  $('#cur').textContent = fmtTime(pos); $('#dur').textContent = fmtTime(m.duration);
  setBar('#progbar', pos / m.duration * 100);
}

/* ---------------- 타일 ---------------- */
function tile({ name, sub, icon, glyph: gl, on, warn, corner, cls, data }) {
  const ic = icon ? `<span class="ic"><img src="${icon}" alt=""></span>` : `<span class="ic glyph">${glyph(gl || 'E8B7')}</span>`;
  const attrs = Object.entries(data || {}).map(([k, v]) => `data-${k}="${esc(v)}"`).join(' ');
  return `<button class="tile${on ? ' on' : ''}${warn ? ' warn' : ''}${cls ? ' ' + cls : ''}" ${attrs} title="${esc(name)}">${ic}<span class="nm">${esc(name)}</span>${sub ? `<span class="sb">${esc(sub)}</span>` : ''}${corner || ''}</button>`;
}

/* ---------------- 오른쪽 패널 ---------------- */
const PANELS = {
  game: { title: '게임', render: renderGames },
  live: { title: '치지직 라이브', render: renderLive },
  msg: { title: '메신저·커뮤니티', render: () => renderLinks(S.messengers, false) },
  file: { title: '내 파일', render: renderFiles },
  dev: { title: '개발 유틸리티', render: renderDev },
  sys: { title: '시스템', render: async () => { renderSys(); S.bin = await api().recycle_info(); if (S.menu === 'sys') renderSys(); } },
  web: { title: '웹 바로가기', render: () => renderLinks(S.web, true) },
  settings: { title: '설정', render: renderSettings },
};

async function openMenu(key) {
  const same = S.menu === key;
  $$('.mi').forEach(m => m.classList.remove('on'));
  if (same || !key) { S.menu = null; $('#right').hidden = true; await api().set_expanded(false); return; }
  if (!S.menu) await api().set_expanded(true);
  S.menu = key;
  const mi = $(`.mi[data-k="${key}"]`); if (mi) mi.classList.add('on');
  $('#right').hidden = false;
  $('#rt').textContent = PANELS[key].title; $('#rs').textContent = ''; $('#chips').innerHTML = '';
  $('#body').innerHTML = '<div class="empty">불러오는 중…</div>';
  PANELS[key].render();
}

function renderGames() {
  const sources = ['전체', ...new Set(S.games.map(g => g.source))];
  if (!sources.includes(S.gameFilter)) S.gameFilter = '전체';
  $('#rs').textContent = `설치된 게임 ${S.games.length}개 · 자동 감지`;
  $('#chips').innerHTML = sources.map(s => `<button class="chip${s === S.gameFilter ? ' on' : ''}" data-f="${esc(s)}">${esc(s)}</button>`).join('');
  const list = S.games.filter(g => S.gameFilter === '전체' || g.source === S.gameFilter);
  const hide = id => `<span class="hide" data-hide="${esc(id)}" title="목록에서 숨기기">${glyph('E711')}</span>`;
  $('#body').innerHTML = `<div class="grid">${list.map(g => tile({ name: g.name, sub: g.source, icon: g.icon, glyph: 'E7FC', data: { game: g.id }, corner: hide(g.id) })).join('')}
    ${tile({ name: '게임 추가', sub: '실행 파일 고르기', glyph: 'E710', cls: 'add', data: { addgame: 1 } })}</div>
    ${list.length ? '' : '<div class="empty">설치된 게임을 찾지 못했어요. "게임 추가"로 직접 넣을 수 있어요.</div>'}`;
}

async function renderLive() {
  const list = await api().chzzk_list();
  if (S.menu !== 'live') return;
  const live = list.filter(s => s.live).length;
  $('#rs').textContent = `방송 중 ${live}명 · 등록 ${list.length}명`;
  const rows = list.map(s => {
    const sub = s.live ? `${s.title} · ${s.category}` : (s.checked ? '방송 꺼짐' : '확인 중…');
    return `<div class="sr">
      <div class="av${s.live ? ' live' : ''}" style="${s.image ? `background-image:url('${esc(s.image)}')` : ''}">${s.image ? '' : glyph('E77B')}</div>
      <div class="sr-text"><div class="sr-top">${s.live ? '<span class="lv">LIVE</span>' : ''}<b>${esc(s.name)}</b>${s.live ? `<span class="label">${Number(s.viewers).toLocaleString()}명</span>` : ''}</div>
      <div class="sr-sub" title="${esc(sub)}">${esc(sub)}</div></div>
      <button class="icon-btn" data-bell="${s.id}" data-on="${s.notify ? 1 : 0}" title="방송 알림 ${s.notify ? '끄기' : '켜기'}">${glyph(s.notify ? 'EA8F' : 'E7ED')}</button>
      <button class="icon-btn" data-del="${s.id}" title="목록에서 빼기">${glyph('E74D')}</button>
      ${s.live ? `<button class="btn" data-watch="${s.id}">시청</button>` : ''}
    </div>`;
  }).join('') || '<div class="empty">아직 등록한 스트리머가 없어요. 아래에서 검색해 추가하세요.</div>';
  $('#body').innerHTML = rows + `
    <div class="search"><input id="q" type="text" placeholder="스트리머 이름으로 검색"><button class="btn" id="qgo">검색</button></div>
    <div id="results"></div>
    <div class="hint">1분마다 방송 상태를 확인하고, 방송이 켜지면 Windows 알림을 띄워요.</div>`;
  const go = async () => {
    const q = $('#q').value.trim();
    if (!q) { $('#results').innerHTML = '<div class="hint" style="color:var(--danger)">검색어를 입력하세요</div>'; return; }
    $('#results').innerHTML = '<div class="hint">검색 중…</div>';
    const res = await api().chzzk_search(q);
    $('#results').innerHTML = res.map(r => `<div class="sr">
      <div class="av" style="${r.image ? `background-image:url('${esc(r.image)}')` : ''}">${r.image ? '' : glyph('E77B')}</div>
      <div class="sr-text"><div class="sr-top">${r.live ? '<span class="lv">LIVE</span>' : ''}<b>${esc(r.name)}</b></div><div class="sr-sub">팔로워 ${Number(r.followers).toLocaleString()}명</div></div>
      <button class="btn" data-add="${r.id}" data-name="${esc(r.name)}" data-img="${esc(r.image)}">추가</button></div>`).join('') || '<div class="hint">검색 결과가 없어요</div>';
  };
  $('#qgo').onclick = go;
  $('#q').onkeydown = e => { if (e.key === 'Enter') go(); };
  $('#q').oninput = () => { if ($('#results').textContent.includes('검색어를')) $('#results').innerHTML = ''; };
}

function renderLinks(items, editable) {
  const del = i => editable ? `<span class="hide" data-webdel="${i}" title="삭제">${glyph('E711')}</span>` : '';
  $('#body').innerHTML = `<div class="grid">${items.map((m, i) => tile({ name: m.name, sub: m.sub, icon: m.icon, glyph: m.glyph || 'E8A7', data: { link: i }, corner: del(i) })).join('')}</div>
    ${editable ? `<div class="search"><input id="wname" type="text" placeholder="이름 (예: 인벤)" style="max-width:180px"><input id="wurl" type="text" placeholder="주소 (예: inven.co.kr)"><button class="btn" id="wadd">추가</button></div><div id="werr" class="hint"></div>` : ''}`;
  if (editable) {
    $('#wadd').onclick = async () => {
      const name = $('#wname').value.trim(), url = $('#wurl').value.trim();
      if (!url) { $('#werr').textContent = '주소를 입력하세요'; $('#werr').style.color = 'var(--danger)'; return; }
      S.web = await api().add_web(name, url); renderLinks(S.web, true); notify('바로가기를 추가했어요');
    };
    $('#wurl').oninput = () => $('#werr').textContent = '';
  }
}

async function renderFiles() {
  const f = await api().files();
  if (S.menu !== 'file') return;
  $('#rs').textContent = '자주 여는 폴더와 드라이브';
  S.fileItems = f.items; S.drives = f.drives;
  const r = f.recycle;
  $('#body').innerHTML = `<div class="sec">폴더</div>
    <div class="grid">${f.items.filter(it => it.stat !== 'recycle').map(it => tile({ name: it.name, sub: it.sub, glyph: it.glyph, data: { file: f.items.indexOf(it) } })).join('')}</div>
    <div class="sec">휴지통</div>
    <div class="grid">${tile({ name: '휴지통 열기', sub: r.count ? `${r.count}개 · ${r.sizeText}` : '비어 있음', glyph: 'E74D', data: { open: 'shell:RecycleBinFolder' } })}
      ${tile({ name: '휴지통 비우기', sub: r.count ? `${r.count}개 · ${r.sizeText}` : '비어 있음', glyph: 'E894', warn: r.count > 0, data: { act: 'empty_bin' } })}</div>
    <div class="sec">드라이브</div>
    <div class="drives">${f.drives.map((d, i) => `<div class="drv" data-drive="${i}" style="cursor:pointer"><b>${esc(d.name)}</b><span class="bar${d.pct > 90 ? ' low' : ''}"><i style="width:${d.pct}%"></i></span><span>${d.pct}% · ${esc(d.free)} 남음</span></div>`).join('')}</div>`;
}

async function renderDev() {
  const d = await api().dev();
  if (S.menu !== 'dev') return;
  S.dev = d;
  $('#rs').textContent = d.projectsDir ? `${d.projectsDir} 자동 감지` : '';
  const corner = i => `<span class="corner" data-term="${i}" title="터미널에서 열기">${glyph('E756')}</span>`;
  const projects = d.projectsDir
    ? (d.projects.map((p, i) => tile({ name: p.name, sub: '폴더 열기', glyph: 'E943', data: { proj: i }, corner: corner(i) })).join('') || '<div class="empty">프로젝트 폴더가 비어 있어요</div>')
    : `<div class="empty">설정에서 프로젝트 폴더를 지정하면 여기에 나와요 <button class="btn ghost" data-gosettings="1">설정 열기</button></div>`;
  $('#body').innerHTML = `<div class="sec">프로젝트</div><div class="grid">${projects}</div>
    <div class="sec">도구</div>
    <div class="grid">${d.tools.map((t, i) => tile({ name: t.name, sub: t.sub, icon: t.icon, glyph: t.glyph || 'E756', on: t.action === 'docker' && t.sub === '실행 중', data: { tool: i } })).join('')}</div>`;
}

function renderSys() {
  const q = S.quick || {};
  $('#rs').textContent = '버튼 하나로 실행';
  const items = [
    { k: 'ram', name: 'RAM 청소', sub: S.ramMsg || '메모리 회수', glyph: 'E945' },
    { k: 'focus', name: '집중 모드', sub: q.focus ? '켜짐 · 메신저 꺼짐' : '메신저 끄기', glyph: 'E708', on: q.focus },
    { k: 'monitor', name: '모니터 1/2', sub: q.monitors > 1 ? `지금 ${q.monitors}대 → 1대` : '지금 1대 → 2대', glyph: 'E7F4' },
    q.hasWallpaper ? { k: 'wallpaper', name: '배경 일시정지', sub: q.wallpaperPaused ? '멈춤 · 눌러서 재생' : '재생 중', glyph: 'E8B9', on: q.wallpaperPaused } : null,
    { k: 'disk', name: '디스크 청소', sub: 'Windows 디스크 정리', glyph: 'E75C' },
    { k: 'empty_bin', name: '휴지통 비우기', sub: S.bin ? (S.bin.count ? `${S.bin.count}개 · ${S.bin.sizeText}` : '비어 있음') : '영구 삭제', glyph: 'E894', warn: S.bin && S.bin.count > 0 },
    q.shutdownIn != null
      ? { k: 'cancel_shutdown', name: '종료 취소', sub: `${q.shutdownIn}초 뒤 종료`, glyph: 'E7E8', warn: true }
      : { k: 'shutdown', name: '안전 종료', sub: '1분 뒤 PC 끄기', glyph: 'E7E8' },
  ].filter(Boolean);
  $('#body').innerHTML = `<div class="grid">${items.map(it => tile({ ...it, data: { act: it.k } })).join('')}</div>`;
}

/* ---------------- 설정 ---------------- */
async function renderSettings() {
  const s = await api().get_settings();
  if (S.menu !== 'settings') return;
  S.settings = s;
  $('#rs').textContent = `버전 ${s.version}`;
  const theme = document.body.classList.contains('dark') ? 'dark' : 'light';
  const op = (s.opacity || {})[theme] || {};
  const devOpts = sel => s.devices.map(d => `<option value="${esc(d.id)}"${d.id === sel ? ' selected' : ''}>${esc(d.name)}${d.enabled ? '' : ' (사용 안 함)'}</option>`).join('');
  const fav = i => s.favorites[i] || {};
  const favRow = i => `<div class="row"><label>버튼 ${i + 1}</label>
      <select data-fav="${i}">${devOpts(fav(i).id)}</select>
      <input type="text" data-favlabel="${i}" value="${esc(fav(i).label || '')}" placeholder="버튼 이름" style="min-width:90px;max-width:120px;flex:none">
      <select data-favicon="${i}" style="min-width:90px;flex:none"><option value="headset"${fav(i).icon === 'headset' ? ' selected' : ''}>헤드셋</option><option value="speaker"${fav(i).icon !== 'headset' ? ' selected' : ''}>스피커</option></select></div>`;
  $('#body').innerHTML = `
    <div class="set"><h4>Windows 시작 시 자동 실행</h4><div class="desc">로그인하고 10초 뒤에 HUD를 켜요.</div>
      <div class="row"><button class="switch${s.autostart ? ' on' : ''}" id="s-auto" aria-label="자동 실행"></button><span class="desc" id="s-auto-t">${s.autostart ? '켜짐' : '꺼짐'}</span></div></div>
    <div class="set"><h4>모양</h4>
      <div class="row"><label>테마</label><div class="seg" id="s-theme" style="flex:none;width:200px"><button data-v="light">밝게</button><button data-v="dark">어둡게</button></div></div>
      <div class="row"><label>왼쪽 패널</label><input type="range" id="s-pa" min="0.2" max="1" step="0.05" value="${op.panel ?? 0.7}"><span class="val" id="s-pa-v"></span></div>
      <div class="row"><label>오른쪽 패널</label><input type="range" id="s-ga" min="0.1" max="1" step="0.05" value="${op.glass ?? 0.4}"><span class="val" id="s-ga-v"></span></div>
      <div class="desc">숫자가 낮을수록 배경화면이 더 비쳐 보여요. 시계 부분을 끌면 HUD 위치를 옮길 수 있어요.</div></div>
    <div class="set"><h4>소리 출력 버튼</h4><div class="desc">왼쪽 위 두 버튼에 연결할 출력 장치예요. '사용 안 함' 장치도 고르면 자동으로 켜져요.</div>
      ${favRow(0)}${favRow(1)}</div>
    <div class="set"><h4>마우스 배터리</h4><div class="desc">Logitech(G HUB 필요)과 Razer(Synapse 없어도 됨) 무선 마우스를 지원해요. 바꾼 뒤에는 HUD를 다시 켜야 적용돼요.</div>
      <div class="row"><label>읽는 곳</label><select id="s-mouse" style="flex:none;min-width:220px">
        ${[['auto', '자동 (Logitech / Razer)'], ['ghub', 'Logitech G HUB 만'], ['razer', 'Razer 만'], ['off', '표시 안 함']].map(([v, t]) => `<option value="${v}"${s.mouse_provider === v ? ' selected' : ''}>${t}</option>`).join('')}
      </select></div></div>
    <div class="set"><h4>키보드 버튼</h4><div class="desc">키보드 아이콘을 누르면 열 주소예요. 비워 두면 버튼이 숨겨져요.</div>
      <div class="row"><input type="text" id="s-kb" value="${esc(s.keyboard_url)}" placeholder="https://"></div></div>
    <div class="set"><h4>개발 프로젝트 폴더</h4>
      <div class="row"><input type="text" id="s-proj" value="${esc(s.projects_dir)}" placeholder="예: C:\\Users\\이름\\source\\repos"><button class="btn ghost" id="s-proj-pick">찾아보기</button></div></div>
    <div class="set"><h4>게임 모드 / 개발 모드</h4>
      ${s.mode_script ? '<div class="desc">지금은 사용자 스크립트로 전환하고 있어요 (설정 파일의 modes.*.script). 아래 목록은 스크립트를 비우면 쓰여요.</div>' : ''}
      <div class="desc">게임 모드로 바꿀 때 끌 프로그램 (프로세스 이름, 한 줄에 하나)</div>
      <textarea id="s-gclose">${esc(s.game_close)}</textarea>
      <div class="row"><button class="switch${s.wsl_shutdown ? ' on' : ''}" id="s-wsl" aria-label="WSL 끄기"></button><span class="desc">게임 모드에서 WSL도 끄기</span></div>
      <div class="desc" style="margin-top:8px">개발 모드로 바꿀 때 끌 프로그램 (예: steam, NexonPlug)</div>
      <textarea id="s-dclose">${esc(s.dev_close)}</textarea></div>
    <div class="row" style="gap:6px;margin:4px 0 8px"><button class="btn" id="s-save">저장</button><button class="btn ghost" id="s-cfg">설정 파일 열기</button><button class="btn ghost" id="s-log">로그 열기</button><span class="hint" id="s-msg" style="margin:0"></span></div>`;
  setSeg('s-theme', theme);
  const showOp = () => { $('#s-pa-v').textContent = Math.round($('#s-pa').value * 100) + '%'; $('#s-ga-v').textContent = Math.round($('#s-ga').value * 100) + '%'; };
  showOp();
  const previewOp = () => { document.body.style.setProperty('--pa', $('#s-pa').value); document.body.style.setProperty('--ga', $('#s-ga').value); showOp(); };
  $('#s-pa').oninput = previewOp; $('#s-ga').oninput = previewOp;
  $$('#s-theme button').forEach(b => b.onclick = async () => {
    await saveSettingsForm(); applyTheme(await api().set_theme(b.dataset.v)); renderSettings();
  });
  $('#s-auto').onclick = async () => {
    const want = !$('#s-auto').classList.contains('on');
    $('#s-auto-t').textContent = '바꾸는 중…';
    const now = await api().set_autostart(want);
    $('#s-auto').classList.toggle('on', now); $('#s-auto-t').textContent = now ? '켜짐' : '꺼짐';
    if (now !== want) notify('자동 실행 설정을 바꾸지 못했어요');
  };
  $('#s-wsl').onclick = () => $('#s-wsl').classList.toggle('on');
  $('#s-proj-pick').onclick = async () => { const p = await api().pick_folder(); if (p) $('#s-proj').value = p; };
  $('#s-cfg').onclick = () => api().open_config();
  $('#s-log').onclick = () => api().open_log();
  $('#s-save').onclick = async () => { await saveSettingsForm(); $('#s-msg').textContent = '저장했어요'; notify('설정을 저장했어요'); };
}

async function saveSettingsForm() {
  const s = S.settings; if (!s || !$('#s-save')) return;
  const theme = document.body.classList.contains('dark') ? 'dark' : 'light';
  const opacity = JSON.parse(JSON.stringify(s.opacity || {}));
  opacity[theme] = { panel: Number($('#s-pa').value), glass: Number($('#s-ga').value) };
  const favorites = [0, 1].map(i => ({ id: $(`[data-fav="${i}"]`).value, label: $(`[data-favlabel="${i}"]`).value.trim() || '출력 ' + (i + 1), icon: $(`[data-favicon="${i}"]`).value }));
  await api().save_settings({
    opacity, favorites, keyboard_url: $('#s-kb').value, projects_dir: $('#s-proj').value, mouse_provider: $('#s-mouse').value,
    game_close: $('#s-gclose').value, dev_close: $('#s-dclose').value, wsl_shutdown: $('#s-wsl').classList.contains('on'),
  });
  S.opacity = opacity; S.favs = favorites; renderAudioButtons(); pollStatus();
  $('#kb').hidden = !$('#s-kb').value.trim();
}

/* ---------------- 이벤트 ---------------- */
function bindEvents() {
  $$('.mi').forEach(m => m.onclick = () => openMenu(m.dataset.k));
  $('#rclose').onclick = () => openMenu(null);
  $('#rrefresh').onclick = async () => {
    if (S.menu === 'game') { $('#body').innerHTML = '<div class="empty">게임을 다시 찾는 중…</div>'; S.games = await api().games(true); $('#gcnt').textContent = S.games.length; }
    if (S.menu) PANELS[S.menu].render();
  };
  $('#mouse').onclick = async () => { if (!(await api().open_mouse_app())) notify('마우스 프로그램(G HUB / Razer Synapse)을 찾지 못했어요'); };
  $('#kb').onclick = () => api().open_keyboard();
  $('#yt').onclick = () => api().open_ytmusic();

  $$('#mod button').forEach(b => b.onclick = async () => {
    if (b.classList.contains('on') || S.busy.mod) return;
    S.busy.mod = true; setSeg('mod', b.dataset.v);
    await api().set_mode(b.dataset.v);
    notify(`${b.textContent.trim()}로 전환 중이에요`);
    setTimeout(() => S.busy.mod = false, 3000);
  });

  $$('.ctrl .cb').forEach(b => b.onclick = async () => { await api().media_control(b.dataset.m); setTimeout(pollMedia, 250); });
  const vol = $('#vol');
  let volTimer;
  vol.oninput = () => {
    S.volDrag = true; $('#volv').textContent = vol.value;
    clearTimeout(volTimer); volTimer = setTimeout(() => api().set_volume(Number(vol.value)), 60);
  };
  vol.onchange = () => { api().set_volume(Number(vol.value)); setTimeout(() => S.volDrag = false, 400); };
  $('#volbtn').onclick = async () => { await api().toggle_mute(); pollStatus(); };

  $('#gear').onclick = e => { e.stopPropagation(); $('#gearmenu').hidden = !$('#gearmenu').hidden; };
  document.addEventListener('click', () => $('#gearmenu').hidden = true);
  $$('#gearmenu button').forEach(b => b.onclick = async () => {
    const g = b.dataset.g;
    if (g === 'settings') openMenu(S.menu === 'settings' ? null : 'settings');
    if (g === 'theme') { applyTheme(await api().set_theme(document.body.classList.contains('dark') ? 'light' : 'dark')); if (S.menu === 'settings') renderSettings(); }
    if (g === 'rescan') { S.games = await api().games(true); $('#gcnt').textContent = S.games.length; if (S.menu === 'game') renderGames(); notify(`게임 ${S.games.length}개를 찾았어요`); }
    if (g === 'toast') { const ok = await api().chzzk_test(); notify(ok ? '알림을 보냈어요' : '알림을 띄우지 못했어요'); }
    if (g === 'reload') location.reload();
    if (g === 'quit' && await confirmBar('HUD를 종료할까요?')) api().quit();
  });

  $('#body').addEventListener('click', async e => {
    const t = e.target.closest('[data-hide],[data-webdel],[data-term],[data-game],[data-addgame],[data-link],[data-file],[data-open],[data-drive],[data-proj],[data-tool],[data-act],[data-bell],[data-del],[data-watch],[data-add],[data-gosettings]');
    if (!t) return;
    const d = t.dataset;
    if (d.hide) { e.stopPropagation(); if (await confirmBar(`'${t.closest('.tile').title}'을(를) 게임 목록에서 숨길까요?`)) { S.games = await api().hide_game(d.hide); $('#gcnt').textContent = S.games.length; renderGames(); } return; }
    if (d.webdel !== undefined) { e.stopPropagation(); S.web = await api().remove_web(Number(d.webdel)); renderLinks(S.web, true); return; }
    if (d.term !== undefined) { e.stopPropagation(); api().open_project(S.dev.projects[d.term].target, true); return; }
    if (d.game) { api().launch_game(d.game); notify(`${t.title} 실행 중…`); }
    else if (d.addgame) { const g = await api().add_game(); if (g) { S.games = g; $('#gcnt').textContent = g.length; renderGames(); notify('게임을 추가했어요'); } }
    else if (d.link !== undefined) { const it = (S.menu === 'msg' ? S.messengers : S.web)[d.link]; api().open(it.target, it.args || null); }
    else if (d.file !== undefined) api().open(S.fileItems[d.file].target);
    else if (d.open) api().open(d.open);
    else if (d.drive !== undefined) api().open(S.drives[d.drive].target);
    else if (d.proj !== undefined) api().open_project(S.dev.projects[d.proj].target, false);
    else if (d.tool !== undefined) {
      const tl = S.dev.tools[d.tool];
      if (tl.action === 'docker') { const on = await api().action('docker'); notify(on ? 'Docker를 켜는 중이에요' : 'Docker를 끄는 중이에요'); setTimeout(renderDev, 4000); }
      else api().open(tl.target, tl.args || null);
    }
    else if (d.act) runAction(d.act);
    else if (d.bell) { await api().chzzk_notify(d.bell, d.on !== '1'); renderLive(); }
    else if (d.del) { if (await confirmBar('이 스트리머를 목록에서 뺄까요?')) { await api().chzzk_remove(d.del); renderLive(); } }
    else if (d.watch) api().chzzk_open(d.watch);
    else if (d.add) { await api().chzzk_add(d.add, d.name, d.img); notify(`${d.name} 님을 추가했어요`); setTimeout(renderLive, 1500); }
    else if (d.gosettings) openMenu('settings');
  });
  $('#chips').addEventListener('click', e => {
    const c = e.target.closest('[data-f]'); if (!c) return;
    S.gameFilter = c.dataset.f; renderGames();
  });
}

async function runAction(k) {
  if (k === 'shutdown' && !(await confirmBar('1분 뒤에 PC를 끌까요? 그 전에 취소할 수 있어요.'))) return;
  if (k === 'empty_bin') {
    const info = await api().recycle_info();
    if (!info.count) { notify('휴지통이 이미 비어 있어요'); return; }
    if (!(await confirmBar(`휴지통의 ${info.count}개 항목(${info.sizeText})을 영구 삭제할까요? 되돌릴 수 없어요.`))) return;
    const res = await api().empty_recycle_bin();
    notify(res.ok ? `휴지통을 비웠어요 (${res.sizeText} 확보)` : '휴지통을 비우지 못했어요');
    S.bin = await api().recycle_info();
    if (S.menu === 'file') renderFiles(); else renderSys();
    return;
  }
  if (k === 'ram') { S.ramMsg = '정리 중…'; renderSys(); }
  const r = await api().action(k);
  if (k === 'ram') { S.ramMsg = `${r.freedGB}GB 확보`; notify(`RAM ${r.freedGB}GB를 확보했어요`); }
  if (k === 'monitor') notify(r === 'single' ? '모니터 1대로 바꾸는 중이에요' : '모니터 2대로 바꾸는 중이에요');
  if (k === 'disk') notify('디스크 정리를 열었어요');
  await pollStatus(); renderSys();
}

/* ---------------- 테마 ---------------- */
function applyTheme(theme, opacity) {
  const dark = theme === 'dark';
  document.body.classList.toggle('dark', dark);
  $('#themebtn').textContent = dark ? '밝은 테마로 바꾸기' : '어두운 테마로 바꾸기';
  const o = (opacity || S.opacity || {})[dark ? 'dark' : 'light'] || {};
  if (o.panel != null) document.body.style.setProperty('--pa', o.panel); else document.body.style.removeProperty('--pa');
  if (o.glass != null) document.body.style.setProperty('--ga', o.glass); else document.body.style.removeProperty('--ga');
}

/* ---------------- 시작 ---------------- */
window.addEventListener('pywebviewready', async () => {
  bindEvents();
  tickClock(); setInterval(tickClock, 1000);
  const d = await api().init();
  S.opacity = d.opacity; applyTheme(d.theme, d.opacity);
  S.games = d.games; S.messengers = d.messengers; S.web = d.web; S.favs = d.audioFavs;
  $('#kb').hidden = !d.hasKeyboard;
  $('#gcnt').textContent = S.games.length;
  renderAudioButtons(); setSeg('snd', d.audio); setSeg('mod', d.mode);
  pollStatus(); setInterval(pollStatus, 2000);
  pollMedia(); setInterval(pollMedia, 1500); setInterval(tickProgress, 250);
  setInterval(() => { if (S.menu === 'live') renderLive(); }, 30000);
  if (d.openPanel) openMenu(d.openPanel);
});
