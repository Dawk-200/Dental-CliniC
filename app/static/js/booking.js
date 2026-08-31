// Multi-step appointment booking wizard.
// IMPORTANT: this is UX only. The Flask backend independently re-validates
// treatment, date, and slot availability before ever creating a record.
document.addEventListener("DOMContentLoaded", function () {
  var wizard = document.getElementById("bookingWizard");
  if (!wizard) return;

  var state = {
    step: 1,
    treatmentId: null,
    treatmentDuration: 30,
    date: null,
    time: null,
    openWeekdays: [],
    calendarMonth: new Date().getMonth(),
    calendarYear: new Date().getFullYear(),
  };

  var steps = wizard.querySelectorAll(".wizard-step");
  var pills = wizard.querySelectorAll(".step-pill");

  function showStep(n) {
    steps.forEach(function (s) {
      s.classList.toggle("active", parseInt(s.dataset.step, 10) === n);
    });
    pills.forEach(function (p) {
      var pn = parseInt(p.dataset.step, 10);
      p.classList.toggle("active", pn === n);
      p.classList.toggle("done", pn < n);
    });
    state.step = n;
    window.scrollTo({ top: wizard.offsetTop - 90, behavior: "smooth" });
  }

  wizard.querySelectorAll("[data-next]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (!validateStep(state.step)) return;
      showStep(state.step + 1);
      if (state.step === 3) loadSlotsForCurrentDate();
    });
  });
  wizard.querySelectorAll("[data-prev]").forEach(function (btn) {
    btn.addEventListener("click", function () { showStep(state.step - 1); });
  });

  function validateStep(step) {
    if (step === 1) {
      if (!state.treatmentId) { alert("Please select a treatment to continue."); return false; }
      if (state.treatmentId === "other") {
        var text = document.getElementById("otherProblemText").value.trim();
        if (!text) { alert("Please describe your problem."); return false; }
      }
    }
    if (step === 2) {
      if (!state.date) { alert("Please select a date."); return false; }
    }
    if (step === 3) {
      if (!state.time) { alert("Please select an available time slot."); return false; }
      buildSummary();
    }
    if (step === 4) {
      var form = document.getElementById("patientInfoForm");
      if (!form.reportValidity()) return false;
    }
    return true;
  }

  // ---------- Step 1: Treatment selection ----------
  var treatmentOptions = wizard.querySelectorAll(".treatment-option");
  var otherWrap = document.getElementById("otherProblemWrap");
  treatmentOptions.forEach(function (opt) {
    opt.addEventListener("click", function () {
      treatmentOptions.forEach(function (o) { o.classList.remove("selected"); });
      opt.classList.add("selected");
      state.treatmentId = opt.dataset.treatmentId;
      state.treatmentDuration = parseInt(opt.dataset.duration || "30", 10);
      document.getElementById("selectedTreatmentId").value = state.treatmentId === "other" ? "" : state.treatmentId;
      if (otherWrap) otherWrap.style.display = state.treatmentId === "other" ? "block" : "none";
    });
  });

  // ---------- Step 2: Calendar ----------
  var calGrid = document.getElementById("calendarGrid");
  var calLabel = document.getElementById("calendarLabel");
  var monthNames = ["January","February","March","April","May","June","July","August","September","October","November","December"];

  fetch("/api/clinic-open-days").then(function (r) { return r.json(); }).then(function (data) {
    state.openWeekdays = data.open_weekdays || [];
    renderCalendar();
  }).catch(function () { renderCalendar(); });

  document.getElementById("calPrev").addEventListener("click", function () {
    state.calendarMonth--;
    if (state.calendarMonth < 0) { state.calendarMonth = 11; state.calendarYear--; }
    renderCalendar();
  });
  document.getElementById("calNext").addEventListener("click", function () {
    state.calendarMonth++;
    if (state.calendarMonth > 11) { state.calendarMonth = 0; state.calendarYear++; }
    renderCalendar();
  });

  function renderCalendar() {
    calGrid.innerHTML = "";
    ["Su","Mo","Tu","We","Th","Fr","Sa"].forEach(function (d) {
      var el = document.createElement("div");
      el.className = "dow"; el.textContent = d;
      calGrid.appendChild(el);
    });

    var firstDay = new Date(state.calendarYear, state.calendarMonth, 1);
    var startOffset = firstDay.getDay();
    var daysInMonth = new Date(state.calendarYear, state.calendarMonth + 1, 0).getDate();
    var today = new Date(); today.setHours(0,0,0,0);

    calLabel.textContent = monthNames[state.calendarMonth] + " " + state.calendarYear;

    for (var i = 0; i < startOffset; i++) {
      var empty = document.createElement("div");
      empty.className = "calendar-day empty";
      calGrid.appendChild(empty);
    }

    for (var day = 1; day <= daysInMonth; day++) {
      var cellDate = new Date(state.calendarYear, state.calendarMonth, day);
      var jsWeekday = cellDate.getDay(); // 0=Sun..6=Sat
      var pyWeekday = jsWeekday === 0 ? 6 : jsWeekday - 1; // convert to 0=Mon..6=Sun
      var isPast = cellDate < today;
      var isClosed = state.openWeekdays.length > 0 && state.openWeekdays.indexOf(pyWeekday) === -1;

      var cell = document.createElement("div");
      cell.className = "calendar-day";
      cell.textContent = day;

      var iso = cellDate.getFullYear() + "-" + String(cellDate.getMonth()+1).padStart(2,"0") + "-" + String(day).padStart(2,"0");

      if (isPast || isClosed) {
        cell.classList.add("disabled");
      } else {
        cell.addEventListener("click", function () {
          calGrid.querySelectorAll(".calendar-day.selected").forEach(function (c) { c.classList.remove("selected"); });
          this.classList.add("selected");
          state.date = this.dataset.iso;
          document.getElementById("selectedDateLabel").textContent = state.date;
        });
      }
      cell.dataset.iso = iso;
      if (state.date === iso) cell.classList.add("selected");
      calGrid.appendChild(cell);
    }
  }

  // ---------- Step 3: Slots ----------
  var slotsGrid = document.getElementById("slotsGrid");
  var slotsLoading = document.getElementById("slotsLoading");
  var slotsEmpty = document.getElementById("slotsEmpty");

  function loadSlotsForCurrentDate() {
    if (!state.date) return;
    slotsGrid.innerHTML = "";
    slotsEmpty.style.display = "none";
    slotsLoading.style.display = "block";
    document.getElementById("slotsDateLabel").textContent = state.date;

    var treatmentId = state.treatmentId === "other" ? "" : state.treatmentId;
    fetch("/api/available-slots?date=" + encodeURIComponent(state.date) + "&treatment_id=" + encodeURIComponent(treatmentId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        slotsLoading.style.display = "none";
        var slots = data.slots || [];
        if (slots.length === 0) {
          slotsEmpty.style.display = "block";
          return;
        }
        slots.forEach(function (s) {
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "slot-btn";
          btn.textContent = s.label;
          btn.dataset.value = s.value;
          btn.addEventListener("click", function () {
            slotsGrid.querySelectorAll(".slot-btn.selected").forEach(function (b) { b.classList.remove("selected"); });
            btn.classList.add("selected");
            state.time = s.value;
            document.getElementById("selectedTime").value = s.value;
          });
          slotsGrid.appendChild(btn);
        });
      })
      .catch(function () {
        slotsLoading.style.display = "none";
        slotsEmpty.style.display = "block";
        slotsEmpty.textContent = "Could not load slots. Please try again.";
      });
  }

  // ---------- Step 4 -> 5: Summary ----------
  function buildSummary() {
    document.getElementById("summaryDate").value = state.date;
    document.getElementById("summaryTime").value = state.time;
    document.getElementById("finalDate").textContent = state.date;
    document.getElementById("finalTime").textContent = document.querySelector(".slot-btn.selected") ? document.querySelector(".slot-btn.selected").textContent : state.time;
  }

  document.getElementById("bookingForm").addEventListener("submit", function (e) {
    var form = document.getElementById("patientInfoForm");
    if (!form.reportValidity()) { e.preventDefault(); return; }
  });

  showStep(1);
});
