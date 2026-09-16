document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("employees");
  setupHireForm();
});

let _hireSpecialtyAc = null;
let _hireSpecialtyAnalAc = null;

function fillSelectOptions(selectEl, items) {
  if (!selectEl) return;
  selectEl.innerHTML = "";
  for (const item of items || []) {
    const opt = document.createElement("option");
    opt.value = String(item.code ?? item.value ?? "");
    opt.textContent = String(item.label ?? item.name ?? opt.value);
    selectEl.appendChild(opt);
  }
}

function greekDateToIso(text) {
  const parts = String(text || "").trim().split("/");
  if (parts.length !== 3) return "";
  return `${parts[2]}-${parts[1].padStart(2, "0")}-${parts[0].padStart(2, "0")}`;
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "");
      const b64 = raw.includes(",") ? raw.split(",", 1)[1] : raw;
      resolve(b64 || "");
    };
    reader.onerror = () => reject(new Error("Αποτυχία ανάγνωσης αρχείου"));
    reader.readAsDataURL(file);
  });
}

async function searchSpecialtyCatalog(q) {
  const res = await fetch(
    `/api/employees/specialty-catalog?q=${encodeURIComponent(q || "")}&limit=40`,
    { cache: "no-store" }
  );
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Αποτυχία καταλόγου ΣΤΕΠ");
  return (data.items || []).map((item) => ({
    value: String(item.value || item.code || ""),
    code: String(item.code || item.value || ""),
    description: String(item.description || ""),
    label: item.label || `${item.value || item.code} — ${item.description || ""}`,
  }));
}

async function setupHireForm() {
  const form = document.getElementById("employeeHireForm");
  const status = document.getElementById("hireStatus");
  const btn = document.getElementById("hireSubmitBtn");
  const desc = document.getElementById("hireDesc");
  if (!form) return;

  Office.attachGreekDateField({
    inputEl: document.getElementById("hireBirthdate"),
    allowEmpty: false,
  });
  const hirePicker = Office.attachGreekDateField({
    inputEl: document.getElementById("hireDate"),
    allowEmpty: false,
  });
  Office.attachGreekDateField({
    inputEl: document.getElementById("hireFixedFrom"),
    allowEmpty: true,
  });
  Office.attachGreekDateField({
    inputEl: document.getElementById("hireFixedTo"),
    allowEmpty: true,
  });
  Office.attachGreekDateField({
    inputEl: document.getElementById("hireTrialTo"),
    allowEmpty: true,
  });

  const acceptanceEl = document.getElementById("hireBasicsAcceptance");
  const fileWrap = document.getElementById("hireFileWrap");
  const fileInput = document.getElementById("hireFile");

  function syncFileVisibility() {
    const needFile = acceptanceEl.value === "0";
    fileWrap?.classList.toggle("hidden", !needFile);
    if (!needFile && fileInput) fileInput.value = "";
  }

  let branchAa = "0";

  try {
    await Office.loadActiveStore();
    const activeRes = await fetch("/api/store/active");
    const activeData = await activeRes.json();
    if (!activeData.store) {
      desc.textContent = "Επιλέξτε ενεργό κατάστημα από Καταστήματα.";
      btn.disabled = true;
      status.textContent = "Δεν υπάρχει ενεργό κατάστημα.";
      return;
    }

    const res = await fetch("/api/employees/hire/draft", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) {
      status.textContent = data.error || "Αποτυχία φόρτωσης φόρμας";
      btn.disabled = true;
      return;
    }

    const draft = data.draft || {};
    branchAa = String(draft.branch_aa || data.store?.branch_aa || "0");
    const storeName = data.store?.name || activeData.store?.name || "";
    desc.textContent =
      `Υποβολή αναγγελίας πρόσληψης (WebE3N) για «${storeName}»` +
      (branchAa !== "" ? ` · παράρτημα ${branchAa}` : "") +
      ".";

    fillSelectOptions(
      acceptanceEl,
      data.basics_acceptance_catalog ||
        draft.basics_acceptance_catalog || [
          { code: "0", label: "Με επισυναπτόμενο αρχείο" },
          { code: "1", label: "Αναμονή αποδοχής εντός myErgani" },
        ]
    );
    acceptanceEl.value = draft.basics_acceptance || "1";
    syncFileVisibility();
    acceptanceEl.addEventListener("change", syncFileVisibility);

    if (draft.hire_date) {
      hirePicker?.setIso(greekDateToIso(draft.hire_date), true);
    }
    document.getElementById("hireSex").value = draft.sex || "0";
    document.getElementById("hireIdType").value = draft.typos_taytothtas || "ΔΑΤ";
    document.getElementById("hireTimeFrom").value = draft.hire_time_from || "09:00";
    document.getElementById("hireTimeTo").value = draft.hire_time_to || "17:00";
    document.getElementById("hireWeeklyHours").value = draft.weekly_hours || "40,0";
    document.getElementById("hireFulltimeHours").value =
      draft.fulltime_contract_weekly_hours || "40,0";
    document.getElementById("hireWeekDays").value = draft.weekly_work_days || "5";
    document.getElementById("hireRegime").value = draft.regime || "0";
    document.getElementById("hireRelation").value = draft.employment_relation || "0";
    document.getElementById("hireCharacterization").value = draft.characterization || "1";
    document.getElementById("hireBreakMinutes").value = draft.break_minutes || "30";
    document.getElementById("hireBreakInWork").value = draft.break_in_work || "1";
    document.getElementById("hireFlexMinutes").value = draft.flex_arrival_minutes || "0";
    document.getElementById("hireDigitalOrg").value =
      draft.working_time_digital_organization || "1";
    document.getElementById("hireWorkingCard").value = draft.working_card || "1";
    document.getElementById("hireTrialPeriod").value = draft.trial_period || "0";

    const specialtyEl = document.getElementById("hireSpecialty");
    const codeEl = document.getElementById("hireSpecialtyCode");
    const stepInput = document.getElementById("hireSpecialtyStepInput");
    function clearHireSpecialtyFields() {
      if (stepInput) stepInput.value = "";
      if (specialtyEl) specialtyEl.value = "";
      if (codeEl) codeEl.value = "";
      stepInput?.removeAttribute("title");
      specialtyEl?.removeAttribute("title");
    }
    if (!Office.createAutocomplete) {
      status.textContent = "Λείπει το autocomplete script";
    } else {
      _hireSpecialtyAc = Office.createAutocomplete({
        inputId: "hireSpecialtyStepInput",
        listId: "hireSpecialtyStepList",
        hiddenId: "hireSpecialtyCode",
        minChars: 1,
        maxItems: 40,
        debounce: 200,
        searchFn: searchSpecialtyCatalog,
        onSelect: (item) => {
          if (specialtyEl && item?.description) specialtyEl.value = String(item.description);
          if (codeEl) codeEl.value = String(item.value || item.code || "");
        },
      });
      _hireSpecialtyAnalAc = Office.createAutocomplete({
        inputId: "hireSpecialty",
        listId: "hireSpecialtyAnalList",
        hiddenId: "hireSpecialtyCode",
        minChars: 1,
        maxItems: 40,
        debounce: 200,
        searchFn: searchSpecialtyCatalog,
        onSelect: (item) => {
          const code = String(item.value || item.code || "");
          const desc = String(item.description || "");
          if (codeEl) codeEl.value = code;
          if (specialtyEl) specialtyEl.value = desc;
          _hireSpecialtyAc?.setValue(code, desc);
        },
      });
      [stepInput, specialtyEl].forEach((el) => {
        if (!el) return;
        el.addEventListener("focus", clearHireSpecialtyFields);
      });
    }
    status.textContent = "";
  } catch (e) {
    status.textContent = String(e);
    btn.disabled = true;
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!window.confirm("Να υποβληθεί η αναγγελία πρόσληψης στο Ergani;")) return;

    const specialtyCode =
      (_hireSpecialtyAc && _hireSpecialtyAc.getValue().code) ||
      document.getElementById("hireSpecialtyCode").value.trim();
    if (!specialtyCode) {
      status.textContent = "Επιλέξτε ειδικότητα από τον κατάλογο ΣΤΕΠ";
      return;
    }

    let fileBase64 = "";
    if (acceptanceEl.value === "0") {
      const file = fileInput?.files?.[0];
      if (!file) {
        status.textContent = "Επιλέξτε PDF αρχείο αποδοχής ουσιωδών όρων";
        return;
      }
      if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") {
        status.textContent = "Το αρχείο πρέπει να είναι PDF";
        return;
      }
      try {
        fileBase64 = await readFileAsBase64(file);
      } catch (e) {
        status.textContent = String(e);
        return;
      }
    }

    let fileSymbash = "";
    const symFile = document.getElementById("hireFileSymbash")?.files?.[0];
    if (symFile) {
      if (!/\.pdf$/i.test(symFile.name) && symFile.type !== "application/pdf") {
        status.textContent = "Η σύμβαση πρέπει να είναι PDF";
        return;
      }
      try {
        fileSymbash = await readFileAsBase64(symFile);
      } catch (e) {
        status.textContent = String(e);
        return;
      }
    }

    btn.disabled = true;
    status.textContent = "Υποβολή…";
    try {
      const res = await fetch("/api/employees/hire/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          branch_aa: branchAa,
          employee_afm: document.getElementById("hireAfm").value.trim(),
          eponymo: document.getElementById("hireEponymo").value.trim(),
          onoma: document.getElementById("hireOnoma").value.trim(),
          onoma_patros: document.getElementById("hireFather").value.trim(),
          onoma_mitros: document.getElementById("hireMother").value.trim(),
          birthdate: document.getElementById("hireBirthdate").value.trim(),
          sex: document.getElementById("hireSex").value,
          amka: document.getElementById("hireAmka").value.trim(),
          amika: document.getElementById("hireAmika").value.trim(),
          typos_taytothtas: document.getElementById("hireIdType").value.trim(),
          ar_taytothtas: document.getElementById("hireIdNo").value.trim(),
          hire_date: document.getElementById("hireDate").value.trim(),
          hire_time_from: document.getElementById("hireTimeFrom").value.trim(),
          hire_time_to: document.getElementById("hireTimeTo").value.trim(),
          specialty: document.getElementById("hireSpecialty").value.trim(),
          specialty_code: specialtyCode,
          salary: document.getElementById("hireSalary").value.trim(),
          hourly_wage: document.getElementById("hireHourly").value.trim(),
          weekly_hours: document.getElementById("hireWeeklyHours").value.trim(),
          fulltime_contract_weekly_hours: document
            .getElementById("hireFulltimeHours")
            .value.trim(),
          weekly_work_days: document.getElementById("hireWeekDays").value,
          regime: document.getElementById("hireRegime").value,
          employment_relation: document.getElementById("hireRelation").value,
          characterization: document.getElementById("hireCharacterization").value,
          fixed_term_from: document.getElementById("hireFixedFrom").value.trim(),
          fixed_term_to: document.getElementById("hireFixedTo").value.trim(),
          break_minutes: document.getElementById("hireBreakMinutes").value.trim(),
          break_in_work: document.getElementById("hireBreakInWork").value,
          flex_arrival_minutes: document.getElementById("hireFlexMinutes").value.trim(),
          working_time_digital_organization: document.getElementById("hireDigitalOrg").value,
          working_card: document.getElementById("hireWorkingCard").value,
          trial_period: document.getElementById("hireTrialPeriod").value,
          trial_date_to: document.getElementById("hireTrialTo").value.trim(),
          basics_acceptance: acceptanceEl.value,
          f_file: fileBase64 || undefined,
          f_file_symbash: fileSymbash || undefined,
          comments: document.getElementById("hireComments").value.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        status.textContent = data.error || "Αποτυχία υποβολής";
        btn.disabled = false;
        return;
      }
      status.textContent = data.message || "Υποβλήθηκε";
      btn.disabled = false;
    } catch (e) {
      status.textContent = String(e);
      btn.disabled = false;
    }
  });
}
