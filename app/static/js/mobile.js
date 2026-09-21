(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  let people = [], selected = new Set(), storeId = null, day = "", action = null, busy = false;
  const message = (text) => { $("message").textContent = text; };
  async function api(url, body) {
    const res = await fetch(url, {credentials: "same-origin", cache: "no-store", ...(body === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    })});
    const data = await res.json().catch(() => ({error: "Μη αναμενόμενη απάντηση server."}));
    if (res.status === 401 && data.login) location.assign("/ui/login?next=/mobile");
    if (data.redirect) location.assign(data.redirect);
    if (!res.ok) throw new Error(data.error || "Αποτυχία αιτήματος");
    return data;
  }
  function controls() {
    $("selected").textContent = `${selected.size} επιλεγμένοι`;
    for (const id of ["open", "close"]) $(id).disabled = busy || !selected.size;
    for (const id of ["store", "refresh", "clear", "logout", "cancel", "search"]) $(id).disabled = busy;
    document.querySelectorAll("[data-minutes], .person").forEach(b => { b.disabled = busy || b.classList.contains("completed"); });
    $("times").hidden = !action;
  }
  function render() {
    people.filter(p => p.completed).forEach(p => selected.delete(p.afm));
    $("roster").replaceChildren();
    const query = $("search").value.toLocaleLowerCase("el").trim();
    const groups = new Map();
    const completed = [], offSchedule = [];
    people.filter(p => `${p.name} ${p.specialty}`.toLocaleLowerCase("el").includes(query)).forEach(p => {
      // Εκτός σημερινού προγράμματος: μόνο με αναζήτηση ή όσο παραμένουν επιλεγμένοι.
      if (p.off_schedule) { if (query || selected.has(p.afm)) offSchedule.push(p); return; }
      if (p.completed) { completed.push(p); return; }
      if (!groups.has(p.specialty)) groups.set(p.specialty, []);
      groups.get(p.specialty).push(p);
    });
    if (offSchedule.length) groups.set("Εκτός σημερινού προγράμματος", offSchedule);
    if (completed.length) groups.set("Ολοκληρωμένη ημέρα", completed.sort((a, b) => a.name.localeCompare(b.name, "el")));
    for (const [specialty, rows] of groups) {
      const section = document.createElement("section"), title = document.createElement("h2"), count = document.createElement("span"), grid = document.createElement("div");
      title.textContent = specialty; count.textContent = String(rows.length); title.append(count); grid.className = "people";
      for (const person of rows) {
        const button = document.createElement("button"), name = document.createElement("strong"), shifts = document.createElement("small");
        button.className = "person"; button.setAttribute("aria-pressed", String(selected.has(person.afm)));
        name.textContent = person.name;
        shifts.append((person.shifts.length
          ? person.shifts.map(s => s.replace(/\s*[–—]\s*/g, " - ")).join(" · ")
          : "Χωρίς ωράριο σήμερα") + " / ");
        const card = document.createElement("span");
        card.className = "punches";
        card.append("Κάρτα: ");
        const clock = () => {
          const icon = document.createElement("span");
          icon.textContent = "◷";
          icon.setAttribute("role", "img");
          icon.setAttribute("aria-label", "Χωρίς χτύπημα");
          icon.title = "Χωρίς χτύπημα";
          return icon;
        };
        const punches = person.punches || [];
        if (!punches.length) card.append(clock());
        punches.forEach((punch, index) => {
          if (index) card.append(" · ");
          card.append(punch.in || clock(), " - ", punch.out || clock());
        });
        shifts.append(card);
        button.append(name, shifts);
        if (person.completed) button.classList.add("completed");
        if (person.off_schedule) button.classList.add("off-schedule");
        button.onclick = () => { if (busy || person.completed) return; selected.has(person.afm) ? selected.delete(person.afm) : selected.add(person.afm); action = null; render(); };
        grid.append(button);
      }
      section.append(title, grid); $("roster").append(section);
    }
    if (!groups.size) $("roster").textContent = query
      ? "Δεν βρέθηκαν αποτελέσματα."
      : "Κανείς με ώρες στο σημερινό πρόγραμμα. Αναζητήστε όνομα για χτύπημα εκτός προγράμματος.";
    controls();
  }
  async function load() {
    selected.clear(); action = null; people = []; storeId = null; render();
    const data = await api("/api/mobile/roster");
    people = data.employees; storeId = data.store.id; day = data.date;
    $("store").value = String(storeId);
    $("date").textContent = new Intl.DateTimeFormat("el-GR", {dateStyle:"full"}).format(new Date(day + "T12:00:00"));
    const scheduled = people.filter(p => !p.off_schedule).length;
    $("total").textContent = `${scheduled} άτομα στο πρόγραμμα · ${people.length - scheduled} με αναζήτηση`;
    $("sync").textContent = data.synced_at ? `Τελευταίος συγχρονισμός προγράμματος: ${data.synced_at}` : "";
    message(""); render();
  }
  async function run(fn) {
    if (busy) return;
    busy = true; controls();
    try { await fn(); } catch (e) { message(e.message); }
    finally { busy = false; controls(); }
  }
  async function submit(minutes) {
    const event = action, ids = [...selected], selectedStore = storeId, selectedDay = day;
    if (!event || !ids.length) return;
    action = null; controls(); $("results").replaceChildren();
    let succeeded = 0;
    for (let index = 0; index < ids.length; index++) {
      const afm = ids[index], person = people.find(p => p.afm === afm);
      message(`Υποβολή ${index + 1}/${ids.length} · ${person.name}…`);
      const result = document.createElement("li");
      try {
        const data = await api("/api/mobile/submit", {employee_afm:afm, store_id:selectedStore, date:selectedDay, event, minutes});
        if (!data.success) throw new Error(data.error || "Η υποβολή δεν ολοκληρώθηκε.");
        selected.delete(afm); succeeded++;
        result.textContent = `${person.name}: ${event === "check_in" ? "Άνοιγμα" : "Κλείσιμο"} — επιτυχία`;
      } catch (e) {
        result.className = "error";
        result.textContent = `${person.name}: ${e.message} Ελέγξτε την κάρτα πριν από νέα προσπάθεια.`;
        // Stop on failure: never automatically retry a potentially accepted punch.
        $("results").append(result); break;
      }
      $("results").append(result);
    }
    message(`${succeeded}/${ids.length} επιτυχημένα χτυπήματα. ${selected.size ? "Τα υπόλοιπα παραμένουν επιλεγμένα." : "Ολοκληρώθηκε."}`);
    try {
      const updated = await api("/api/mobile/roster");
      if (String(updated.store.id) === String(selectedStore) && updated.date === selectedDay) {
        people = updated.employees;
      } else {
        people = []; selected.clear(); storeId = null;
        message("Η ημέρα ή το κατάστημα άλλαξε. Πατήστε Ανανέωση.");
      }
    } catch (e) { message(`Οι υποβολές ελέγχθηκαν. Η ανανέωση χτυπημάτων απέτυχε: ${e.message}`); }
    render();
    $("results").scrollIntoView({block:"center"});
  }
  $("search").oninput = render;
  $("clear").onclick = () => { selected.clear(); action = null; render(); };
  $("cancel").onclick = () => { action = null; controls(); };
  for (const [id, event, label] of [["open","check_in","Άνοιγμα"],["close","check_out","Κλείσιμο"]]) {
    $(id).onclick = () => { action = event; $("actionLabel").textContent = `${label} · ${selected.size} άτομα`; controls(); };
  }
  document.querySelectorAll("[data-minutes]").forEach(b => { b.onclick = () => run(() => submit(Number(b.dataset.minutes))); });
  $("refresh").onclick = () => run(load);
  $("store").onchange = () => run(async () => {
    selected.clear(); people = []; storeId = null; action = null; render();
    if (!$("store").value) return;
    message("Σύνδεση καταστήματος…");
    await api("/api/store/select", {id:Number($("store").value)}); await load();
  });
  $("logout").onclick = () => run(async () => { await api("/api/auth/logout", {}); location.assign("/ui/login?next=/mobile"); });
  run(async () => {
    message("Φόρτωση καταστημάτων…");
    const stores = await api("/api/store/list");
    for (const store of stores) { const option = document.createElement("option"); option.value = store.id; option.textContent = store.name; $("store").append(option); }
    const active = await api("/api/store/active");
    if (active.store) await load();
    else message(stores.length ? "Επιλέξτε κατάστημα για να δείτε το προσωπικό." : "Δεν υπάρχουν διαθέσιμα καταστήματα.");
  });
})();
