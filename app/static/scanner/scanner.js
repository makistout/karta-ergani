'use strict';
const $ = id => document.getElementById(id);
let session = null, stream = null, scanning = false, facing = 'environment', action = 'in', preview = null, sending = false;
let recentPage = 0, recentLoading = false;
let serverOnline = null, connectivityCheck = null;
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
async function api(path, body) {
  const response = await fetch('/scanner/api/' + path, {method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-Scanner-Request': '1'}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
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
async function refreshSession() {
  session = await api('session');
  $('login').hidden = true; $('workspace').hidden = false;
  $('menu-toggle').hidden=false; $('sync-top').hidden=false;
  const store=session.stores.find(s=>s.id===session.store_id) || {};
  $('store-name').textContent=store.name || '';
  $('store-afm').textContent='ΑΦΜ: '+(store.employer_afm || '—');
  $('store-branch').textContent='Παράρτημα: ('+(store.branch_aa ?? '—')+') '+(store.branch_description || '');
  $('store-last-card').textContent=store.last_card_at || 'Δεν υπάρχει καταχωρημένη κάρτα';
  $('store-user').textContent='Όνομα χρήστη: '+(store.username || '—');
  await renderPending();
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
async function page(name) {
  closeMenu();
  if (name === 'recent') await unlock();
  $('page-title').textContent=({home:'Αρχική',recent:'Αποστολές',pending:'Εκκρεμείς',settings:'Ρυθμίσεις'})[name];
  document.querySelectorAll('.page').forEach(el => { el.hidden = el.id !== name; });
  document.querySelectorAll('nav button').forEach(el => { el.removeAttribute('aria-current'); if(el.dataset.page === name) el.setAttribute('aria-current','page'); });
  if(name === 'recent') await loadRecent(0);
  if(name === 'pending') await renderPending();
}
function safeTask(fn) { return async event => { try { await fn(event); } catch(error) { message(error.message, true); } }; }
$('login-form').onsubmit = safeTask(async event => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
  try { const form = new FormData(event.target); await api('login',{username:form.get('username'),password:form.get('password')}); event.target.reset(); message(''); await refreshSession(); } finally { button.disabled = false; }
});
function closeMenu() { $('menu-drawer').close(); $('menu-toggle').setAttribute('aria-expanded','false'); }
$('menu-toggle').onclick=()=>{ $('menu-drawer').showModal(); $('menu-toggle').setAttribute('aria-expanded','true'); if(serverOnline) refreshSession().catch(error=>message(error.message,true)); };
$('menu-close').onclick=closeMenu;
$('menu-drawer').addEventListener('close',()=> $('menu-toggle').setAttribute('aria-expanded','false'));
$('menu-drawer').onclick=event=>{if(event.target===$('menu-drawer')) {const rect=$('menu-drawer').getBoundingClientRect();if(event.clientX<rect.left)closeMenu();}};
document.querySelectorAll('nav button[data-page]').forEach(el => el.onclick = safeTask(() => page(el.dataset.page)));
$('logout').onclick = safeTask(async () => { stopCamera(); closeMenu(); await api('logout',{}); $('menu-toggle').hidden=true; $('sync-top').hidden=true; session=null; $('pending-list').replaceChildren(); $('workspace').hidden=true; $('login').hidden=false; message('Αποσυνδεθήκατε.'); });
function stopCamera() { scanning=false; if(stream) stream.getTracks().forEach(track=>track.stop()); stream=null; $('video').srcObject=null; }
async function openCamera(event) {
  if(!session?.store_id) throw new Error('Επιλέξτε πρώτα κατάστημα');
  action=event; preview=null; stopCamera();
  if(!navigator.mediaDevices?.getUserMedia) throw new Error('Η κάμερα απαιτεί HTTPS και υποστηριζόμενο browser.');
  stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:facing},width:{ideal:1280},height:{ideal:720}},audio:false});
  $('video').srcObject=stream; await $('video').play();
  $('scan-title').textContent=event==='in'?'Προσέλευση':'Αποχώρηση';
  if(!$('camera-dialog').open) $('camera-dialog').showModal();
  $('torch').disabled=!stream.getVideoTracks()[0].getCapabilities?.().torch;
  scanning=true; scanFrame();
}
const canvas=document.createElement('canvas'), context=canvas.getContext('2d',{willReadFrequently:true});
async function scanFrame() {
  if(!scanning) return;
  const video=$('video');
  if(video.readyState>=2 && video.videoWidth) {
    canvas.width=640; canvas.height=Math.round(video.videoHeight*640/video.videoWidth);
    context.drawImage(video,0,0,canvas.width,canvas.height);
    const pixels=context.getImageData(0,0,canvas.width,canvas.height);
    const qr=jsQR(pixels.data,pixels.width,pixels.height,{inversionAttempts:'attemptBoth'});
    if(qr?.data) {
      stopCamera(); $('camera-dialog').close();
      try {
        const data=await api('preview',{qr:qr.data,event:action});
        preview={...data,qr:qr.data};
      } catch(error) {
        if(error.status) { message(error.message,true); return; }
        serverOnline=false; network();
        preview={qr:qr.data,event:action,event_at:new Date().toISOString(),name:'Κάρτα εκτός σύνδεσης'};
      }
      $('confirm-name').textContent=preview.name;
      $('confirm-detail').textContent=`${action==='in'?'Προσέλευση':'Αποχώρηση'} · ${new Date(preview.event_at).toLocaleTimeString('el-GR')} ${preview.employee_afm?'· ΑΦΜ '+preview.employee_afm:'· Τα στοιχεία θα ελεγχθούν όταν συνδεθεί η συσκευή.'}`;
      $('confirm-dialog').showModal(); return;
    }
  }
  setTimeout(scanFrame,180);
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
        item.state=data.success?'success':data.uncertain?'uncertain':'failed'; item.note=data.success?`Υποβλήθηκε${data.protocol?' · '+data.protocol:''}`:(data.error||'Δεν επιβεβαιώθηκε η υποβολή');
        if(data.success) { beep(); message(`${item.name}: ${item.note}`); }
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
function syncResult(text) {
  $('sync-result').textContent=text;
  $('sync-time').textContent=new Intl.DateTimeFormat('el-GR',{timeZone:'Europe/Athens',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date());
  if(!$('sync-dialog').open) $('sync-dialog').showModal();
}
async function synchronizePending() {
  closeMenu();
  if(manualSyncRunning) return;
  if(sending) { syncResult('Η αποστολή δηλώσεων βρίσκεται ήδη σε εξέλιξη.'); return; }
  manualSyncRunning=true;
  $('sync-top').disabled=$('sync-menu').disabled=true;
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
    await refreshSession();
  } catch(error) { syncResult(error.message || 'Ο συγχρονισμός δεν ολοκληρώθηκε.'); }
  finally { manualSyncRunning=false; $('sync-top').disabled=$('sync-menu').disabled=false; }
}
$('sync-top').onclick=synchronizePending;
$('sync-menu').onclick=synchronizePending;
async function loadRecent(pageIndex) {
  if(recentLoading) return;
  recentLoading=true; $('recent-prev').disabled=$('recent-next').disabled=true;
  $('recent-list').replaceChildren(textNode('p','Φόρτωση χτυπημάτων…','muted'));
  try {
    const data=await api(`recent?page=${pageIndex}`); recentPage=pageIndex;
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
  } finally { recentLoading=false; }
}
$('recent-prev').onclick=safeTask(()=>loadRecent(Math.max(0,recentPage-1)));
$('recent-next').onclick=safeTask(()=>loadRecent(recentPage+1));
$('pin-form').onsubmit=safeTask(async event=>{event.preventDefault();await api('pin',{pin:$('old-pin').value,new_pin:$('new-pin').value});event.target.reset();await refreshSession();message('Το PIN διαχείρισης ενεργοποιήθηκε για αυτή τη σύνδεση.');});
window.addEventListener('online',()=>checkConnectivity().catch(error=>message(error.message,true)));window.addEventListener('offline',()=>checkConnectivity().catch(error=>message(error.message,true)));
document.addEventListener('visibilitychange',()=>{if(document.hidden){stopCamera();$('camera-dialog').close();$('recent-list').replaceChildren();$('pending-list').replaceChildren();document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!=='home');}else{checkConnectivity().catch(error=>message(error.message,true));}});
network();clock();setInterval(clock,10000);
checkConnectivity().catch(error=>message(error.message,true));
setInterval(()=>{if(!document.hidden)checkConnectivity().catch(error=>message(error.message,true));},30000);
setInterval(()=>sendPending().catch(error=>message(error.message,true)),60000);
if('serviceWorker' in navigator) navigator.serviceWorker.register('/scanner/sw.js',{scope:'/scanner/'}).catch(()=>message('Δεν ενεργοποιήθηκε η λειτουργία εκτός σύνδεσης.',true));
refreshSession().catch(error=>{if(error.status!==401)message(error.message,true);});
