(function () {
  const CHAT_OPEN_KEY = "erganios.aiChat.open";
  const panel = document.getElementById("aiChatPanel");
  const toggle = document.getElementById("aiChatToggle");
  const close = document.getElementById("aiChatClose");
  const form = document.getElementById("aiChatForm");
  const input = document.getElementById("aiChatInput");
  const messages = document.getElementById("aiChatMessages");
  const storeLabel = document.getElementById("aiChatStore");
  if (!panel || !toggle || !form) return;
  let store = null;

  async function readJsonResponse(res, fallback) {
    const contentType = String(res.headers.get("content-type") || "").toLowerCase();
    if (contentType.includes("application/json")) return res.json();
    const text = await res.text();
    throw new Error(res.ok ? fallback : `${fallback} (HTTP ${res.status})`);
  }

  function setOpen(isOpen) {
    panel.classList.toggle("is-open", isOpen);
    panel.setAttribute("aria-hidden", isOpen ? "false" : "true");
    sessionStorage.setItem(CHAT_OPEN_KEY, isOpen ? "1" : "0");
  }

  function addMessage(row) {
    const el = document.createElement("div");
    el.className = `ai-chat-message ai-chat-message--${row.direction === "in" ? "in" : "out"}`;
    const channel = document.createElement("small");
    channel.className = "ai-chat-channel";
    channel.textContent = row.direction === "out"
      ? "erganiOS"
      : (row.channel === "telegram" ? "Εσείς · Telegram" : "Εσείς");
    el.appendChild(channel);
    el.appendChild(document.createTextNode(row.message_text || ""));
    const timestamp = document.createElement("time");
    timestamp.className = "ai-chat-time";
    const createdAt = new Date();
    timestamp.textContent = row.created_time || createdAt.toLocaleTimeString(
      "el-GR", {hour:"2-digit", minute:"2-digit", hour12:false}
    );
    el.appendChild(timestamp);
    if (row.direction === "out" && row.task_status === "awaiting_ui_confirmation" && row.task_id) {
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "btn btn-sm ai-chat-confirm";
      btn.textContent = "Επιβεβαίωση";
      btn.onclick = () => confirmTask(row.task_id, btn);
      el.appendChild(document.createElement("br")); el.appendChild(btn);
    }
    messages.appendChild(el);
    return el;
  }

  function addLoadingMessage() {
    const el = document.createElement("div");
    el.className = "ai-chat-message ai-chat-message--out ai-chat-message--loading";
    el.innerHTML = '<small class="ai-chat-channel">erganiOS</small><span>Αναλύω την εντολή</span><span class="ai-chat-loading-dots" aria-label="Αναμονή"><i></i><i></i><i></i></span>';
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
    return el;
  }

  async function loadHistory() {
    const active = await Office.fetchActiveStore({ refresh: true });
    store = active?.store || null;
    storeLabel.textContent = store?.name || "Δεν επιλέχθηκε κατάστημα";
    messages.replaceChildren();
    if (!store) { messages.innerHTML = '<p class="ai-chat-empty">Επιλέξτε πρώτα κατάστημα.</p>'; return; }
    const res = await fetch(`/api/assistant/history/${store.id}`);
    const data = await readJsonResponse(res, "Αποτυχία φόρτωσης ιστορικού");
    if (!res.ok) throw new Error(data.error || "Αποτυχία φόρτωσης ιστορικού");
    if (!(data.messages || []).length) messages.innerHTML = '<p class="ai-chat-empty">Ξεκινήστε μια συνομιλία με τον AI Agent.</p>';
    else data.messages.forEach(addMessage);
    messages.scrollTop = messages.scrollHeight;
  }

  async function confirmTask(taskId, btn) {
    btn.disabled = true;
    btn.textContent = "Εκτέλεση…";
    const executing = document.createElement("div");
    executing.className = "ai-chat-message ai-chat-message--out ai-chat-message--loading";
    executing.innerHTML = '<small class="ai-chat-channel">erganiOS</small><span>Εκτέλεση εντολών. Παρακαλώ περιμένετε...</span><span class="ai-chat-loading-dots" aria-label="Αναμονή"><i></i><i></i><i></i></span>';
    messages.appendChild(executing);
    messages.scrollTop = messages.scrollHeight;
    try {
      const res = await fetch(`/api/assistant/task/${taskId}/confirm`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({store_id:store.id})});
      const data = await readJsonResponse(res, "Αποτυχία επιβεβαίωσης");
      if (!res.ok) throw new Error(data.error || "Αποτυχία επιβεβαίωσης");
      await loadHistory();
    } catch (error) {
      executing.remove();
      btn.disabled = false;
      btn.textContent = "Επιβεβαίωση";
      await Office.alert(error.message || "Αποτυχία επιβεβαίωσης", { title: "Σφάλμα επιβεβαίωσης" });
    }
  }

  toggle.onclick = async () => {
    const willOpen = !panel.classList.contains("is-open");
    setOpen(willOpen);
    if (willOpen) {
      try { await loadHistory(); input.focus(); }
      catch(e) { messages.textContent = e.message; }
    }
  };
  close.onclick = () => setOpen(false);
  form.onsubmit = async (event) => {
    event.preventDefault(); const text = input.value.trim(); if (!text || !store) return;
    input.value = ""; input.disabled = true;
    messages.querySelector(".ai-chat-empty")?.remove();
    addMessage({direction:"in",channel:"ui",message_text:text});
    const loadingMessage = addLoadingMessage();
    try {
      const res = await fetch("/api/assistant/message", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({store_id:store.id,text})});
      const data = await readJsonResponse(res, "Αποτυχία αποστολής"); if (!res.ok) throw new Error(data.error || "Αποτυχία αποστολής"); await loadHistory();
    } catch(e) {
      loadingMessage.remove();
      try { await loadHistory(); }
      catch (_) { addMessage({direction:"out",channel:"ui",message_text:e.message}); }
      messages.scrollTop=messages.scrollHeight;
    }
    finally { input.disabled=false; input.focus(); }
  };
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });

  if (sessionStorage.getItem(CHAT_OPEN_KEY) === "1") {
    setOpen(true);
    loadHistory().then(() => input.focus()).catch(e => { messages.textContent = e.message; });
  }
})();
