'use strict';
const $ = id => document.getElementById(id);
let session = null, stream = null, scanning = false, facing = 'environment', action = 'in', preview = null, sending = false;
let recentPage = 0, recentLoading = false;
let serverOnline = null, connectivityCheck = null;
let loginUsername = '';
const PREF_STORE_KEY = 'erganios-scanner-preferred-store';
const dbPromise = new Promise((resolve, reject) => {
  const req = indexedDB.open('erganios-scanner', 1);
  req.onupgradeneeded = () => req.result.createObjectStore('outbox', {keyPath: 'request_id'});
  req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
});
async function storage(method, value) {
  const db = await dbPromise;
  return new Promise((resolve, reject) => {
    const tx = db.transaction('outbox', method === 'getAll' ? 'readonly' : 'readwrite');
    const req = tx.objectStore('outbox')[method](value);
    tx.oncomplete = () => resolve(req.result); tx.onerror = () => reject(tx.error);
  });
}
function message(text, error = false) { $('message').textContent = text; $('message').className = error ? 'error' : ''; $('message').hidden = !text; }
function setDryRunBanner(enabled) {
  const banner = $('dry-run-banner');
  if (!banner) return;
  banner.hidden = !enabled;
}
function showDryRunPreview(text) {
  const preview = $('dry-run-preview');
  const dialog = $('dry-run-dialog');
  if (!preview || !dialog) {
    message(text || 'DRY-RUN — δεν στάλθηκε τίποτα στο ΕΡΓΑΝΗ');
    return;
  }
  preview.textContent = text || 'DRY-RUN — δεν στάλθηκε τίποτα στο ΕΡΓΑΝΗ';
  if (!dialog.open) dialog.showModal();
}
function preferenceKey(username) {
  const name = String(username || loginUsername || '').trim().toLowerCase();
  return name ? `${PREF_STORE_KEY}:${name}` : PREF_STORE_KEY;
}
function readPreferredStoreId(username) {
  try {
    const raw = localStorage.getItem(preferenceKey(username));
    if (!raw) return null;
    const value = Number(raw);
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch { return null; }
}
function writePreferredStoreId(storeId, username) {
  try {
    if (storeId == null) localStorage.removeItem(preferenceKey(username));
    else localStorage.setItem(preferenceKey(username), String(storeId));
  } catch {}
}
async function api(path, body, options = {}) {
  const response = await fetch('/scanner/api/' + path, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    cache: options.cache || (body === undefined ? 'no-store' : 'default'),
    headers: {'Content-Type': 'application/json', 'X-Scanner-Request': '1'},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  });
  let data; try { data = await response.json(); } catch { throw new Error('Μη αναμενόμενη απάντηση από τον server'); }
  if (!response.ok) { const error = new Error(data.error || 'Η ενέργεια απέτυχε'); error.data = data; error.status = response.status; throw error; }
  return data;
}
function network() {
  $('network').textContent = serverOnline === null ? 'Έλεγχος…' : serverOnline ? '● Online' : '○ Offline';
  $('network').title = 'Έλεγχος επικοινωνίας με τον server erganiOS κάθε 30 δευτερόλεπτα';
}
async function checkConnectivity() {
  if (!navigator.onLine) { serverOnline=false; network(); await renderPending(); return; }
  if (connectivityCheck) return connectivityCheck;
  connectivityCheck=(async()=>{
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),5000);
    const wasOnline=serverOnline;
    try {
      const nonce=crypto.randomUUID();
      const response=await fetch('/scanner/api/connectivity?nonce='+nonce,{cache:'no-store',credentials:'omit',signal:controller.signal});
      const data=await response.json();
      serverOnline=navigator.onLine && response.ok && data.service==='erganios-scanner' && data.nonce===nonce;
    } catch { serverOnline=false; }
    finally { clearTimeout(timer); network(); }
    await renderPending();
    if(serverOnline && wasOnline!==true) await sendPending();
  })();
  try { await connectivityCheck; } finally { connectivityCheck=null; }
}
function clock() { $('clock').textContent = new Intl.DateTimeFormat('el-GR',{timeZone:'Europe/Athens',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date()); }
function updateStorePanel() {
  const store=session?.stores?.find(s=>s.id===session.store_id) || {};
  const multi=(session?.stores?.length || 0) > 1;
  $('store-name').textContent=store.name || (multi ? 'Επιλέξτε παράρτημα' : '');
  $('store-afm').textContent=store.employer_afm ? 'ΑΦΜ: '+store.employer_afm : '';
  $('store-branch').textContent=store.branch_aa!=null ? 'Παράρτημα: ('+store.branch_aa+') '+(store.branch_description || '') : '';
  $('store-last-card').textContent=session?.last_sync || store.last_card_at || 'Δεν υπάρχει καταχωρημένη κάρτα';
  $('store-user').textContent=store.username ? 'Όνομα χρήστη: '+store.username : '';
  $('store-switch-hint').hidden=!multi;
  $('drawer-store').classList.toggle('switchable', multi);
  $('drawer-store').setAttribute('aria-disabled', multi ? 'false' : 'true');
}
function openBranchPicker({required=false}={}) {
  if (!session?.stores?.length) return;
  const list=$('branch-list');
  list.replaceChildren();
  for (const store of session.stores) {
    const button=document.createElement('button');
    button.type='button';
    button.setAttribute('role','option');
    button.setAttribute('aria-selected', String(store.id===session.store_id));
    button.append(
      textNode('strong', store.name || 'Κατάστημα'),
      textNode('span', `ΑΦΜ ${store.employer_afm || '—'} · Παράρτημα (${store.branch_aa ?? '—'}) ${store.branch_description || ''}`.trim()),
    );
    button.onclick=safeTask(async()=>{
      await api('store',{store_id:store.id});
      writePreferredStoreId(store.id, store.username || loginUsername);
      $('branch-dialog').close();
      await refreshSession({promptBranch:false});
      message(`Ενεργό παράρτημα: (${store.branch_aa ?? '—'}) ${store.branch_description || store.name || ''}`.trim());
    });
    list.append(button);
  }
  if (!$('branch-dialog').open) $('branch-dialog').showModal();
  $('branch-dialog').oncancel = required
    ? (event => { event.preventDefault(); })
    : null;
}
async function refreshSession({promptBranch=true}={}) {
  const previousSync=session?.last_sync;
  session = await api('session');
  if (previousSync) session.last_sync=previousSync;
  if (!loginUsername) {
    const current=session.stores.find(s=>s.id===session.store_id);
    loginUsername = current?.username || '';
  }
  $('login').hidden = true; $('workspace').hidden = false;
  $('menu-toggle').hidden=false;
  setDryRunBanner(Boolean(session.dry_run));
  updateStorePanel();
  await renderPending();
  if (promptBranch && (session.needs_store_selection || (!session.store_id && session.stores.length > 1))) {
    openBranchPicker({required:true});
  }
}
async function unlock() {
  if (!session?.pin_enabled) return;
  $('unlock-pin').value = ''; $('pin-error').textContent = ''; $('unlock-dialog').showModal();
  await new Promise((resolve, reject) => {
    $('unlock-form').onsubmit = async event => { event.preventDefault(); try { await api('pin', {pin: $('unlock-pin').value}); $('unlock-dialog').close(); resolve(); } catch(error) { $('pin-error').textContent = error.message; } };
    $('cancel-unlock').onclick = () => { $('unlock-dialog').close(); reject(new Error('Η πρόσβαση ακυρώθηκε')); };
    $('unlock-dialog').oncancel = () => reject(new Error('Η πρόσβαση ακυρώθηκε'));
  });
}
function showPage(name) {
  $('page-title').textContent=({home:'Αρχική',recent:'Αποστολές',pending:'Εκκρεμείς',settings:'Ρυθμίσεις'})[name];
  document.querySelectorAll('.page').forEach(el => { el.hidden = el.id !== name; });
  document.querySelectorAll('nav button').forEach(el => { el.removeAttribute('aria-current'); if(el.dataset.page === name) el.setAttribute('aria-current','page'); });
}
async function page(name) {
  closeMenu();
  if(!session?.store_id && (session?.stores?.length || 0) > 1) {
    openBranchPicker({required:true});
    throw new Error('Επιλέξτε πρώτα παράρτημα');
  }
  if (name === 'recent') {
    showPage(name);
    showRecentLoading();
    try {
      await unlock();
      await loadRecent(0);
    } catch (error) {
      $('recent').removeAttribute('aria-busy');
      if (!recentLoading) {
        $('recent-list').replaceChildren(textNode('p', error.message || 'Η φόρτωση ακυρώθηκε.', 'muted'));
      }
      throw error;
    }
    return;
  }
  showPage(name);
  if(name === 'pending') await renderPending();
}
function safeTask(fn) { return async event => { try { await fn(event); } catch(error) { message(error.message, true); } }; }
$('login-form').onsubmit = safeTask(async event => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
  try {
    const form = new FormData(event.target);
    loginUsername = String(form.get('username') || '').trim();
    const preferred = readPreferredStoreId(loginUsername);
    await api('login',{
      username:loginUsername,
      password:form.get('password'),
      ...(preferred ? {preferred_store_id: preferred} : {}),
    });
    event.target.reset(); message(''); await refreshSession();
  } finally { button.disabled = false; }
});
function closeMenu() { $('menu-drawer').close(); $('menu-toggle').setAttribute('aria-expanded','false'); }
$('menu-toggle').onclick=()=>{ $('menu-drawer').showModal(); $('menu-toggle').setAttribute('aria-expanded','true'); if(serverOnline) refreshSession({promptBranch:false}).catch(error=>message(error.message,true)); };
$('menu-close').onclick=closeMenu;
$('menu-drawer').addEventListener('close',()=> $('menu-toggle').setAttribute('aria-expanded','false'));
$('menu-drawer').onclick=event=>{if(event.target===$('menu-drawer')) {const rect=$('menu-drawer').getBoundingClientRect();if(event.clientX<rect.left)closeMenu();}};
function onDrawerStoreActivate(event) {
  if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
  event.preventDefault();
  if ((session?.stores?.length || 0) <= 1) return;
  closeMenu();
  openBranchPicker({required:false});
}
$('drawer-store').onclick=onDrawerStoreActivate;
$('drawer-store').onkeydown=onDrawerStoreActivate;
document.querySelectorAll('nav button[data-page]').forEach(el => el.onclick = safeTask(() => page(el.dataset.page)));
$('logout').onclick = safeTask(async () => { stopCamera(); closeMenu(); await api('logout',{}); $('menu-toggle').hidden=true; session=null; loginUsername=''; setDryRunBanner(false); $('pending-list').replaceChildren(); $('workspace').hidden=true; $('login').hidden=false; message('Αποσυνδεθήκατε.'); });
function stopCamera() { scanning=false; if(stream) stream.getTracks().forEach(track=>track.stop()); stream=null; $('video').srcObject=null; }
async function openCamera(event) {
  if(!session?.store_id) {
    if ((session?.stores?.length || 0) > 1) openBranchPicker({required:true});
    throw new Error('Επιλέξτε πρώτα παράρτημα');
  }
  action=event; preview=null; stopCamera();
  if(!navigator.mediaDevices?.getUserMedia) throw new Error('Η κάμερα απαιτεί HTTPS και υποστηριζόμενο browser.');
  stream=await navigator.mediaDevices.getUserMedia({
    video:{
      facingMode:{ideal:facing},
      width:{ideal:1920},
      height:{ideal:1080},
    },
    audio:false,
  });
  $('video').srcObject=stream; await $('video').play();
  $('scan-title').textContent=event==='in'?'Προσέλευση':'Αποχώρηση';
  if(!$('camera-dialog').open) $('camera-dialog').showModal();
  $('torch').disabled=!stream.getVideoTracks()[0].getCapabilities?.().torch;
  scanning=true; scanFrame();
}
const canvas=document.createElement('canvas'), context=canvas.getContext('2d',{willReadFrequently:true});
function decodeQrFromVideo(video) {
  const vw = video.videoWidth, vh = video.videoHeight;
  if (!vw || !vh) return null;
  // Υψηλότερη ανάλυση + εναλλακτικά μεγέθη (tablet συχνά χρειάζεται >640).
  const widths = [];
  for (const maxW of [1280, 960, 640]) {
    const w = Math.min(vw, maxW);
    if (!widths.includes(w)) widths.push(w);
  }
  for (const width of widths) {
    canvas.width = width;
    canvas.height = Math.max(1, Math.round(vh * width / vw));
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    const qr = jsQR(pixels.data, pixels.width, pixels.height, {inversionAttempts: 'attemptBoth'});
    if (qr?.data) return qr.data;
  }
  // Κεντρικό crop ~70% σε 960px — βοηθά σε tablets με παραμόρφωση στις άκρες.
  const cropW = Math.floor(vw * 0.7);
  const cropH = Math.floor(vh * 0.7);
  const sx = Math.floor((vw - cropW) / 2);
  const sy = Math.floor((vh - cropH) / 2);
  const outW = Math.min(960, cropW);
  canvas.width = outW;
  canvas.height = Math.max(1, Math.round(cropH * outW / cropW));
  context.drawImage(video, sx, sy, cropW, cropH, 0, 0, canvas.width, canvas.height);
  const cropPixels = context.getImageData(0, 0, canvas.width, canvas.height);
  const cropQr = jsQR(cropPixels.data, cropPixels.width, cropPixels.height, {inversionAttempts: 'attemptBoth'});
  return cropQr?.data || null;
}
async function scanFrame() {
  if(!scanning) return;
  const video=$('video');
  if(video.readyState>=2 && video.videoWidth) {
    const qrData=decodeQrFromVideo(video);
    if(qrData) {
      stopCamera(); $('camera-dialog').close();
      try {
        const data=await api('preview',{qr:qrData,event:action});
        preview={...data,qr:qrData};
      } catch(error) {
        if(error.status) { message(error.message,true); return; }
        serverOnline=false; network();
        preview={qr:qrData,event:action,event_at:new Date().toISOString(),name:'Κάρτα εκτός σύνδεσης'};
      }
      $('confirm-name').textContent=preview.name;
      $('confirm-detail').textContent=`${action==='in'?'Προσέλευση':'Αποχώρηση'} · ${new Date(preview.event_at).toLocaleTimeString('el-GR')} ${preview.employee_afm?'· ΑΦΜ '+preview.employee_afm:'· Τα στοιχεία θα ελεγχθούν όταν συνδεθεί η συσκευή.'}`;
      $('confirm-dialog').showModal(); return;
    }
  }
  setTimeout(scanFrame,160);
}
$('arrival').onclick=safeTask(()=>openCamera('in')); $('departure').onclick=safeTask(()=>openCamera('out'));
$('close-camera').onclick=()=>{stopCamera();$('camera-dialog').close();}; $('camera-dialog').oncancel=stopCamera;
$('flip').onclick=safeTask(async()=>{facing=facing==='environment'?'user':'environment';await openCamera(action);});
$('torch').onclick=safeTask(async()=>{const track=stream?.getVideoTracks()[0];if(track) await track.applyConstraints({advanced:[{torch:!track.getSettings().torch}]});});
$('cancel-confirm').onclick=()=>{preview=null;$('confirm-dialog').close();};
$('confirm').onclick=safeTask(async()=>{
  if(!preview) return; $('confirm').disabled=true;
  try {
    const item={...preview,request_id:crypto.randomUUID(),store_id:session.store_id,owner:session.owner,state:'pending',note:'Σε αναμονή αποστολής'};
    await storage('put',item); preview=null; $('confirm-dialog').close(); message('Το χτύπημα αποθηκεύτηκε στη συσκευή και αναμένει επιβεβαίωση.'); await sendPending(); await renderPending();
  } finally { $('confirm').disabled=false; }
});
async function outbox() { return (await storage('getAll')).filter(item=>item.store_id===session?.store_id && item.owner===session?.owner); }
function beep() { if(!$('sound').checked) return; try {const C=window.AudioContext||window.webkitAudioContext;const ac=new C();const osc=ac.createOscillator();const gain=ac.createGain();gain.gain.value=.07;osc.frequency.value=880;osc.connect(gain);gain.connect(ac.destination);osc.start();osc.stop(ac.currentTime+.14);osc.onended=()=>ac.close();}catch{} }
async function sendPending() {
  if(sending || !navigator.onLine || serverOnline!==true || !session?.store_id) return;
  sending=true;
  try {
    for(const item of await outbox()) {
      if(!['pending','sending'].includes(item.state)) continue;
      item.state='sending'; await storage('put',item);
      try {
        const data=await api('submit',item);
        item.state=data.success?'success':data.uncertain?'uncertain':'failed';
        if (data.dry_run && data.success) {
          item.note='DRY-RUN · δεν στάλθηκε στο ΕΡΓΑΝΗ';
          item.preview=data.preview || '';
          beep();
          message(`${item.name}: προσομοίωση — δείτε τι θα στελνόταν`);
          showDryRunPreview(data.preview);
        } else {
          item.note=data.success?`Υποβλήθηκε${data.protocol?' · '+data.protocol:''}`:(data.error||'Δεν επιβεβαιώθηκε η υποβολή');
          if(data.success) { beep(); message(`${item.name}: ${item.note}`); }
        }
      } catch(error) {
        if(!error.status) {item.state='sending';item.note='Αναμονή ελέγχου αποτελέσματος με το ίδιο αναγνωριστικό';}
        else { item.state=error.data?.late?'late':error.data?.uncertain?'uncertain':'failed'; item.note=error.message; }
        message(item.note,true);
      }
      await storage('put',item);
    }
  } finally {sending=false;await renderPending();}
}
function textNode(tag,text,className='') {const el=document.createElement(tag);el.textContent=text;el.className=className;return el;}
async function renderPending() {
  const items=(await outbox()).filter(i=>i.state!=='success');$('pending-count').textContent=items.length; $('retry').disabled=!navigator.onLine || serverOnline!==true || sending || !items.some(i=>['pending','sending'].includes(i.state));$('pending-list').replaceChildren();
  for(const item of items.reverse()) {
    const el=document.createElement('article');el.className='event';const info=document.createElement('div');
    info.append(textNode('strong',item.name),textNode('p',`${item.event==='in'?'Προσέλευση':'Αποχώρηση'} · ${new Date(item.event_at).toLocaleString('el-GR')}`),textNode('p',item.note));
    if(item.state==='late') {
      const reason=document.createElement('select');reason.setAttribute('aria-label','Αιτιολογία εκπρόθεσμης υποβολής');
      reason.add(new Option('Επιλέξτε αιτιολογία',''));
      [['001','Ηλεκτροδότηση / τηλεπικοινωνίες'],['002','Συστήματα εργοδότη'],['003','Σύνδεση με ΠΣ ΕΡΓΑΝΗ']].forEach(([value,label])=>reason.add(new Option(label,value)));
      const button=textNode('button','Υποβολή εκπρόθεσμης');
      button.onclick=safeTask(async()=>{if(!reason.value)throw new Error('Επιλέξτε αιτιολογία');item.aitiologia=reason.value;item.state='pending';await storage('put',item);await sendPending();});
      info.append(reason,button);
    }
    el.append(info);$('pending-list').append(el);
  }
  if(!items.length) $('pending-list').append(textNode('p','Δεν υπάρχουν εκκρεμείς αποστολές.','muted'));
}
$('retry').onclick=safeTask(sendPending);
let manualSyncRunning=false;
function syncStamp() {
  return new Intl.DateTimeFormat('el-GR',{timeZone:'Europe/Athens',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date());
}
function syncResult(text) {
  const stamp=syncStamp();
  $('sync-result').textContent=text;
  $('sync-time').textContent=stamp;
  if(session) session.last_sync=stamp;
  $('store-last-card').textContent=stamp;
  if(!$('sync-dialog').open) $('sync-dialog').showModal();
}
async function synchronizePending() {
  closeMenu();
  if(manualSyncRunning) return;
  if(sending) { syncResult('Η αποστολή δηλώσεων βρίσκεται ήδη σε εξέλιξη.'); return; }
  manualSyncRunning=true;
  $('sync-menu').disabled=true;
  try {
    const pending=(await outbox()).filter(item=>item.state!=='success');
    if(!pending.length) { syncResult('Δεν βρέθηκαν δηλώσεις προς υποβολή.'); return; }
    await checkConnectivity();
    if(!serverOnline) { syncResult('Δεν υπάρχει σύνδεση με τον server. Οι εκκρεμείς δηλώσεις παραμένουν αποθηκευμένες στη συσκευή.'); return; }
    await sendPending();
    const remaining=(await outbox()).filter(item=>item.state!=='success');
    const sent=pending.filter(item=>!remaining.some(row=>row.request_id===item.request_id)).length;
    if(!remaining.length) syncResult(`Υποβλήθηκαν επιτυχώς ${sent} δηλώσεις.`);
    else syncResult(`${sent ? `Υποβλήθηκαν ${sent} δηλώσεις. ` : ''}Παραμένουν ${remaining.length} εκκρεμείς δηλώσεις. Ελέγξτε τις «Εκκρεμείς» για αιτιολογία ή έλεγχο αποτελέσματος.`);
    await refreshSession({promptBranch:false});
  } catch(error) { syncResult(error.message || 'Ο συγχρονισμός δεν ολοκληρώθηκε.'); }
  finally { manualSyncRunning=false; $('sync-menu').disabled=false; }
}
$('sync-menu').onclick=synchronizePending;
async function loadRecent(pageIndex) {
  if(recentLoading) return;
  recentLoading=true;
  showRecentLoading();
  try {
    const data=await api(`recent?page=${pageIndex}&limit=20&_=${Date.now()}`, undefined, {cache:'no-store'});
    recentPage=pageIndex;
    $('recent-list').replaceChildren();
    for(const row of data.events) {
      const el=document.createElement('article');el.className='event';
      const info=document.createElement('div'),right=document.createElement('div');right.className='right';
      info.append(textNode('p',row.event==='in'?'Προσέλευση':'Αποχώρηση','kind'),textNode('strong',row.name),textNode('p','ΑΦΜ '+row.employee_afm,'muted'));
      if(row.protocol) info.append(textNode('p','Πρωτόκολλο '+row.protocol,'small'));
      right.append(textNode('p',row.date),textNode('p',row.time,'time'));
      if(row.next_day) right.append(textNode('p','Επόμενη ημέρα','small'));
      el.append(info,right);$('recent-list').append(el);
    }
    if(!data.events.length) $('recent-list').append(textNode('p','Δεν υπάρχουν καταγεγραμμένα χτυπήματα.','muted'));
    $('recent-prev').disabled=!data.has_previous; $('recent-next').disabled=!data.has_next;
  } catch(error) {
    $('recent-list').replaceChildren(textNode('p','Δεν ήταν δυνατή η φόρτωση των χτυπημάτων.','muted'));
    throw error;
  } finally {
    recentLoading=false;
    $('recent').removeAttribute('aria-busy');
  }
}
function showRecentLoading() {
  $('recent').setAttribute('aria-busy','true');
  $('recent-prev').disabled=true;
  $('recent-next').disabled=true;
  const state=document.createElement('div');
  state.className='loading-state';
  state.setAttribute('role','status');
  const spinner=document.createElement('div');
  spinner.className='spinner';
  spinner.setAttribute('aria-hidden','true');
  state.append(spinner, textNode('p','Φόρτωση από τη βάση…'));
  $('recent-list').replaceChildren(state);
}
$('recent-prev').onclick=safeTask(()=>loadRecent(Math.max(0,recentPage-1)));
$('recent-next').onclick=safeTask(()=>loadRecent(recentPage+1));
$('pin-form').onsubmit=safeTask(async event=>{event.preventDefault();await api('pin',{pin:$('old-pin').value,new_pin:$('new-pin').value});event.target.reset();await refreshSession({promptBranch:false});message('Το PIN διαχείρισης ενεργοποιήθηκε για αυτή τη σύνδεση.');});
window.addEventListener('online',()=>checkConnectivity().catch(error=>message(error.message,true)));window.addEventListener('offline',()=>checkConnectivity().catch(error=>message(error.message,true)));
document.addEventListener('visibilitychange',()=>{if(document.hidden){stopCamera();closeMenu();$('camera-dialog').close();$('recent-list').replaceChildren();$('pending-list').replaceChildren();showPage('home');}else{checkConnectivity().catch(error=>message(error.message,true));}});
network();clock();setInterval(clock,10000);
checkConnectivity().catch(error=>message(error.message,true));
setInterval(()=>{if(!document.hidden)checkConnectivity().catch(error=>message(error.message,true));},30000);
setInterval(()=>{if(!document.hidden)sendPending().catch(error=>message(error.message,true));},30000);
if('serviceWorker' in navigator) navigator.serviceWorker.register('/scanner/sw.js',{scope:'/scanner/'}).catch(()=>message('Δεν ενεργοποιήθηκε η λειτουργία εκτός σύνδεσης.',true));
refreshSession().catch(error=>{if(error.status!==401)message(error.message,true);});
