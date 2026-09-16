document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("employees");
  loadEmployeeDetail();
});

const CONTRACT_FIELDS = [
  ["employer_afm", "ΑΦΜ εργοδότη"],
  ["branch_aa", "Παράρτημα"],
  ["employee_afm", "ΑΦΜ εργαζομένου"],
  ["eponymo", "Επώνυμο"],
  ["onoma", "Όνομα"],
  ["specialty", "Ειδικότητα"],
  ["characterization", "Χαρακτηρισμός"],
  ["step92", "ΣΤΕΠ 92"],
  ["weekly_work_days", "Ημέρες εβδομαδιαίας απασχόλησης"],
  ["prior_service", "Προϋπηρεσία"],
  ["employment_relation", "Σχέση απασχόλησης"],
  ["fixed_term_from", "Ορισμένου χρόνου από"],
  ["fixed_term_to", "Ορισμένου χρόνου έως"],
  ["regime", "Καθεστώς"],
  ["weekly_hours", "Ώρες εβδομαδιαίως"],
  ["salary", "Αποδοχές"],
  ["hourly_wage", "Ωρομίσθιο"],
  ["total_weekly_hours", "Συνολικές ώρες εβδομαδιαίως"],
  ["fulltime_contract_weekly_hours", "Συμβατικές ώρες πλήρους απασχόλησης"],
  ["break_minutes", "Διάλειμμα (λεπτά)"],
  ["break_in_work", "Διάλειμμα εντός ωραρίου"],
  ["flex_arrival_minutes", "Ευέλικτη προσέλευση (λεπτά)"],
  ["ergani_updated_at", "Ημ/νία τελευταίας ενημέρωσης Ergani"],
  ["last_checked_at", "Τελευταίος επιτυχής έλεγχος"],
  ["synced_at", "Αποθήκευση έκδοσης"],
  ["source", "Πηγή"],
];

let _eccDraft = null;
let _eccSpecialtyAc = null;
let _eccSpecialtyAnalAc = null;

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

function resolveSpecialtyFromCatalog(items, codeOrText, specialtyText) {
  const code = String(codeOrText || "").trim();
  const specialty = String(specialtyText || "").trim();
  if (code && /^\d{1,6}$/.test(code)) {
    const byCode = items.find((x) => String(x.value || x.code || "") === code);
    if (byCode) return byCode;
  }
  const needle = (specialty || code).toLowerCase();
  if (!needle) return null;
  return (
    items.find((x) => String(x.description || "").toLowerCase() === needle) ||
    items.find((x) => String(x.description || "").toLowerCase().includes(needle)) ||
    null
  );
}

function applySpecialtySelection(item, { stepAc, analAc, codeEl, specialtyEl }) {
  if (!item) return;
  const code = String(item.value || item.code || "");
  const desc = String(item.description || "");
  if (codeEl) codeEl.value = code;
  if (specialtyEl) specialtyEl.value = desc;
  stepAc?.setValue(code, desc);
}

function attachLinkedSpecialtyAutocompletes({
  stepInputId,
  stepListId,
  codeHiddenId,
  analInputId,
  analListId,
}) {
  const codeEl = document.getElementById(codeHiddenId);
  const specialtyEl = document.getElementById(analInputId);
  const stepInput = document.getElementById(stepInputId);
  if (!Office.createAutocomplete) {
    console.error("Office.createAutocomplete λείπει — δεν φορτώθηκε office-autocomplete.js");
    return { stepAc: null, analAc: null };
  }

  function clearSpecialtyFields() {
    if (stepInput) stepInput.value = "";
    if (specialtyEl) specialtyEl.value = "";
    if (codeEl) codeEl.value = "";
    stepInput?.removeAttribute("title");
    specialtyEl?.removeAttribute("title");
  }

  const stepAc = Office.createAutocomplete({
    inputId: stepInputId,
    listId: stepListId,
    hiddenId: codeHiddenId,
    minChars: 1,
    maxItems: 40,
    debounce: 200,
    searchFn: searchSpecialtyCatalog,
    onSelect: (item) => {
      if (specialtyEl && item?.description) specialtyEl.value = String(item.description);
      if (codeEl) codeEl.value = String(item.value || item.code || "");
    },
  });

  const analAc = Office.createAutocomplete({
    inputId: analInputId,
    listId: analListId,
    hiddenId: codeHiddenId,
    minChars: 1,
    maxItems: 40,
    debounce: 200,
    searchFn: searchSpecialtyCatalog,
    onSelect: (item) => {
      const code = String(item.value || item.code || "");
      const desc = String(item.description || "");
      if (codeEl) codeEl.value = code;
      if (specialtyEl) specialtyEl.value = desc;
      stepAc?.setValue(code, desc);
    },
  });

  // Στο κλικ/focus αδειάζουν και τα δύο για καθαρή αναζήτηση.
  [stepInput, specialtyEl].forEach((el) => {
    if (!el) return;
    el.addEventListener("focus", () => {
      clearSpecialtyFields();
    });
  });

  return { stepAc, analAc, clearSpecialtyFields };
}

function displayValue(key, value) {
  if (value == null || value === "") return "—";
  if (key === "break_in_work") {
    if (value === 1 || value === true || value === "1") return "Ναι";
    if (value === 0 || value === false || value === "0") return "Όχι";
  }
  if (key === "flex_arrival_minutes" && Office.formatFlexMinutes) {
    return Office.formatFlexMinutes(value);
  }
  if (key === "synced_at" || key === "last_checked_at") {
    return String(value).replace("T", " ").slice(0, 19);
  }
  return String(value);
}

function renderContractFieldsTable(row) {
  const t = document.createElement("table");
  t.className = "data employee-contract-fields-table";
  const hr = document.createElement("tr");
  ["Πεδίο", "Τιμή"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);
  CONTRACT_FIELDS.forEach(([key, label]) => {
    const tr = document.createElement("tr");
    const tdLabel = document.createElement("td");
    tdLabel.className = "employee-contract-field-label";
    tdLabel.textContent = label;
    const tdVal = document.createElement("td");
    tdVal.textContent = displayValue(key, row?.[key]);
    tr.appendChild(tdLabel);
    tr.appendChild(tdVal);
    t.appendChild(tr);
  });
  return t;
}

function fillSelectOptions(select, rows) {
  if (!select) return;
  select.innerHTML = "";
  (rows || []).forEach((row) => {
    const opt = document.createElement("option");
    const code = String(row.code ?? row.value ?? "");
    const label = String(row.label ?? row.description ?? "");
    opt.value = code;
    opt.textContent = code && label ? `${code} — ${label}` : label || code;
    select.appendChild(opt);
  });
}

/** Κωδικός καταλόγου από «001» ή «001-ετικέτα» Ergani. */
function insuranceCatalogCode(raw, fallback = "001") {
  const m = String(raw || "").trim().match(/^(\d{1,10})/);
  if (!m || m[1] === "0") return fallback;
  const digits = m[1];
  return digits.length <= 3 ? digits.padStart(3, "0") : digits;
}

function fillInsuranceSelect(select, rows, rawValue, fallback = "001") {
  if (!select) return;
  const list =
    Array.isArray(rows) && rows.length
      ? rows
      : [{ code: fallback, label: fallback }];
  fillSelectOptions(select, list);
  const code = insuranceCatalogCode(rawValue, fallback);
  select.value = code;
  if (select.value !== code) {
    const opt = Array.from(select.options).find(
      (o) => insuranceCatalogCode(o.value, "") === code
    );
    if (opt) select.value = opt.value;
    else if (select.options.length) select.selectedIndex = 0;
  }
}

function guessRegimeCode(text) {
  const t = String(text || "").toUpperCase();
  if (t.includes("ΠΛΗΡ")) return "0";
  if (t.includes("ΜΕΡΙΚ")) return "1";
  if (t.includes("ΠΕΡΙΤΡΟΠ") || t.includes("ΕΚ ΠΕΡ")) return "2";
  return "";
}

function guessRelationCode(text) {
  const t = String(text || "").toUpperCase();
  if (t.includes("ΔΑΝΕΙ")) return "3";
  if (t.includes("ΟΡΙΣΜΕΝ")) return "1";
  if (t.includes("ΑΟΡΙΣΤ")) return "0";
  return "";
}

function guessWeekDays(text) {
  const t = String(text || "");
  if (t.includes("6")) return "6";
  if (t.includes("5")) return "5";
  return "";
}

async function setupContractChange(afm) {
  const form = document.getElementById("employeeContractChangeForm");
  const btn = document.getElementById("eccSubmitBtn");
  if (!form) return;

  const msg = (text, ok) => Office.showMsg("eccMsg", text, ok);

  const dateInput = document.getElementById("eccChangeDate");
  const datePicker = Office.attachGreekDateField({ inputEl: dateInput, allowEmpty: false });
  const birthInput = document.getElementById("eccBirthdate");
  const birthPicker = Office.attachGreekDateField({ inputEl: birthInput, allowEmpty: true });
  const fixedFromInput = document.getElementById("eccFixedFrom");
  const fixedToInput = document.getElementById("eccFixedTo");
  const fixedFromPicker = Office.attachGreekDateField({
    inputEl: fixedFromInput,
    allowEmpty: true,
  });
  const fixedToPicker = Office.attachGreekDateField({
    inputEl: fixedToInput,
    allowEmpty: true,
  });
  const typesEl = document.getElementById("eccChangeTypes");
  const acceptanceEl = document.getElementById("eccBasicsAcceptance");
  const fileWrap = document.getElementById("eccFileWrap");
  const fileInput = document.getElementById("eccFile");
  const relationEl = document.getElementById("eccRelation");
  const fixedTermWrap = document.getElementById("eccFixedTermWrap");

  function syncFileVisibility() {
    const needFile = acceptanceEl.value === "0";
    fileWrap?.classList.toggle("hidden", !needFile);
    if (!needFile && fileInput) fileInput.value = "";
  }

  function syncFixedTermVisibility() {
    const needDates = relationEl?.value === "1";
    fixedTermWrap?.classList.toggle("hidden", !needDates);
    if (!needDates) {
      if (fixedFromInput) fixedFromInput.value = "";
      if (fixedToInput) fixedToInput.value = "";
    }
  }

  function setGreekDate(picker, value) {
    if (!picker || !value) return;
    const text = String(value).trim();
    if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
      picker.setIso(text.slice(0, 10), true);
      return;
    }
    const parts = text.split("/");
    if (parts.length === 3) {
      picker.setIso(
        `${parts[2]}-${parts[1].padStart(2, "0")}-${parts[0].padStart(2, "0")}`,
        true
      );
    }
  }

  try {
    const res = await fetch(
      `/api/employees/contract/change/draft?employee_afm=${encodeURIComponent(afm)}`,
      { cache: "no-store" }
    );
    const data = await res.json();
    if (!res.ok) {
      msg(data.error || "Αποτυχία φόρτωσης φόρμας", false);
      btn.disabled = true;
      return;
    }
    const draft = data.draft || {};
    _eccDraft = draft;
    fillSelectOptions(typesEl, data.change_types || draft.change_types_catalog || []);
    fillSelectOptions(
      acceptanceEl,
      draft.basics_acceptance_catalog || [
        { code: "0", label: "Με επισυναπτόμενο αρχείο" },
        { code: "1", label: "Αναμονή αποδοχής εντός myErgani" },
        { code: "2", label: "Δεν απαιτείται" },
      ]
    );
    acceptanceEl.value = draft.basics_acceptance || "1";
    syncFileVisibility();
    acceptanceEl.addEventListener("change", syncFileVisibility);
    setGreekDate(datePicker, draft.change_date);
    setGreekDate(birthPicker, draft.birthdate);
    document.getElementById("eccEponymo").value = draft.eponymo || "";
    document.getElementById("eccOnoma").value = draft.onoma || "";
    document.getElementById("eccFather").value = draft.onoma_patros || "";
    document.getElementById("eccMother").value = draft.onoma_mitros || "";
    document.getElementById("eccSex").value = draft.sex || "";
    const idTypes =
      data.identity_document_types ||
      draft.identity_document_types || [
        { code: "ΔAT", label: "ΔΕΛΤΙΟ ΑΣΤΥΝΟΜΙΚΗΣ ΤΑΥΤΟΤΗΤΑΣ" },
        { code: "ΔΙΑ", label: "ΔΙΑΒΑΤΗΡΙΟ" },
      ];
    fillSelectOptions(document.getElementById("eccIdType"), idTypes);
    document.getElementById("eccIdType").value = draft.typos_taytothtas || "ΔAT";
    document.getElementById("eccIdNo").value = draft.ar_taytothtas || "";
    document.getElementById("eccAmka").value = draft.amka || "";
    document.getElementById("eccAmika").value = draft.amika || "";
    const kyriaFunds =
      data.main_insurance_funds ||
      draft.main_insurance_funds || [
        { code: "001", label: "e-ΕΦΚΑ" },
        { code: "002", label: "e-ΕΦΚΑ – ΝΑΤ" },
        { code: "003", label: "Τράπεζα της Ελλάδος" },
      ];
    fillInsuranceSelect(
      document.getElementById("eccKyriaAsfalish"),
      kyriaFunds,
      draft.kyria_asfalish,
      "001"
    );
    const epikFunds =
      data.supplementary_insurance_funds ||
      draft.supplementary_insurance_funds || [
        { code: "001", label: "Κλάδος επικουρικής e-ΕΦΚΑ" },
        { code: "002", label: "ΤΕΚΑ" },
      ];
    fillInsuranceSelect(
      document.getElementById("eccEpikourikiki"),
      epikFunds,
      draft.epikourikiki_kod,
      "001"
    );
    document.getElementById("eccXronosKatabolhs").value =
      draft.xronos_katabolhs || "Μηνιαίως";
    const dieutTypes =
      data.dieuthetisi_types ||
      draft.dieuthetisi_types || [
        { code: "2", label: "Όχι" },
        { code: "0", label: "Ναι — συλλογική συμφωνία" },
        { code: "1", label: "Ναι — ατομική συμφωνία" },
      ];
    fillSelectOptions(document.getElementById("eccDieuthetisi"), dieutTypes);
    document.getElementById("eccDieuthetisi").value =
      draft.eidos_dieuthethshs || "2";
    document.getElementById("eccSpecialty").value = draft.specialty || "";
    document.getElementById("eccSalary").value = draft.salary || "";
    document.getElementById("eccHourly").value = draft.hourly_wage || "";
    document.getElementById("eccWeeklyHours").value =
      draft.weekly_hours || draft.total_weekly_hours || "";
    document.getElementById("eccFulltimeHours").value =
      draft.fulltime_contract_weekly_hours || "";
    document.getElementById("eccWeekDays").value =
      guessWeekDays(draft.weekly_work_days) || String(draft.weekly_work_days || "");
    document.getElementById("eccRegime").value =
      guessRegimeCode(draft.regime) || String(draft.regime || "");
    document.getElementById("eccRelation").value =
      guessRelationCode(draft.employment_relation) ||
      String(draft.employment_relation || "");
    setGreekDate(fixedFromPicker, draft.fixed_term_from);
    setGreekDate(fixedToPicker, draft.fixed_term_to);
    document.getElementById("eccDigitalOrg").value =
      String(draft.working_time_digital_organization ?? "1");
    document.getElementById("eccWorkingCard").value = String(draft.working_card ?? "1");
    document.getElementById("eccComments").value = "";
    syncFixedTermVisibility();
    relationEl?.addEventListener("change", syncFixedTermVisibility);

    function syncDigitalFlagsFromChangeTypes() {
      const selected = Array.from(typesEl.selectedOptions).map((o) => o.value);
      if (selected.includes("011") || selected.includes("013")) {
        document.getElementById("eccDigitalOrg").value = "1";
        document.getElementById("eccWorkingCard").value = "1";
      }
      // Μετατροπή ορισμένου → αορίστου
      if (selected.includes("006")) {
        relationEl.value = "0";
        syncFixedTermVisibility();
      }
    }
    typesEl.addEventListener("change", syncDigitalFlagsFromChangeTypes);
    syncDigitalFlagsFromChangeTypes();

    try {
      const linked = attachLinkedSpecialtyAutocompletes({
        stepInputId: "eccSpecialtyStepInput",
        stepListId: "eccSpecialtyStepList",
        codeHiddenId: "eccSpecialtyCode",
        analInputId: "eccSpecialty",
        analListId: "eccSpecialtyAnalList",
      });
      _eccSpecialtyAc = linked.stepAc;
      _eccSpecialtyAnalAc = linked.analAc;
      const seedQ = String(draft.specialty_code || draft.specialty || draft.step92 || "").trim();
      let matched = null;
      if (seedQ) {
        const items = await searchSpecialtyCatalog(seedQ);
        matched = resolveSpecialtyFromCatalog(
          items,
          draft.specialty_code || draft.step92,
          draft.specialty
        );
      }
      if (matched) {
        _eccSpecialtyAc?.setValue(matched.value || matched.code, matched.description);
        document.getElementById("eccSpecialty").value =
          draft.specialty || matched.description || "";
        document.getElementById("eccSpecialtyCode").value = matched.value || matched.code || "";
      } else if (draft.specialty_code || draft.step92) {
        const code = String(draft.specialty_code || "").replace(/\D/g, "") || "";
        if (code) {
          _eccSpecialtyAc?.setValue(code, draft.specialty || draft.step92 || code);
          document.getElementById("eccSpecialtyCode").value = code;
        } else if (draft.step92) {
          document.getElementById("eccSpecialtyStepInput").value = draft.step92;
        }
        if (draft.specialty) document.getElementById("eccSpecialty").value = draft.specialty;
      }
    } catch (e) {
      msg(`Κατάλογος ΣΤΕΠ: ${e}`, false);
    }

    if (data.ergani_enriched) {
      msg("Προσυμπληρώθηκε από τρέχουσα κατάσταση Ergani (EX_BASE_05).", true);
    } else if (data.ergani_enrich_error) {
      msg(
        `Δεν φορτώθηκαν στοιχεία από Ergani: ${data.ergani_enrich_error}. Συμπληρώστε χειροκίνητα ή ξαναφορτώστε τη σελίδα.`,
        false
      );
    } else {
      msg(
        "Δεν φορτώθηκαν στοιχεία από Ergani (EX_BASE_05). Συμπληρώστε χειροκίνητα ή ξαναφορτώστε τη σελίδα.",
        false
      );
    }
  } catch (e) {
    msg(String(e), false);
    btn.disabled = true;
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selectedTypes = Array.from(typesEl.selectedOptions)
      .map((o) => o.value)
      .filter(Boolean);
    if (!selectedTypes.length) {
      msg("Επιλέξτε τουλάχιστον έναν τύπο μεταβολής", false);
      return;
    }
    const changeDate = dateInput.value.trim();
    if (!changeDate) {
      msg("Συμπληρώστε ημερομηνία μεταβολής", false);
      return;
    }
    const eponymo = document.getElementById("eccEponymo").value.trim();
    const onoma = document.getElementById("eccOnoma").value.trim();
    const father = document.getElementById("eccFather").value.trim();
    const mother = document.getElementById("eccMother").value.trim();
    const birthdate = birthInput.value.trim();
    const sex = document.getElementById("eccSex").value;
    const idType = document.getElementById("eccIdType").value.trim();
    const idNo = document.getElementById("eccIdNo").value.trim();
    const amka = document.getElementById("eccAmka").value.trim().replace(/\D/g, "");
    const amika = document.getElementById("eccAmika").value.trim().replace(/\D/g, "");
    if (!eponymo || !onoma || !father || !mother || !birthdate || !sex || !idType || !idNo) {
      msg(
        "Συμπληρώστε τα στοιχεία ταυτότητας (ον/μο, πατρός/μητρός, γέννηση, φύλο, ταυτότητα)",
        false
      );
      return;
    }
    if (!amka || amka.length < 11) {
      msg("Συμπληρώστε έγκυρο ΑΜΚΑ εργαζομένου (11 ψηφία)", false);
      return;
    }
    const salary = document.getElementById("eccSalary").value.trim();
    const weeklyHours = document.getElementById("eccWeeklyHours").value.trim();
    if (!salary || !weeklyHours) {
      msg("Συμπληρώστε αποδοχές και ώρες εβδομαδιαίως", false);
      return;
    }
    const specialtyCode =
      (_eccSpecialtyAc && _eccSpecialtyAc.getValue().code) ||
      document.getElementById("eccSpecialtyCode").value.trim();
    if (!specialtyCode) {
      msg("Επιλέξτε ειδικότητα από τον κατάλογο ΣΤΕΠ", false);
      return;
    }
    const relation = document.getElementById("eccRelation").value;
    const fixedFrom = fixedFromInput?.value.trim() || "";
    const fixedTo = fixedToInput?.value.trim() || "";
    if (relation === "1" && (!fixedFrom || !fixedTo)) {
      msg("Για ορισμένου χρόνου συμπληρώστε ημερομηνίες από / έως", false);
      return;
    }

    let uploadFile = null;
    if (acceptanceEl.value === "0") {
      uploadFile = fileInput?.files?.[0] || null;
      if (!uploadFile) {
        msg("Επιλέξτε PDF αρχείο αποδοχής ουσιωδών όρων", false);
        return;
      }
      if (!/\.pdf$/i.test(uploadFile.name) && uploadFile.type !== "application/pdf") {
        msg("Το αρχείο πρέπει να είναι PDF", false);
        return;
      }
      if (uploadFile.size < 32) {
        msg("Το PDF φαίνεται κενό — επιλέξτε ξανά το αρχείο", false);
        return;
      }
    }

    const ok = await Office.confirm("Να υποβληθεί η μεταβολή σύμβασης στο Ergani;", {
      title: "Υποβολή μεταβολής σύμβασης",
      confirmText: "Υποβολή",
    });
    if (!ok) return;

    btn.disabled = true;
    Office.showLoading("eccMsg", "Υποβολή μεταβολής σύμβασης στο Ergani…");
    try {
      const payload = {
        employee_afm: afm,
        eponymo,
        onoma,
        onoma_patros: father,
        onoma_mitros: mother,
        birthdate,
        sex,
        typos_taytothtas: idType,
        ar_taytothtas: idNo,
        amka,
        amika,
        kyria_asfalish: insuranceCatalogCode(
          document.getElementById("eccKyriaAsfalish")?.value,
          "001"
        ),
        epikourikiki_kod: insuranceCatalogCode(
          document.getElementById("eccEpikourikiki")?.value,
          "001"
        ),
        characterization: (_eccDraft && _eccDraft.characterization) || "",
        xronos_katabolhs:
          document.getElementById("eccXronosKatabolhs")?.value.trim() ||
          (_eccDraft && _eccDraft.xronos_katabolhs) ||
          "Μηνιαίως",
        eidos_dieuthethshs: document.getElementById("eccDieuthetisi")?.value || "2",
        prior_service: (_eccDraft && _eccDraft.prior_service) || "0",
        break_minutes: (_eccDraft && _eccDraft.break_minutes) || "0",
        break_in_work: (_eccDraft && _eccDraft.break_in_work) || "0",
        flex_arrival_minutes: (_eccDraft && _eccDraft.flex_arrival_minutes) || "0",
        working_card: document.getElementById("eccWorkingCard")?.value || "1",
        working_time_digital_organization:
          document.getElementById("eccDigitalOrg")?.value || "1",
        yphkoothta: (_eccDraft && _eccDraft.yphkoothta) || "025",
        marital_status: (_eccDraft && _eccDraft.marital_status) || "0",
        arithmos_teknon: (_eccDraft && _eccDraft.arithmos_teknon) || "0",
        epipedo_morfosis: (_eccDraft && _eccDraft.epipedo_morfosis) || "0",
        branch_aa: (_eccDraft && _eccDraft.branch_aa) || "",
        change_date: changeDate,
        change_types: selectedTypes,
        basics_acceptance: acceptanceEl.value,
        specialty: document.getElementById("eccSpecialty").value,
        specialty_code: specialtyCode,
        salary,
        hourly_wage: document.getElementById("eccHourly").value,
        weekly_hours: weeklyHours,
        fulltime_contract_weekly_hours: document.getElementById("eccFulltimeHours").value,
        weekly_work_days: document.getElementById("eccWeekDays").value,
        regime: document.getElementById("eccRegime").value,
        employment_relation: document.getElementById("eccRelation").value,
        fixed_term_from: relation === "1" ? fixedFrom : "",
        fixed_term_to: relation === "1" ? fixedTo : "",
        comments: document.getElementById("eccComments").value,
      };
      const body = new FormData();
      body.append("payload", JSON.stringify(payload));
      if (uploadFile) body.append("file", uploadFile, uploadFile.name);

      const res = await fetch("/api/employees/contract/change/submit", {
        method: "POST",
        body,
      });
      const data = await res.json();
      if (!res.ok) {
        msg(data.error || "Αποτυχία υποβολής", false);
        btn.disabled = false;
        return;
      }
      msg(data.message || "Η μεταβολή σύμβασης υποβλήθηκε επιτυχώς.", true);
      btn.disabled = false;
      await reloadEmployeeContractHistory(afm);
    } catch (e) {
      msg(String(e), false);
      btn.disabled = false;
    }
  });
}

async function reloadEmployeeContractHistory(afm) {
  const title = document.getElementById("employeeDetailTitle");
  const meta = document.getElementById("employeeDetailMeta");
  const wrap = document.getElementById("employeeContractWrap");
  const histSection = document.getElementById("employeeContractHistorySection");
  const histWrap = document.getElementById("employeeContractHistoryWrap");
  if (!wrap) return;
  try {
    const res = await fetch(
      `/api/employees/contract/history?employee_afm=${encodeURIComponent(afm)}`,
      { cache: "no-store" }
    );
    const data = await res.json();
    if (!res.ok) return;
    renderEmployeeContractHistory(afm, data, title, meta, wrap, histSection, histWrap);
  } catch (_) {
    /* ignore refresh errors */
  }
}

function renderEmployeeContractHistory(afm, data, title, meta, wrap, histSection, histWrap) {
  const rows = data.contracts || [];
  if (data.employee_name && title) title.textContent = data.employee_name;
  if (data.store && meta) {
    meta.textContent = `ΑΦΜ ${afm} · ${data.store.name || ""} · παράρτημα ${data.store.branch_aa ?? "0"}`;
  }
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">Δεν υπάρχουν στοιχεία σύμβασης.</p>`;
    histSection?.classList.add("hidden");
    return;
  }
  const current =
    rows.find((r) => r.is_current === true || r.is_current === 1 || r.is_current === "1") ||
    rows[0];
  const previous = rows.filter((r) => r !== current);
  wrap.innerHTML = "";
  wrap.appendChild(renderContractFieldsTable(current));

  if (!previous.length) {
    histSection?.classList.add("hidden");
    return;
  }
  histSection?.classList.remove("hidden");
  const t = document.createElement("table");
  t.className = "data";
  const hr = document.createElement("tr");
  ["Αποθήκευση έκδοσης", "Ενημ. Ergani", "Ειδικότητα", "Ώρες", "Αποδοχές", ""].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);
  previous.forEach((row) => {
    const tr = document.createElement("tr");
    [
      displayValue("synced_at", row.synced_at),
      displayValue("ergani_updated_at", row.ergani_updated_at),
      displayValue("specialty", row.specialty),
      displayValue("weekly_hours", row.weekly_hours),
      displayValue("salary", row.salary),
    ].forEach((text) => {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    });
    const tdAct = document.createElement("td");
    tdAct.className = "work-log-action-cell";
    const histBtn = document.createElement("button");
    histBtn.type = "button";
    histBtn.className = "btn btn-sm btn-secondary";
    histBtn.innerHTML = Office.icon("table");
    histBtn.title = "Αναλυτικά";
    histBtn.addEventListener("click", () => {
      wrap.innerHTML = "";
      const note = document.createElement("p");
      note.className = "table-meta";
      note.textContent =
        `Προβολή προηγούμενης έκδοσης · αποθήκευση ${displayValue("synced_at", row.synced_at)}`;
      wrap.appendChild(note);
      wrap.appendChild(renderContractFieldsTable(row));
      wrap.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    tdAct.appendChild(histBtn);
    tr.appendChild(tdAct);
    t.appendChild(tr);
  });
  if (histWrap) {
    histWrap.innerHTML = "";
    histWrap.appendChild(t);
  }
}

async function loadEmployeeDetail() {
  const params = new URLSearchParams(window.location.search);
  const afm = (params.get("afm") || params.get("employee_afm") || "").trim();
  const nameQ = `${(params.get("eponymo") || "").trim()} ${(params.get("onoma") || "").trim()}`.trim();
  const title = document.getElementById("employeeDetailTitle");
  const meta = document.getElementById("employeeDetailMeta");
  const wrap = document.getElementById("employeeContractWrap");
  const histSection = document.getElementById("employeeContractHistorySection");
  const histWrap = document.getElementById("employeeContractHistoryWrap");

  if (!afm) {
    title.textContent = "Άγνωστος εργαζόμενος";
    wrap.innerHTML = '<p style="color:var(--err);">Λείπει <code>afm</code> στο URL.</p>';
    return;
  }
  title.textContent = nameQ || `ΑΦΜ ${afm}`;
  meta.textContent = `ΑΦΜ ${afm}`;
  setupEmploymentDates(afm);
  setupCateringOverride(afm);
  setupContractChange(afm);

  try {
    await Office.loadActiveStore();
    const res = await fetch(
      `/api/employees/contract/history?employee_afm=${encodeURIComponent(afm)}`,
      { cache: "no-store" }
    );
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    renderEmployeeContractHistory(afm, data, title, meta, wrap, histSection, histWrap);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

async function setupCateringOverride(afm) {
  const form = document.getElementById("employeeCateringForm");
  const select = document.getElementById("employeeCateringOverride");
  const status = document.getElementById("employeeCateringStatus");
  try {
    const res = await fetch("/api/employees/list?limit=5000", { cache: "no-store" });
    const data = await res.json();
    const row = (data.employees || []).find((item) => String(item.afm || "") === afm);
    if (row) {
      select.value = row.catering_override == null ? "auto" : row.catering_override ? "yes" : "no";
    }
  } catch (_) {}
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "Αποθήκευση…";
    const override = select.value === "auto" ? null : select.value === "yes";
    const res = await fetch("/api/employees/catering-override", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employee_afm: afm, catering_override: override }),
    });
    const data = await res.json();
    status.textContent = res.ok ? "Αποθηκεύτηκε" : data.error || "Αποτυχία αποθήκευσης";
  });
}

async function setupEmploymentDates(afm) {
  const form = document.getElementById("employeeEmploymentDatesForm");
  const hire = document.getElementById("employeeHireDate");
  const departure = document.getElementById("employeeDepartureDate");
  const status = document.getElementById("employeeEmploymentDatesStatus");
  const hirePicker = Office.attachGreekDateField({ inputEl: hire, allowEmpty: true });
  const departurePicker = Office.attachGreekDateField({ inputEl: departure, allowEmpty: true });
  try {
    const res = await fetch("/api/employees/list?limit=5000", { cache: "no-store" });
    const data = await res.json();
    const row = (data.employees || []).find((item) => String(item.afm || "") === afm);
    if (row) {
      hirePicker?.setIso(row.hire_date || "", true);
      departurePicker?.setIso(row.departure_date || "", true);
    }
  } catch (_) {}
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "Αποθήκευση…";
    const res = await fetch("/api/employees/employment-dates", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employee_afm: afm,
        hire_date: hirePicker?.getIso() || "",
        departure_date: departurePicker?.getIso() || "",
      }),
    });
    const data = await res.json();
    status.textContent = res.ok ? "Αποθηκεύτηκε" : data.error || "Αποτυχία αποθήκευσης";
  });
}
