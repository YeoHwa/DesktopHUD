'use strict';
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const api = () => window.pywebview.api;
const glyph = code => `<i class="g">${String.fromCharCode(parseInt(code, 16))}</i>`;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtTime = s => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
const DAYS = ['일', '월', '화', '수', '목', '금', '토'];

const S = { menu: null, games: [], gameFilter: '전체', messengers: [], web: [], links: {}, edit: false, media: null, mediaAt: 0, volDrag: false, busy: {}, favs: [] };

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
    S.stats = s;
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
    if (!S.busy.quick) renderQuick(st.quickButtons);
    if (!S.volDrag && st.volume.level != null) {
      $('#vol').value = st.volume.level; $('#volv').textContent = st.volume.muted ? '음소거' : st.volume.level;
      $('#volbtn').innerHTML = glyph(st.volume.muted ? 'E74F' : 'E767');
    }
    const lc = $('#livecnt'); lc.hidden = !st.live; lc.textContent = `${st.live} LIVE`;
    const vc = $('#vidcnt'); vc.hidden = !st.newVideos; vc.textContent = `새 영상 ${st.newVideos}`;
    S.quick = st.quick;
    if (S.menu === 'sys') { S.sysov = await api().sys_overview(); renderSys(); }
  } catch (e) { console.error(e); }
}

/* ---------------- 음악 ---------------- */
async function pollMedia() {
  try { S.media = await api().media(); S.mediaAt = performance.now(); renderMedia(); } catch (e) { console.error(e); }
}
function renderMedia() {
  const m = S.media;
  const pname = (S.player && S.player.name) || '음악 앱';
  if (!m || !m.ok || !m.title) {
    $('#title').textContent = '재생 중인 곡이 없어요';
    $('#artist').textContent = S.player && S.player.id !== 'any' ? `${pname}을(를) 열어 보세요` : '음악이나 영상을 재생해 보세요';
    $('#art').style.backgroundImage = ''; $('#art').innerHTML = glyph('E8D6');
    $('#pp').innerHTML = glyph('E768'); $('#cur').textContent = '0:00'; $('#dur').textContent = '0:00'; setBar('#progbar', 0);
    $('#plabel').textContent = '지금 재생 중';
    return;
  }
  $('#plabel').textContent = m.isPreferred ? pname : '지금 재생 중';
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
  live: { title: '라이브 바로가기', render: renderLive },
  msg: { title: '메신저·커뮤니티', render: renderMsg },
  file: { title: '내 파일', render: renderFiles },
  dev: { title: '작업 도구', render: renderWs },
  sys: { title: '시스템', render: async () => { S.sysHtml = null; renderSys(); [S.bin, S.sysov] = await Promise.all([api().recycle_info(), api().sys_overview()]); if (S.menu === 'sys') renderSys(); } },
  web: { title: '웹 바로가기', render: renderWeb },
  settings: { title: '설정', render: renderSettings },
};

async function openMenu(key) {
  const same = S.menu === key;
  $$('.mi').forEach(m => m.classList.remove('on'));
  const R = $('#right');
  if (same || !key) {
    // 닫기: 창이 줄어들기 전에 메뉴 창을 먼저 부드럽게 접는다
    S.menu = null; R.classList.remove('enter'); R.classList.add('leave');
    await new Promise(r => setTimeout(r, 160));
    R.hidden = true; R.classList.remove('leave');
    await api().set_expanded(false); $('#app').classList.remove('flip');
    return;
  }
  if (!S.menu) {
    // 열기: 창을 넓힌 뒤(오른쪽에 공간이 없으면 왼쪽으로) 메뉴 쪽에서 미끄러지듯 나타나게
    const r = await api().set_expanded(true);
    $('#app').classList.toggle('flip', !!(r && r.flip));
    R.classList.remove('enter'); void R.offsetWidth; R.classList.add('enter');
  }
  if (S.menu !== key) S.edit = false;
  S.menu = key;
  const mi = $(`.mi[data-k="${key}"]`); if (mi) mi.classList.add('on');
  R.hidden = false;
  $('#rt').textContent = key === 'dev' ? (S.wsTitle || PANELS.dev.title) : PANELS[key].title; $('#rs').textContent = ''; $('#chips').innerHTML = '';
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

/* ---------------- 라이브 (치지직 · SOOP · YouTube · Twitch) + 새 YouTube 영상 ---------------- */
const PLATS = ['chzzk', 'soop', 'youtube', 'twitch'];
const PLAT_HINT = {
  chzzk: '스트리머 이름으로 검색', soop: '스트리머 이름 또는 아이디로 검색',
  youtube: '채널 이름, @핸들 또는 채널 주소', twitch: '스트리머 이름 또는 아이디로 검색',
};
const platName = p => (S.platforms || {})[p] || p;
const platBadge = p => S.liveIcons && S.liveIcons[p] ? `<img class="pf" src="${S.liveIcons[p]}" alt="${esc(platName(p))}" title="${esc(platName(p))}">` : '';
const avatar = (img, live, p) => `<div class="av${live ? ' live' : ''}" style="${img ? `background-image:url('${esc(img)}')` : ''}">${img ? '' : glyph('E77B')}${p ? platBadge(p) : ''}</div>`;
const fmtCount = n => { n = Number(n) || 0; return n >= 1e8 ? `${+(n / 1e8).toFixed(1)}억` : n >= 1e4 ? `${+(n / 1e4).toFixed(1)}만` : n >= 1e3 ? `${+(n / 1e3).toFixed(1)}천` : `${n}`; };
const ago = ts => {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return '방금'; if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`; return `${Math.floor(s / 86400)}일 전`;
};

function renderLive() {
  // 검색 칸은 한 번만 그리고, 30초마다 갱신할 때는 목록 부분만 다시 그린다 (입력 중인 검색어가 지워지지 않게)
  S.livePlat = S.livePlat || 'chzzk';
  $('#body').innerHTML = `
    <div class="search live-search">
      <div class="seg plat" id="lplat">${PLATS.map(p => `<button data-plat="${p}">${S.liveIcons && S.liveIcons[p] ? `<img src="${S.liveIcons[p]}" alt="">` : ''}${esc(platName(p))}</button>`).join('')}</div>
      <input id="q" type="text"><button class="btn" id="qgo">검색</button></div>
    <div id="results"></div>
    <div class="hint">치지직 · SOOP · Twitch 는 1분마다, YouTube 는 3분마다 확인해요. 방송이 켜지거나 새 영상이 올라오면 Windows 알림을 띄워요 (종 모양으로 채널마다 끄기).</div>
    <div id="streams"><div class="empty">불러오는 중…</div></div>
    <div id="vsec"></div>`;
  const setPlat = p => { S.livePlat = p; $$('#lplat button').forEach(b => b.classList.toggle('on', b.dataset.plat === p)); $('#q').placeholder = PLAT_HINT[p]; };
  setPlat(S.livePlat);
  $$('#lplat button').forEach(b => b.onclick = () => { setPlat(b.dataset.plat); if ($('#q').value.trim()) go(); else $('#q').focus(); });
  const go = async () => {
    const q = $('#q').value.trim(), p = S.livePlat;
    if (!q) { $('#results').innerHTML = '<div class="hint" style="color:var(--danger)">검색어를 입력하세요</div>'; return; }
    $('#results').innerHTML = '<div class="hint">검색 중…</div>';
    const res = await api().live_search(p, q);
    if (S.menu !== 'live' || p !== S.livePlat) return;
    const added = new Set((S.live?.streamers || []).map(s => `${s.platform}:${s.id}`));
    $('#results').innerHTML = (res.length ? `<div class="res-head"><span class="sec">${esc(platName(p))} 검색 결과</span><button class="icon-btn" data-rclose="1" title="검색 결과 닫기">${glyph('E711')}</button></div>` : '') +
      (res.map(r => `<div class="sr">${avatar(r.image, r.live)}
        <div class="sr-text"><div class="sr-top">${r.live ? '<span class="lv">LIVE</span>' : ''}<b>${esc(r.name)}</b></div><div class="sr-sub">${esc(r.sub || '')}</div></div>
        ${added.has(`${p}:${r.id}`) ? '<span class="label">추가됨</span>' : `<button class="btn" data-add="${esc(r.id)}" data-p="${p}" data-name="${esc(r.name)}" data-img="${esc(r.image)}">추가</button>`}</div>`).join('')
        || '<div class="hint">검색 결과가 없어요</div>');
  };
  $('#qgo').onclick = go;
  $('#q').onkeydown = e => { if (e.key === 'Enter') go(); };
  $('#q').oninput = () => { if ($('#results').textContent.includes('검색어를')) $('#results').innerHTML = ''; };
  refreshLive();
}

async function refreshLive() {
  const d = await api().live_data();
  if (S.menu !== 'live' || !$('#streams')) return;
  S.live = d;
  const list = d.streamers;
  const live = list.filter(s => s.live).length;
  $('#rs').textContent = `방송 중 ${live}명 · 등록 ${list.length}명`;
  // 플랫폼 필터 (등록한 플랫폼이 둘 이상일 때만)
  const used = PLATS.filter(p => list.some(s => s.platform === p));
  if (!used.includes(S.liveFilter)) S.liveFilter = '전체';
  $('#chips').innerHTML = used.length > 1 ? ['전체', ...used].map(p => {
    const n = p === '전체' ? live : list.filter(s => s.platform === p && s.live).length;
    return `<button class="chip${p === S.liveFilter ? ' on' : ''}" data-lf="${p}">${p === '전체' ? '전체' : esc(platName(p))}${n ? ` · ${n}` : ''}</button>`;
  }).join('') : '';
  // '전체'에서는 YouTube 채널을 숨길 수 있다 (YouTube 는 라이브보다 영상을 보러 가는 경우가 많아서, 아래 영상 목록만)
  // YouTube 라이브는 아래 영상 목록에 LIVE 로 나오고, 채널 관리는 YouTube 칩에서 한다
  const hideYT = d.hideChannels && S.liveFilter === '전체';
  const ytCount = list.filter(s => s.platform === 'youtube').length;
  const shown = list.filter(s => S.liveFilter === '전체' ? !(hideYT && s.platform === 'youtube') : s.platform === S.liveFilter);
  const newBy = {};
  d.videos.forEach(v => { newBy[v.channel] = (newBy[v.channel] || 0) + 1; });
  $('#streams').innerHTML = shown.map(s => {
    const off = s.checked ? '방송 꺼짐' : '확인 중…';
    const sub = s.live ? [s.title, s.category].filter(Boolean).join(' · ')
      : (s.platform === 'youtube' && newBy[s.id] ? `${off} · 새 영상 ${newBy[s.id]}개` : off);
    const k = `data-p="${s.platform}"`;
    return `<div class="sr${s.live ? '' : ' off'}">${avatar(s.image, s.live, s.platform)}
      <div class="sr-text"><div class="sr-top">${s.live ? '<span class="lv">LIVE</span>' : ''}<b>${esc(s.name)}</b>${s.live && s.viewers ? `<span class="label">${Number(s.viewers).toLocaleString()}명</span>` : ''}</div>
      <div class="sr-sub" title="${esc(sub)}">${esc(sub)}</div></div>
      <button class="icon-btn" data-bell="${esc(s.id)}" ${k} data-on="${s.notify ? 1 : 0}" title="${s.platform === 'youtube' ? '방송·새 영상' : '방송'} 알림 ${s.notify ? '끄기' : '켜기'}">${glyph(s.notify ? 'EA8F' : 'E7ED')}</button>
      <button class="icon-btn" data-del="${esc(s.id)}" ${k} title="목록에서 빼기">${glyph('E74D')}</button>
      ${s.live ? `<button class="btn" data-watch="${esc(s.id)}" ${k}>시청</button>` : ''}
    </div>`;
  }).join('') || (hideYT && ytCount && shown.length === 0 ? '' : `<div class="empty">${list.length ? '이 플랫폼에 등록한 스트리머가 없어요.' : '아직 등록한 스트리머가 없어요. 위에서 플랫폼을 고르고 검색해 추가하세요.'}</div>`);
  if (hideYT && ytCount) {
    $('#streams').insertAdjacentHTML('beforeend', `<button class="yt-note" data-golf="youtube">${S.liveIcons && S.liveIcons.youtube ? `<img src="${S.liveIcons.youtube}" alt="">` : ''}
      <span>YouTube 채널 ${ytCount}개는 목록에서 숨기고, 아래에 새 영상만 보여 줘요</span><b>채널 관리</b></button>`);
  }
  renderVideos(d);
}

function renderVideos(d) {
  const hasYT = d.streamers.some(s => s.platform === 'youtube');
  if (!hasYT) { $('#vsec').innerHTML = ''; return; }
  const vids = d.videos;
  $('#vsec').innerHTML = `<div class="vsec-head"><span class="vsec-title">새로운 유튜브 동영상</span>${vids.length ? `<span class="label">${vids.length}개</span>` : ''}
      <span class="vsec-tools"><span class="label" title="켜면 '전체'에서 YouTube 채널 줄을 숨기고 영상만 보여 줘요">전체에서 채널 숨기기</span><button class="switch${d.hideChannels ? ' on' : ''}" data-ythide="1" aria-label="전체에서 YouTube 채널 숨기기"></button>
      <span class="label">쇼츠 숨기기</span><button class="switch${d.hideShorts ? ' on' : ''}" data-shorts="1" aria-label="쇼츠 숨기기"></button>
      ${vids.length ? '<button class="btn ghost" data-vall="1">모두 읽음</button>' : ''}</span></div>
    ${vids.length ? `<div class="vgrid">${vids.map(v => `<div class="vc" data-video="${esc(v.id)}" title="${esc(v.title)}">
        <div class="vthumb" style="background-image:url('${esc(v.thumb)}')">${v.live ? '<span class="lv">LIVE</span>' : v.short ? '<span class="vbadge">쇼츠</span>' : ''}</div>
        <div class="vinfo"><div class="vtitle">${esc(v.title)}</div>
          <div class="vch"><span class="vav" style="${v.channelImage ? `background-image:url('${esc(v.channelImage)}')` : ''}"></span><span>${esc(v.channelName)}</span></div>
          <div class="vmeta">${v.live ? (v.viewers ? `지금 라이브 · ${fmtCount(v.viewers)}명 시청 중` : '지금 라이브') : `조회수 ${fmtCount(v.views)}회 · ${ago(v.published)}`}</div></div>
        <button class="vx" data-vdismiss="${esc(v.id)}" title="목록에서 지우기">${glyph('E711')}</button>
      </div>`).join('')}</div>`
    : '<div class="empty">새 영상이 없어요. 등록한 채널에 영상이 올라오면 여기에 나와요.</div>'}`;
}

/* ---------------- 고칠 수 있는 바로가기 격자 (메신저 · 웹 바로가기 · 작업 도구) ----------------
   kind: 'msg' | 'web' | 'ws:<묶음 id>'. '편집'을 켜면 지우기 · 순서 바꾸기 · 눌러서 이름 바꾸기 */
function linkGrid(kind, items) {
  S.links[kind] = items;
  const ed = S.edit, k = esc(kind);
  const tiles = items.map((m, i) => {
    const corner = ed ? `<span class="hide show" data-ldel="1" data-lk="${k}" data-li="${i}" title="지우기">${glyph('E711')}</span>
      <span class="mv"><span data-lmv="-1" data-lk="${k}" data-li="${i}" title="앞으로"${i === 0 ? ' hidden' : ''}>${glyph('E76B')}</span><span data-lmv="1" data-lk="${k}" data-li="${i}" title="뒤로"${i === items.length - 1 ? ' hidden' : ''}>${glyph('E76C')}</span></span>` : '';
    return tile({ name: m.name, sub: ed ? '눌러서 이름 바꾸기' : m.sub, icon: m.icon, glyph: m.glyph || 'E8A7',
      on: !ed && m.action === 'docker' && m.sub === '실행 중', cls: ed ? 'editing' : '', data: { lk: kind, li: i }, corner });
  }).join('');
  const add = kind === 'web' ? '' : tile({ name: '추가', sub: '앱 · 파일 · 웹 주소', glyph: 'E710', cls: 'add', data: { addto: kind } });
  return `<div class="grid">${tiles}${add}</div><div data-boxslot="${k}"></div>`;
}
const editChip = () => `<button class="chip${S.edit ? ' on' : ''}" data-edit="1">${S.edit ? '편집 끝내기' : '편집'}</button>`;

// '추가' → 설치된 앱 목록에서 고르기 / 파일에서 고르기 / 웹 주소
async function openAddBox(kind) {
  $$('[data-boxslot]').forEach(b => b.innerHTML = '');
  const slot = $(`[data-boxslot="${kind}"]`);
  if (!slot) return;
  const k = esc(kind);
  slot.innerHTML = `<div class="addbox">
    <div class="addbox-head"><div class="seg atabs"><button data-atab="app" class="on">설치된 앱</button><button data-atab="web">웹 주소</button></div>
      <button class="btn ghost" data-afile="${k}">파일에서 고르기…</button>
      <button class="icon-btn" data-aclose="1" title="닫기">${glyph('E711')}</button></div>
    <div data-atabbody="app"><input type="text" class="afilter" placeholder="앱 이름으로 찾기"><div class="alist"><div class="hint">앱 목록을 불러오는 중…</div></div></div>
    <div data-atabbody="web" hidden><div class="search" style="margin:0"><input class="aname" type="text" placeholder="이름 (예: 네이버)" style="max-width:180px"><input class="aurl" type="text" placeholder="주소 (예: google.com)"><button class="btn" data-aweb="${k}">추가</button></div></div>
  </div>`;
  const box = $('.addbox', slot);
  $('.afilter', box).focus();
  S.apps = S.apps || await api().app_choices();
  const draw = () => {
    const q = $('.afilter', box).value.trim().toLowerCase();
    const list = S.apps.filter(a => !q || a.name.toLowerCase().includes(q)).slice(0, 80);
    $('.alist', box).innerHTML = list.map(a => `<button class="arow" data-arow="${k}" data-name="${esc(a.name)}" data-target="${esc(a.target)}">${glyph('ECAA')}<span>${esc(a.name)}</span></button>`).join('')
      || '<div class="hint">찾는 앱이 없어요. "파일에서 고르기"로 실행 파일을 직접 고를 수 있어요.</div>';
  };
  $('.afilter', box).oninput = draw;
  draw();
}

async function runDetect(kind) {
  notify('설치된 프로그램을 찾는 중…');
  const added = await api().links_detect(kind, true);
  notify(added.length ? `${added.join(', ')}을(를) 찾아서 추가했어요` : '새로 찾은 프로그램이 없어요');
  await linksChanged(kind, await api().links(kind));
}

async function linksChanged(kind, items) {
  if (kind === 'msg') { S.messengers = items; drawMsg(); }
  else if (kind === 'web') { S.web = items; drawWeb(); }
  else { S.ws = await api().workspace(); drawWs(); }
}

/* 메신저 · 커뮤니티: 설치된 메신저를 자동으로 찾고, 새로 설치하면 알아서 더한다 */
function drawMsg() {
  if (S.menu !== 'msg') return;
  $('#rs').textContent = '설치된 메신저를 자동으로 찾아 넣어요';
  $('#chips').innerHTML = editChip() + `<button class="chip" data-detect="msg">${glyph('E72C')} 새 메신저 찾기</button>`;
  $('#body').innerHTML = linkGrid('msg', S.messengers)
    + (S.messengers.length ? '' : '<div class="empty">찾은 메신저가 없어요. "추가"로 앱이나 커뮤니티 사이트를 직접 넣을 수 있어요.</div>')
    + '<div class="hint">메신저를 새로 설치하면 이 메뉴를 열 때 자동으로 추가돼요. 지운 항목은 다시 들어오지 않아요. 집중 모드는 여기 있는 메신저를 꺼요.</div>';
}
async function renderMsg() {
  drawMsg();
  S.messengers = await api().links('msg'); drawMsg();
  const added = await api().links_detect('msg', false);
  if (added && added.length) { notify(`${added.join(', ')}을(를) 찾아서 추가했어요`); S.messengers = await api().links('msg'); drawMsg(); }
}

/* 웹 바로가기: 추가 칸을 맨 위에 */
function drawWeb() {
  if (S.menu !== 'web') return;
  $('#rs').textContent = '자주 가는 사이트';
  $('#chips').innerHTML = editChip();
  const keep = { name: $('#wname')?.value || '', url: $('#wurl')?.value || '' };
  $('#body').innerHTML = `<div class="search web-add"><input id="wname" type="text" placeholder="이름 (예: 네이버)" style="max-width:200px"><input id="wurl" type="text" placeholder="주소 (예: google.com)"><button class="btn" id="wadd">추가</button></div>
    <div id="werr" class="hint" style="margin:-2px 0 10px"></div>` + linkGrid('web', S.web);
  $('#wname').value = keep.name; $('#wurl').value = keep.url;
  const add = async () => {
    const name = $('#wname').value.trim(), url = $('#wurl').value.trim();
    if (!url) { $('#werr').textContent = '주소를 입력하세요'; $('#werr').style.color = 'var(--danger)'; return; }
    $('#wname').value = ''; $('#wurl').value = '';
    await linksChanged('web', await api().links_add('web', { name, target: url, type: 'web' })); notify('바로가기를 추가했어요');
  };
  $('#wadd').onclick = add;
  $('#wurl').onkeydown = e => { if (e.key === 'Enter') add(); };
  $('#wname').onkeydown = e => { if (e.key === 'Enter') $('#wurl').focus(); };
  $('#wurl').oninput = () => $('#werr').textContent = '';
}
async function renderWeb() { drawWeb(); S.web = await api().links('web'); drawWeb(); }

/* 작업 도구: 분야별(개발 · 음악 · 영상 · 디자인 …) 프로그램 묶음 + 작업 폴더 */
function setWsTitle(t) {
  S.wsTitle = t || '작업 도구';
  MENU_NAMES.dev = S.wsTitle;
  const mi = $('.mi[data-k="dev"] .mtx'); if (mi) mi.textContent = S.wsTitle;
  if (S.menu === 'dev') $('#rt').textContent = S.wsTitle;
}
function drawWs() {
  const w = S.ws;
  if (S.menu !== 'dev' || !w) return;
  setWsTitle(w.title);
  $('#rs').textContent = '분야별 프로그램과 작업 폴더';
  $('#chips').innerHTML = editChip() + `<button class="chip" data-gadd="1">${glyph('E710')} 묶음 추가</button>`
    + (S.edit ? '<button class="chip" data-wstitle="1">메뉴 이름 바꾸기</button>' : '');
  const groups = w.groups.map((g, gi) => {
    const kind = `ws:${g.id}`;
    const tools = S.edit ? `<span class="grp-tools">
        <button class="icon-btn" data-grename="${esc(g.id)}" title="묶음 이름 바꾸기">${glyph('E8AC')}</button>
        <button class="icon-btn" data-gmove="${esc(g.id)}" data-d="-1" title="위로"${gi === 0 ? ' disabled' : ''}>${glyph('E70E')}</button>
        <button class="icon-btn" data-gmove="${esc(g.id)}" data-d="1" title="아래로"${gi === w.groups.length - 1 ? ' disabled' : ''}>${glyph('E70D')}</button>
        <button class="icon-btn" data-gdel="${esc(g.id)}" title="묶음 지우기">${glyph('E74D')}</button></span>`
      : (g.field ? `<span class="grp-tools"><button class="icon-btn" data-detect="${esc(kind)}" title="새로 설치한 프로그램 찾기">${glyph('E72C')}</button></span>` : '');
    return `<div class="grp-head"><span class="sec">${esc(g.name)}</span>${tools}</div>${linkGrid(kind, g.items)}`;
  }).join('') || '<div class="empty">"묶음 추가"로 하는 작업(개발, 음악, 영상 편집 …)을 고르면 설치된 프로그램을 찾아서 넣어 드려요.</div>';
  const corner = i => w.terminal ? `<span class="corner" data-term="${i}" title="터미널에서 열기">${glyph('E756')}</span>` : '';
  const folder = w.folder
    ? `<div class="grp-head"><span class="sec">작업 폴더 · ${esc(w.folder)}</span><span class="grp-tools"><button class="icon-btn" data-wsfolder="1" title="작업 폴더 바꾸기">${glyph('E8DA')}</button></span></div>
       <div class="grid">${w.projects.map((p, i) => tile({ name: p.name, sub: '폴더 열기', glyph: 'E8B7', data: { proj: i }, corner: corner(i) })).join('') || '<div class="empty">폴더가 비어 있어요</div>'}</div>`
    : `<div class="grp-head"><span class="sec">작업 폴더</span></div>
       <div class="empty">프로젝트나 작업 파일을 모아 둔 폴더를 고르면, 그 안의 폴더를 여기서 바로 열 수 있어요 <button class="btn ghost" data-wsfolder="1">폴더 고르기</button></div>`;
  $('#body').innerHTML = '<div id="grppick"></div>' + groups + folder;
}
async function renderWs() { if (S.ws) drawWs(); S.ws = await api().workspace(); drawWs(); }

function showGroupPicker() {
  const used = new Set(S.ws.groups.map(g => g.field));
  $('#grppick').innerHTML = `<div class="addbox"><div class="addbox-head"><b>어떤 작업을 하세요?</b>
      <span class="hint" style="margin:0">고르면 이 PC 에 설치된 관련 프로그램을 찾아서 넣어 드려요</span>
      <button class="icon-btn" data-aclose="1" title="닫기">${glyph('E711')}</button></div>
    <div class="fields">${S.ws.fields.map(f => `<button class="fieldbtn${used.has(f.id) ? ' used' : ''}" data-gfield="${f.id}" data-name="${esc(f.name)}">${glyph(f.glyph)}<span>${esc(f.name)}</span>${used.has(f.id) ? '<small>추가됨</small>' : ''}</button>`).join('')}
      <button class="fieldbtn" data-gfield="" data-name="">${glyph('E710')}<span>직접 만들기</span></button></div></div>`;
}

// 이름 입력 받기 (확인 바에 입력 칸을 붙여서)
function promptBar(msg, value) {
  return new Promise(res => {
    const inp = $('#cinput');
    $('#cmsg').textContent = msg; inp.hidden = false; inp.value = value || ''; $('#confirm').hidden = false;
    setTimeout(() => { inp.focus(); inp.select(); }, 0);
    const done = v => { $('#confirm').hidden = true; inp.hidden = true; inp.onkeydown = null; res(v); };
    $('#cyes').onclick = () => done(inp.value.trim() || null);
    $('#cno').onclick = () => done(null);
    inp.onkeydown = e => { if (e.key === 'Enter') done(inp.value.trim() || null); if (e.key === 'Escape') { e.stopPropagation(); done(null); } };
  });
}

// 바로가기 / 작업 도구 관련 클릭 (본문 클릭 처리에서 먼저 부른다). 처리했으면 true
async function handleLinkClick(e, t) {
  const d = t.dataset;
  if (d.ldel) {
    e.stopPropagation();
    const it = S.links[d.lk][Number(d.li)];
    if (await confirmBar(`'${it.name}'을(를) 목록에서 지울까요?`)) await linksChanged(d.lk, await api().links_remove(d.lk, Number(d.li)));
    return true;
  }
  if (d.lmv) { e.stopPropagation(); await linksChanged(d.lk, await api().links_move(d.lk, Number(d.li), Number(d.lmv))); return true; }
  if (d.lk !== undefined && d.li !== undefined) {
    const it = S.links[d.lk][Number(d.li)];
    if (S.edit) {
      const name = await promptBar('새 이름', it.name);
      if (name) await linksChanged(d.lk, await api().links_rename(d.lk, Number(d.li), name));
    } else if (it.action === 'docker') {
      const on = await api().action('docker'); notify(on ? 'Docker를 켜는 중이에요' : 'Docker를 끄는 중이에요'); setTimeout(renderWs, 4000);
    } else {
      api().open(it.target, it.args || null);
    }
    return true;
  }
  if (d.addto) { openAddBox(d.addto); return true; }
  if (d.aclose) { t.closest('.addbox').remove(); return true; }
  if (d.atab) {
    const box = t.closest('.addbox');
    $$('[data-atab]', box).forEach(b => b.classList.toggle('on', b === t));
    $$('[data-atabbody]', box).forEach(b => b.hidden = b.dataset.atabbody !== d.atab);
    const f = $(d.atab === 'web' ? '.aname' : '.afilter', box); if (f) f.focus();
    return true;
  }
  if (d.arow) { await linksChanged(d.arow, await api().links_add(d.arow, { name: d.name, target: d.target, type: 'app' })); notify(`${d.name}을(를) 추가했어요`); return true; }
  if (d.afile) {
    const f = await api().pick_app_file();
    if (f) { await linksChanged(d.afile, await api().links_add(d.afile, { ...f, type: 'app' })); notify(`${f.name}을(를) 추가했어요`); }
    return true;
  }
  if (d.aweb) {
    const box = t.closest('.addbox'), name = $('.aname', box).value.trim(), url = $('.aurl', box).value.trim();
    if (!url) { $('.aurl', box).focus(); return true; }
    await linksChanged(d.aweb, await api().links_add(d.aweb, { name, target: url, type: 'web' })); notify('바로가기를 추가했어요');
    return true;
  }
  if (d.grename) {
    const g = S.ws.groups.find(x => x.id === d.grename);
    const name = await promptBar('묶음 이름', g.name);
    if (name) { S.ws = await api().ws_rename_group(d.grename, name); drawWs(); }
    return true;
  }
  if (d.gmove) { S.ws = await api().ws_move_group(d.gmove, Number(d.d)); drawWs(); return true; }
  if (d.gdel) {
    const g = S.ws.groups.find(x => x.id === d.gdel);
    if (await confirmBar(`'${g.name}' 묶음과 그 안의 바로가기를 지울까요? (프로그램은 지워지지 않아요)`)) { S.ws = await api().ws_remove_group(d.gdel); drawWs(); }
    return true;
  }
  if (d.gfield !== undefined) {
    let name = d.name;
    if (!d.gfield) { name = await promptBar('새 묶음 이름 (예: 업무, 공부)', ''); if (!name) return true; }
    $('#grppick').innerHTML = '<div class="hint">설치된 프로그램을 찾는 중…</div>';
    S.ws = await api().ws_add_group(d.gfield, name); drawWs();
    const g = S.ws.groups[S.ws.groups.length - 1];
    notify(d.gfield ? `'${g.name}' 묶음에 프로그램 ${g.items.length}개를 찾아 넣었어요` : `'${g.name}' 묶음을 만들었어요`);
    return true;
  }
  if (d.wsfolder) {
    const p = await api().pick_folder();
    if (p) { S.ws = await api().ws_set(null, p); drawWs(); }
    return true;
  }
  return false;
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

/* 시스템: 위쪽 상태 카드(CPU · RAM · GPU · 켜진 시간) + 묶음별 큰 버튼 카드 */
const fmtUptime = s => {
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return d ? `${d}일 ${h}시간` : h ? `${h}시간 ${m}분` : `${m}분`;
};
function statCard(label, value, pct, low) {
  return `<div class="stc"><span class="label">${label}</span><b>${value}</b>${pct == null ? '<span class="bar" style="visibility:hidden"><i></i></span>' : `<span class="bar${low ? ' low' : ''}"><i style="width:${Math.max(0, Math.min(100, pct))}%"></i></span>`}</div>`;
}
function wideCard({ k, name, sub, glyph: gl, on, warn, quick }) {
  return `<button class="wcard${on ? ' on' : ''}${warn ? ' warn' : ''}" ${quick ? 'data-sq' : 'data-act'}="${k}" title="${esc(name)}">
    ${glyph(gl)}<span class="wtx"><b>${esc(name)}</b><small>${esc(sub || '')}</small></span></button>`;
}
function renderSys() {
  const q = S.quick || {}, st = S.stats || {}, ov = S.sysov || {};
  $('#rs').textContent = '상태 확인과 버튼 하나로 실행';
  const stats = [
    statCard('CPU', st.cpu == null ? '-' : `${st.cpu}%`, st.cpu),
    statCard(`RAM · ${st.ramUsed ?? '-'} / ${st.ramTotal ?? '-'}GB`, st.ramPct == null ? '-' : `${st.ramPct}%`, st.ramPct, st.ramPct > 90),
    st.gpu != null ? statCard(`GPU${ov.gpuTemp != null ? ` · ${ov.gpuTemp}°C` : ''}`, `${st.gpu}%`, st.gpu)
      : (ov.disk ? statCard(`디스크 ${esc(ov.disk.name)} · ${esc(ov.disk.free)} 남음`, `${ov.disk.pct}%`, ov.disk.pct, ov.disk.pct > 90) : ''),
    statCard('켜진 시간', ov.uptime != null ? fmtUptime(ov.uptime) : '-', null),
  ].join('');
  const disk = ov.disk;
  const groups = [
    ['빠른 정리', [
      { k: 'ram', name: 'RAM 청소', sub: S.ramMsg || (ov.ramFree != null ? `지금 ${ov.ramFree}GB 남음` : '메모리 회수'), glyph: 'E945' },
      { k: 'disk', name: '디스크 청소', sub: disk ? `${disk.name} ${disk.pct}% 사용 · ${disk.free} 남음` : 'Windows 디스크 정리', glyph: 'E75C', warn: disk && disk.pct > 90 },
      { k: 'empty_bin', name: '휴지통 비우기', sub: S.bin ? (S.bin.count ? `${S.bin.count}개 · ${S.bin.sizeText}` : '비어 있음') : '영구 삭제', glyph: 'E894', warn: S.bin && S.bin.count > 0 },
    ]],
    ['화면 · 집중', [
      { k: 'focus', name: '집중 모드', sub: q.focus ? '켜짐 · 메신저 꺼짐' : '메신저를 잠시 꺼요', glyph: 'E7ED', on: q.focus },
      { k: 'monitor', name: '모니터 1/2', sub: q.monitors > 1 ? `지금 ${q.monitors}대 → 1대` : '지금 1대 → 2대', glyph: 'E7F4' },
      q.hasWallpaper ? { k: 'wallpaper', name: '배경 멈춤', sub: q.wallpaperPaused ? '멈춤 · 눌러서 재생' : '재생 중', glyph: 'E8B9', on: q.wallpaperPaused } : null,
    ]],
    ['전원', [
      { k: 'lock', name: '화면 잠금', sub: '바로 잠그기', glyph: 'E72E', quick: true },
      { k: 'sleep', name: '절전', sub: '확인 후 절전 모드', glyph: 'E708', quick: true },
      q.shutdownIn != null
        ? { k: 'cancel_shutdown', name: '종료 취소', sub: `${q.shutdownIn}초 뒤 종료`, glyph: 'E7E8', warn: true }
        : { k: 'shutdown', name: '안전 종료', sub: '1분 뒤 · 그 전에 취소 가능', glyph: 'E7E8' },
    ]],
  ];
  const html = `<div class="stats-row">${stats}</div>` + groups.map(([title, items]) =>
    `<div class="sec">${title}</div><div class="wgrid">${items.filter(Boolean).map(wideCard).join('')}</div>`).join('');
  if (html === S.sysHtml && $('#body .stats-row')) return;     // 2초마다 갱신할 때 바뀐 게 없으면 그대로 (마우스 올림 상태 유지)
  S.sysHtml = html;
  $('#body').innerHTML = html;
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
    <div class="set"><h4>HUD 불러오기 단축키</h4><div class="desc">어느 창에 있든 이 단축키를 누르면 HUD가 맨 앞에 떠요. 단축키를 한 번 더 누르거나, Esc를 누르거나, 다른 창을 누르면 다시 바탕화면으로 돌아가요.</div>
      <div class="row"><button class="keycap" id="s-hk" title="눌러서 새 단축키 입력">${esc(s.hotkey || '꺼짐')}</button>
        <button class="btn ghost" id="s-hk-off"${s.hotkey ? '' : ' hidden'}>끄기</button><span class="hint" id="s-hk-msg" style="margin:0">바꾸려면 단추를 누른 뒤 새 조합을 누르세요</span></div></div>
    <div class="set"><h4>모양</h4>
      <div class="row"><label>테마</label><div class="seg" id="s-theme" style="flex:none;width:200px"><button data-v="light">밝게</button><button data-v="dark">어둡게</button></div></div>
      <div class="row"><label>글꼴</label><div class="seg" id="s-font" style="flex:none;width:300px"><button data-v="pretendard" style="font-family:Pretendard">Pretendard</button><button data-v="suit" style="font-family:SUIT">SUIT</button><button data-v="system">Windows 기본</button></div></div>
      <div class="row"><label>숫자 글꼴</label><div class="seg" id="s-num" style="flex:none;width:300px"><button data-v="rajdhani" style="font-family:Rajdhani;font-size:13px">Rajdhani 0123</button><button data-v="body">본문 글꼴과 같게</button></div></div>
      <div class="row"><label>왼쪽 패널 투명도</label>${numSlider('s-pa', 0, 95, 1, transp(op.panel ?? 0.7), '%')}</div>
      <div class="row"><label>오른쪽 창 투명도</label>${numSlider('s-ga', 0, 95, 1, transp(op.glass ?? 0.4), '%')}</div>
      <div class="desc">0% = 완전히 불투명, 숫자가 클수록 배경화면이 더 비쳐 보여요. 움직이면 바로 미리 보이고, 저장하면 유지돼요. (테마마다 따로 저장)</div></div>
    <div class="set"><h4>위치·크기</h4><div class="desc">시계 부분을 끌어서 옮길 수도 있어요. 오른쪽에 두면 메뉴 창이 왼쪽으로 열려요.</div>
      <div class="row"><label>모니터</label><select id="s-mon" style="flex:none;min-width:240px">${s.monitors.map(m => `<option value="${m.index}"${m.index === s.layout.monitor ? ' selected' : ''}>${esc(m.name)}</option>`).join('')}</select></div>
      <div class="row"><label>붙일 쪽</label><div class="seg" id="s-side" style="flex:none;width:200px"><button data-v="left">왼쪽</button><button data-v="right">오른쪽</button></div></div>
      <div class="row"><label>가장자리 여백</label>${numSlider('s-mx', 0, 600, 4, s.layout.margin_x, 'px')}</div>
      <div class="row"><label>위쪽 여백</label>${numSlider('s-my', 0, 400, 4, s.layout.margin_y, 'px')}</div>
      <div class="row"><label>크기</label>${numSlider('s-scale', 70, 160, 5, Math.round(s.layout.scale * 100), '%')}</div>
      <div class="row"><label>메뉴 창 너비</label>${numSlider('s-pw', 480, 1400, 20, s.layout.panel_width, 'px')}</div>
      <div class="row"><label>높이</label><div class="seg" id="s-hmode" style="flex:none;width:200px"><button data-v="fit">화면에 맞춤</button><button data-v="custom">직접 지정</button></div>
        <span id="s-h-wrap"${s.layout.height_mode === 'custom' ? '' : ' hidden'}>${numSlider('s-h', 480, 2000, 10, s.layout.height, 'px')}</span></div>
      <div class="row"><button class="btn" id="s-layout-apply">위치·크기 적용</button><span class="hint" id="s-layout-msg" style="margin:0"></span></div></div>
    <div class="set"><h4>소리 출력 버튼</h4><div class="desc">왼쪽 위 두 버튼에 연결할 출력 장치예요. '사용 안 함' 장치도 고르면 자동으로 켜져요.</div>
      ${favRow(0)}${favRow(1)}</div>
    <div class="set"><h4>빠른 버튼</h4><div class="desc">왼쪽 위 소리 버튼 아래의 네 칸에 넣을 기능이에요.</div>
      <div class="row">${[0, 1, 2, 3].map(i => `<select data-qslot="${i}" style="flex:1;min-width:120px">${s.quick_choices.map(c => `<option value="${c.id}"${s.quick[i] === c.id ? ' selected' : ''}>${esc(c.name)}</option>`).join('')}</select>`).join('')}</div></div>
    <div class="set"><h4>음악 플레이어</h4><div class="desc">왼쪽 아래 플레이어가 먼저 보여 줄 앱이에요. 버튼을 누르면 이 앱이 열려요.</div>
      <div class="row"><label>플레이어</label><select id="s-player" style="flex:none;min-width:220px">
        ${s.players.map(p => `<option value="${p.id}"${s.player === p.id ? ' selected' : ''}>${esc(p.name)}${p.installed ? '' : ' (웹)'}</option>`).join('')}
        <option value="custom"${s.player === 'custom' ? ' selected' : ''}>직접 고르기…</option>
      </select></div>
      <div class="row" id="s-custom-row"${s.player === 'custom' ? '' : ' hidden'}><label>앱</label>
        <select id="s-custom"><option value="">${s.player_custom.target ? esc(s.player_custom.name) : '불러오는 중…'}</option></select></div></div>
    <div class="set"><h4>왼쪽 메뉴 순서</h4><div class="desc">화살표로 순서를 바꾸고, 스위치로 메뉴를 숨길 수 있어요.</div>
      <div id="s-menu"></div></div>
    <div class="set"><h4>마우스 배터리</h4><div class="desc">Logitech(G HUB 필요)과 Razer(Synapse 없어도 됨) 무선 마우스를 지원해요. 바꾼 뒤에는 HUD를 다시 켜야 적용돼요.</div>
      <div class="row"><label>읽는 곳</label><select id="s-mouse" style="flex:none;min-width:220px">
        ${[['auto', '자동 (Logitech / Razer)'], ['ghub', 'Logitech · G HUB 로'], ['logitech', 'Logitech · 수신기에서 직접'], ['razer', 'Razer'], ['off', '표시 안 함']].map(([v, t]) => `<option value="${v}"${s.mouse_provider === v ? ' selected' : ''}>${t}</option>`).join('')}
      </select></div></div>
    <div class="set"><h4>키보드 버튼</h4><div class="desc">키보드 아이콘을 누르면 열 주소예요. 비워 두면 버튼이 숨겨져요.</div>
      <div class="row"><input type="text" id="s-kb" value="${esc(s.keyboard_url)}" placeholder="https://"></div></div>
    <div class="set"><h4>작업 폴더</h4><div class="desc">'작업 도구' 메뉴 아래쪽에 이 폴더 안의 폴더들이 나와요. (프로젝트, 곡 작업 폴더 등)</div>
      <div class="row"><input type="text" id="s-proj" value="${esc(s.projects_dir)}" placeholder="예: D:\\작업"><button class="btn ghost" id="s-proj-pick">찾아보기</button></div></div>
    <div class="row" style="gap:6px;margin:4px 0 8px"><button class="btn" id="s-save">저장</button><button class="btn ghost" id="s-cfg">설정 파일 열기</button><button class="btn ghost" id="s-log">로그 열기</button><span class="hint" id="s-msg" style="margin:0"></span></div>`;
  setSeg('s-theme', theme);
  // 글꼴: 누르면 바로 미리 적용, 저장하면 유지
  const font = { body: s.font.body || 'pretendard', num: s.font.num || 'rajdhani' };
  setSeg('s-font', font.body); setSeg('s-num', font.num);
  $$('#s-font button').forEach(b => b.onclick = () => { setSeg('s-font', b.dataset.v); applyFont({ ...curFont(), body: b.dataset.v }); });
  $$('#s-num button').forEach(b => b.onclick = () => { setSeg('s-num', b.dataset.v); applyFont({ ...curFont(), num: b.dataset.v }); });
  // 음악 플레이어: '직접 고르기' 를 고르면 시작 메뉴 앱 목록을 불러온다
  const loadCustom = async () => {
    const apps = await api().list_start_apps();
    const cur = s.player_custom.target || '';
    $('#s-custom').innerHTML = `<option value="">앱을 고르세요</option>` +
      apps.map(a => `<option value="${esc(a.target)}"${a.target === cur ? ' selected' : ''}>${esc(a.name)}</option>`).join('');
  };
  if (s.player === 'custom') loadCustom();
  $('#s-player').onchange = () => { const c = $('#s-player').value === 'custom'; $('#s-custom-row').hidden = !c; if (c) loadCustom(); };
  // 메뉴 순서
  S.menuDraft = JSON.parse(JSON.stringify(s.menu));
  renderMenuOrder();
  // 투명도: 슬라이더와 숫자 칸이 서로 맞춰지고, 바로 미리 보기
  bindNumSliders();
  const previewOp = () => {
    document.body.style.setProperty('--pa', opac(numVal('s-pa')));
    document.body.style.setProperty('--ga', opac(numVal('s-ga')));
  };
  ['s-pa', 's-ga'].forEach(id => $$(`[data-ns="${id}"]`).forEach(el => el.addEventListener('input', previewOp)));
  // 위치·크기
  setSeg('s-side', s.layout.side); setSeg('s-hmode', s.layout.height_mode);
  $$('#s-side button').forEach(b => b.onclick = () => setSeg('s-side', b.dataset.v));
  $$('#s-hmode button').forEach(b => b.onclick = () => { setSeg('s-hmode', b.dataset.v); $('#s-h-wrap').hidden = b.dataset.v !== 'custom'; });
  $('#s-layout-apply').onclick = async () => {
    $('#s-layout-msg').textContent = '적용 중…';
    const ok = await api().apply_layout(layoutForm());
    $('#s-layout-msg').textContent = ok ? '적용했어요' : '적용하지 못했어요';
  };
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
  bindHotkeyInput(s.hotkey);
  $('#s-proj-pick').onclick = async () => { const p = await api().pick_folder(); if (p) $('#s-proj').value = p; };
  $('#s-cfg').onclick = () => api().open_config();
  $('#s-log').onclick = () => api().open_log();
  $('#s-save').onclick = async () => { await saveSettingsForm(); $('#s-msg').textContent = '저장했어요'; notify('설정을 저장했어요'); };
}

/* 설정: 단축키 입력 — 단추를 누르고 원하는 조합을 누르면 바로 등록 (Esc 는 취소) */
const KEY_NAMES = {
  Space: 'Space', Backquote: '`', Minus: '-', Equal: '=', BracketLeft: '[', BracketRight: ']', Backslash: '\\',
  Semicolon: ';', Quote: "'", Comma: ',', Period: '.', Slash: '/', Insert: 'Insert', Delete: 'Delete', Home: 'Home',
  End: 'End', PageUp: 'PageUp', PageDown: 'PageDown', ArrowLeft: 'Left', ArrowRight: 'Right', ArrowUp: 'Up', ArrowDown: 'Down',
  Tab: 'Tab', Enter: 'Enter', Backspace: 'Backspace', Pause: 'Pause',
};
function keyName(code) {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3);
  if (/^Digit\d$/.test(code)) return code.slice(5);
  if (/^F\d{1,2}$/.test(code)) return code;
  if (/^Numpad\d$/.test(code)) return 'Num' + code.slice(6);
  return KEY_NAMES[code] || null;
}
function bindHotkeyInput(current) {
  const cap = $('#s-hk'), msg = $('#s-hk-msg'), off = $('#s-hk-off');
  let cur = current || '';
  const show = (spec, text, bad) => {
    cur = spec; cap.textContent = spec || '꺼짐'; cap.classList.remove('rec'); off.hidden = !spec;
    msg.textContent = text; msg.style.color = bad ? 'var(--danger)' : '';
  };
  const stop = () => { S.capturingKey = false; document.removeEventListener('keydown', onKey, true); cap.classList.remove('rec'); };
  const onKey = async e => {
    e.preventDefault(); e.stopPropagation();
    if (['Control', 'Alt', 'Shift', 'Meta', 'HangulMode', 'HanjaMode', 'Process'].includes(e.key)) {
      cap.textContent = [e.ctrlKey && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift', e.metaKey && 'Win'].filter(Boolean).join('+') + '+…';
      return;
    }
    if (e.code === 'Escape' && !e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey) {
      stop(); api().suspend_hotkey(false); show(cur, '취소했어요'); return;
    }
    const k = keyName(e.code);
    if (!k) { msg.textContent = '이 키는 쓸 수 없어요. 다른 키를 눌러 보세요'; msg.style.color = 'var(--danger)'; return; }
    const spec = [e.ctrlKey && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift', e.metaKey && 'Win', k].filter(Boolean).join('+');
    stop();
    const r = await api().set_hotkey(spec);
    if (r.ok) show(r.spec, `${r.spec} 로 바꿨어요`); else show(r.spec, r.error, true);
  };
  cap.onclick = () => {
    if (S.capturingKey) return;
    S.capturingKey = true; cap.classList.add('rec'); cap.textContent = '키를 누르세요…';
    msg.textContent = 'Ctrl / Alt / Shift / Win 과 함께 누르세요 (F 키는 혼자도 돼요) · Esc: 취소'; msg.style.color = '';
    api().suspend_hotkey(true);
    document.addEventListener('keydown', onKey, true);
  };
  cap.onblur = () => { if (S.capturingKey) { stop(); api().suspend_hotkey(false); show(cur, ''); } };
  off.onclick = async () => { const r = await api().set_hotkey(''); show(r.spec, '단축키를 껐어요'); };
}

/* 설정 도우미: 슬라이더 + 숫자 입력 칸 */
const transp = o => Math.round((1 - Number(o)) * 100);               // 불투명도(0~1) → 투명도(%)
const opac = t => Math.round((1 - Math.min(95, Math.max(0, Number(t) || 0)) / 100) * 100) / 100;
function numSlider(id, min, max, step, value, unit) {
  return `<input type="range" data-ns="${id}" id="${id}" min="${min}" max="${max}" step="${step}" value="${value}">
    <input type="number" data-ns="${id}" id="${id}-n" min="${min}" max="${max}" step="${step}" value="${value}" style="width:70px;flex:none"><span class="val">${unit}</span>`;
}
function bindNumSliders() {
  $$('input[type=range][data-ns]').forEach(r => {
    const n = $(`#${r.id}-n`);
    r.addEventListener('input', () => { n.value = r.value; });
    n.addEventListener('input', () => {
      const v = Math.min(Number(n.max), Math.max(Number(n.min), Number(n.value) || 0));
      r.value = v; if (String(v) !== n.value && n.value !== '') n.value = v;
    });
  });
}
const numVal = id => Number($(`#${id}`).value);
function layoutForm() {
  return {
    monitor: Number($('#s-mon').value), side: $('#s-side .on')?.dataset.v || 'left',
    margin_x: numVal('s-mx'), margin_y: numVal('s-my'), scale: numVal('s-scale') / 100,
    panel_width: numVal('s-pw'), height_mode: $('#s-hmode .on')?.dataset.v || 'fit', height: numVal('s-h'),
  };
}

const MENU_NAMES = { game: '게임', live: '라이브', msg: '메신저·커뮤니티', file: '내 파일', dev: '작업 도구', sys: '시스템', web: '웹 바로가기' };
function renderMenuOrder() {
  const list = S.menuDraft;
  $('#s-menu').innerHTML = list.map((m, i) => `<div class="mo${m.show ? '' : ' off'}">
      <span class="nm">${MENU_NAMES[m.key] || m.key}</span>
      <button class="icon-btn" data-mv="${i}" data-d="-1" title="위로"${i === 0 ? ' disabled' : ''}>${glyph('E70E')}</button>
      <button class="icon-btn" data-mv="${i}" data-d="1" title="아래로"${i === list.length - 1 ? ' disabled' : ''}>${glyph('E70D')}</button>
      <button class="switch${m.show ? ' on' : ''}" data-show="${i}" aria-label="메뉴 표시"></button></div>`).join('');
  $$('#s-menu [data-mv]').forEach(b => b.onclick = () => {
    const i = Number(b.dataset.mv), j = i + Number(b.dataset.d);
    [list[i], list[j]] = [list[j], list[i]]; renderMenuOrder(); applyMenu(list);
  });
  $$('#s-menu [data-show]').forEach(b => b.onclick = () => {
    const m = list[Number(b.dataset.show)];
    if (m.show && list.filter(x => x.show).length === 1) { notify('메뉴를 하나는 남겨 두어야 해요'); return; }
    m.show = !m.show; renderMenuOrder(); applyMenu(list);
  });
}

function applyMenu(menu) {
  const box = $('#menu');
  menu.forEach(m => { const el = $(`.mi[data-k="${m.key}"]`, box); if (el) { box.appendChild(el); el.hidden = !m.show; } });
}

/* ---------------- 빠른 버튼 ---------------- */
function renderQuick(buttons) {
  if (!buttons) return;
  const key = JSON.stringify(buttons);
  if (key === S.quickKey) return;          // 바뀐 것이 없으면 다시 그리지 않음 (2초마다 상태 갱신)
  S.quickKey = key;
  $('#quick').innerHTML = buttons.map(b =>
    `<button class="qb${b.on ? ' on' : ''}" data-q="${b.id}" data-confirm="${esc(b.confirm)}" title="${esc(b.name)}">${glyph(b.glyph)}<span>${esc(b.name)}</span></button>`).join('');
}

async function runQuick(btn) {
  const id = btn.dataset.q, name = btn.title;
  if (id === 'empty_bin') { runAction('empty_bin'); return; }
  if (btn.dataset.confirm && !(await confirmBar(btn.dataset.confirm))) return;
  S.busy.quick = true; btn.classList.add('busy');
  try {
    const r = await api().quick_run(id);
    if (id === 'ram' && r) notify(`RAM ${r.freedGB}GB를 확보했어요`);
    else if (id === 'mic' && r) notify(r.on === null ? '마이크를 찾지 못했어요' : r.on ? '마이크를 껐어요' : '마이크를 켰어요');
    else if (id === 'focus' && r) notify(r.on ? '집중 모드: 메신저를 껐어요' : '집중 모드를 끄고 메신저를 다시 켰어요');
    else if (id === 'mute' && r) notify(r.on ? '소리를 껐어요' : '소리를 켰어요');
    else if (id === 'wallpaper' && r) notify(r.on ? '배경을 멈췄어요' : '배경을 다시 재생해요');
    else if (!['lock', 'monitor', 'sleep', 'capture', 'clipboard'].includes(id)) notify(`${name} 실행`);
  } finally {
    btn.classList.remove('busy'); S.busy.quick = false; S.quickKey = null;
    renderQuick(await api().quick_buttons());
  }
}

// Python 쪽에서 HUD 가 보이게/가려지게 될 때 부른다
window.setVisible = visible => {
  const wasHidden = S.hidden;
  S.hidden = !visible;
  if (visible && wasHidden) { tickClock(); pollStatus(); pollMedia(); if (S.menu === 'live') refreshLive(); }
};

// Python 쪽에서 단축키로 HUD 를 맨 앞에 띄우거나 다시 뒤로 보낼 때 부른다
window.setFront = front => {
  S.front = !!front;
  document.body.classList.toggle('front', S.front);
  if (S.front && S.menu === 'live' && $('#q')) $('#q').focus();
};

// Python 쪽에서 창 위치가 바뀔 때 부른다 (붙일 쪽 변경, 끌어서 옮기기 등)
window.setFlip = flip => {
  const app = $('#app');
  if (app.classList.contains('flip') === !!flip) return;
  app.classList.toggle('flip', !!flip);
  const R = $('#right');
  if (!R.hidden) { R.classList.remove('enter'); void R.offsetWidth; R.classList.add('enter'); }
};

function applyFont(f) {
  document.body.dataset.font = (f && f.body) || 'pretendard';
  document.body.dataset.num = (f && f.num) || 'rajdhani';
}
function curFont() {
  return { body: document.body.dataset.font || 'pretendard', num: document.body.dataset.num || 'rajdhani' };
}

function setPlayer(p) {
  S.player = p;
  $('#ytname').textContent = p.id === 'any' ? '음악 앱' : p.name;
  $('#yticon').innerHTML = p.icon ? `<img src="${p.icon}" alt="">` : glyph('E8D6');
  renderMedia();
}

async function saveSettingsForm() {
  const s = S.settings; if (!s || !$('#s-save')) return;
  const theme = document.body.classList.contains('dark') ? 'dark' : 'light';
  const opacity = JSON.parse(JSON.stringify(s.opacity || {}));
  opacity[theme] = { panel: opac(numVal('s-pa')), glass: opac(numVal('s-ga')) };
  const favorites = [0, 1].map(i => ({ id: $(`[data-fav="${i}"]`).value, label: $(`[data-favlabel="${i}"]`).value.trim() || '출력 ' + (i + 1), icon: $(`[data-favicon="${i}"]`).value }));
  await api().save_settings({
    opacity, favorites, keyboard_url: $('#s-kb').value, projects_dir: $('#s-proj').value, mouse_provider: $('#s-mouse').value,
    quick: [0, 1, 2, 3].map(i => $(`[data-qslot="${i}"]`).value),
    menu: S.menuDraft, player: $('#s-player').value, font: curFont(), layout: layoutForm(),
    player_custom: { target: $('#s-custom').value, name: $('#s-custom').selectedOptions[0] ? $('#s-custom').selectedOptions[0].textContent : '' },
  });
  setPlayer(await api().player());
  S.opacity = opacity; S.favs = favorites; renderAudioButtons(); renderQuick(await api().quick_buttons()); pollStatus();
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
  $('#yt').onclick = async () => { if (!(await api().open_player())) notify('설정에서 음악 앱을 골라 주세요'); };

  $('#quick').addEventListener('click', e => { const b = e.target.closest('.qb'); if (b) runQuick(b); });

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
    if (g === 'toast') { const ok = await api().live_test(); notify(ok ? '알림을 보냈어요' : '알림을 띄우지 못했어요'); }
    if (g === 'reload') location.reload();
    if (g === 'quit' && await confirmBar('HUD를 종료할까요?')) api().quit();
  });

  $('#body').addEventListener('click', async e => {
    const t = e.target.closest('[data-hide],[data-webdel],[data-term],[data-game],[data-addgame],[data-link],[data-file],[data-open],[data-drive],[data-proj],[data-tool],[data-act],[data-bell],[data-del],[data-watch],[data-add],[data-gosettings],[data-vdismiss],[data-video],[data-vall],[data-shorts],[data-ythide],[data-golf],[data-rclose],[data-lk],[data-addto],[data-aclose],[data-atab],[data-arow],[data-afile],[data-aweb],[data-grename],[data-gmove],[data-gdel],[data-gfield],[data-wsfolder],[data-detect],[data-sq]');
    if (!t) return;
    const d = t.dataset;
    if (d.detect) { runDetect(d.detect); return; }
    if (d.sq) {
      if (d.sq === 'sleep' && !(await confirmBar('PC를 절전 모드로 바꿀까요?'))) return;
      api().quick_run(d.sq); return;
    }
    if (await handleLinkClick(e, t)) return;
    if (d.hide) { e.stopPropagation(); if (await confirmBar(`'${t.closest('.tile').title}'을(를) 게임 목록에서 숨길까요?`)) { S.games = await api().hide_game(d.hide); $('#gcnt').textContent = S.games.length; renderGames(); } return; }
    if (d.term !== undefined) { e.stopPropagation(); api().open_project(S.ws.projects[d.term].target, true); return; }
    if (d.game) { api().launch_game(d.game); notify(`${t.title} 실행 중…`); }
    else if (d.addgame) { const g = await api().add_game(); if (g) { S.games = g; $('#gcnt').textContent = g.length; renderGames(); notify('게임을 추가했어요'); } }
    else if (d.file !== undefined) api().open(S.fileItems[d.file].target);
    else if (d.open) api().open(d.open);
    else if (d.drive !== undefined) api().open(S.drives[d.drive].target);
    else if (d.proj !== undefined) api().open_project(S.ws.projects[d.proj].target, false);
    else if (d.act) runAction(d.act);
    else if (d.bell) { await api().live_notify(d.p, d.bell, d.on !== '1'); refreshLive(); }
    else if (d.del) { if (await confirmBar('이 채널을 목록에서 뺄까요?')) { await api().live_remove(d.p, d.del); refreshLive(); } }
    else if (d.watch) api().live_open(d.p, d.watch);
    else if (d.add) {
      await api().live_add(d.p, d.add, d.name, d.img); notify(`${d.name} 님을 추가했어요`);
      t.outerHTML = '<span class="label">추가됨</span>';
      refreshLive(); setTimeout(refreshLive, 2500); if (d.p === 'youtube') setTimeout(refreshLive, 8000);
    }
    else if (d.vdismiss) { e.stopPropagation(); await api().video_dismiss([d.vdismiss]); refreshLive(); pollStatus(); }
    else if (d.video) { api().video_open(d.video); setTimeout(() => { refreshLive(); pollStatus(); }, 300); }
    else if (d.vall) { await api().video_dismiss((S.live?.videos || []).map(v => v.id)); notify('새 영상을 모두 읽음으로 표시했어요'); refreshLive(); pollStatus(); }
    else if (d.shorts) { S.live = await api().set_hide_shorts(!t.classList.contains('on')); refreshLive(); pollStatus(); }
    else if (d.ythide) { const on = !t.classList.contains('on'); await api().set_hide_yt_channels(on); notify(on ? "'전체'에서 YouTube 채널을 숨겼어요" : "'전체'에 YouTube 채널도 보여요"); refreshLive(); }
    else if (d.golf) { S.liveFilter = d.golf; refreshLive(); }
    else if (d.rclose) { $('#results').innerHTML = ''; $('#q').value = ''; }
    else if (d.gosettings) openMenu('settings');
  });
  $('#chips').addEventListener('click', async e => {
    const ch = e.target.closest('[data-edit],[data-detect],[data-gadd],[data-wstitle]');
    if (ch) {
      const cd = ch.dataset;
      if (cd.edit) { S.edit = !S.edit; if (S.menu === 'msg') drawMsg(); else if (S.menu === 'web') drawWeb(); else drawWs(); }
      else if (cd.detect) runDetect(cd.detect);
      else if (cd.gadd) showGroupPicker();
      else if (cd.wstitle) { const t = await promptBar('왼쪽 메뉴에 보일 이름 (예: 음악 작업실)', S.ws.title); if (t) { S.ws = await api().ws_set(t, null); drawWs(); } }
      return;
    }
    const lf = e.target.closest('[data-lf]');
    if (lf) { S.liveFilter = lf.dataset.lf; refreshLive(); return; }
    const c = e.target.closest('[data-f]'); if (!c) return;
    S.gameFilter = c.dataset.f; renderGames();
  });
  // 단축키로 맨 앞에 띄운 상태에서 Esc 를 누르면 다시 바탕화면으로
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && S.front && !S.capturingKey) { e.preventDefault(); api().hide_front(); }
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
  tickClock(); setInterval(() => { if (!S.hidden) tickClock(); }, 1000);
  const d = await api().init();
  S.opacity = d.opacity; applyTheme(d.theme, d.opacity); applyFont(d.font);
  S.games = d.games; S.messengers = d.messengers; S.web = d.web; S.favs = d.audioFavs;
  $('#kb').hidden = !d.hasKeyboard;
  if (d.kbIcon) $('#kbicon').innerHTML = `<img src="${d.kbIcon}" alt="">`;
  S.liveIcons = d.liveIcons || {}; S.platforms = d.platforms || {};
  applyMenu(d.menu); setPlayer(d.player); setWsTitle(d.wsTitle);
  $('#gcnt').textContent = S.games.length;
  renderAudioButtons(); setSeg('snd', d.audio); renderQuick(d.quickButtons);
  // 다른 창에 완전히 가려져 있으면(S.hidden) 아무것도 새로 그리지 않는다 — 보이는 순간 바로 갱신
  pollStatus(); setInterval(() => { if (!S.hidden) pollStatus(); }, 2000);
  pollMedia(); setInterval(() => { if (!S.hidden) pollMedia(); }, 1500);
  setInterval(() => { if (!S.hidden && S.media && S.media.playing) tickProgress(); }, 500);
  setInterval(() => { if (!S.hidden && S.menu === 'live') refreshLive(); }, 30000);
  if (d.openPanel) openMenu(d.openPanel);
});
