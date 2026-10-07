/**
 * Cloud for Kids: lesson quizzes and module exams.
 *
 * The page never contains the answers. Each answer (or the whole exam) is sent to the server, which checks it,
 * keeps the score, and replies with the right answer and an explanation. Lesson pages describe their URLs in
 * <div id="quiz-cfg" data-check-url data-finish-url data-grade-url data-reset-url data-needed data-exam data-passed data-score>.
 *
 * Markup in the lesson HTML:
 *   <div class="mcq-question"><p class="mcq-prompt">..</p><div class="mcq-options"><button class="mcq-option" data-index="0">..</button>..</div></div>
 *   (module exam) <div class="exam-form" data-pass="70"> .. questions .. <button class="exam-submit-btn"> <div class="exam-result"></div></div>
 */
(function () {
  "use strict";

  var cfg = null;

  /* Messages: English here, Kiswahili comes from window.C4K_T (set by the page). {0}, {1}... are filled in. */
  var EN = {
    checkFailed: "We could not check that answer. Please try again.",
    offline: "No internet? Check your connection and try again.",
    answered: "Answered {0} of {1}",
    saveFailed: "We could not save your score. Please try again.",
    gradeFailed: "We could not grade your exam. Please try again.",
    passedQuiz: "You passed this quiz{0}. You can finish the lesson.",
    gotQuiz: "You got {0} of {1} ({2}%). Quiz passed!",
    gotExam: "You got {0} of {1} ({2}%). Exam passed!",
    retry: "You got {0} of {1} ({2}%). You need {3}%. Have another go!",
    correct: "Correct",
    review: "Review",
    outOf: "{0} out of {1} correct",
    examPass: "Great job, you passed this module exam! Scroll down and mark it complete.",
    examFail: "You need {0}% to pass. Review the questions below, revisit the lessons you are unsure about, then try again.",
    answeredExam: "Answered {0} of {1}",
    stale: "This quiz was refreshed in another tab. Reload the page to continue.",
    tryAgain: "Try again with fresh questions",
    noCopy: "Copying and pasting are turned off during quizzes."
  };
  function T(key) {
    var text = (window.C4K_T && window.C4K_T[key]) || EN[key] || key;
    for (var i = 1; i < arguments.length; i++) text = text.replace("{" + (i - 1) + "}", arguments[i]);
    return text;
  }

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }
  function csrf() {
    var el = document.querySelector("input[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }
  function post(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(body || {})
    }).then(function (r) { return r.json().then(function (d) { d.__status = r.status; return d; }); });
  }
  function idx(btn) { return parseInt(btn.getAttribute("data-index"), 10); }
  function qid(question) { return parseInt(question.getAttribute("data-qid"), 10); }

  /* ---------- no copy and paste while answering ---------- */
  var ZONES = ".quiz-side, .exam-form, .mcq-block";
  function inQuiz(node) {
    var el = node && (node.nodeType === 1 ? node : node.parentElement);
    return !!(el && el.closest && el.closest(ZONES));
  }
  function lockQuiz() {
    function block(e) {
      var sel = window.getSelection && window.getSelection();
      if (inQuiz(e.target) || (sel && (inQuiz(sel.anchorNode) || inQuiz(sel.focusNode)))) {
        e.preventDefault();
        if (e.type !== "contextmenu" && statusEl && !statusEl.classList.contains("show")) info(T("noCopy"));
      }
    }
    ["copy", "cut", "paste", "contextmenu", "dragstart", "selectstart"].forEach(function (name) {
      document.addEventListener(name, block, true);
    });
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && /^[acvxp]$/i.test(e.key) && (inQuiz(e.target) || inQuiz(document.activeElement))) e.preventDefault();
    }, true);
  }

  /* ---------- status panel + unlock button (lesson page) ---------- */
  var statusEl, retryWrap, completeBtn, hintEl;
  function showStatus(ok, text) {
    if (!statusEl) return;
    statusEl.className = "quiz-status show " + (ok ? "pass" : "fail");
    statusEl.innerHTML = '<i class="bi ' + (ok ? "bi-check-circle-fill" : "bi-x-circle-fill") + '"></i> ' + text;
  }
  function info(text) {
    if (!statusEl) return;
    statusEl.className = "quiz-status show info";
    statusEl.textContent = text;
  }
  function unlock() {
    if (completeBtn) completeBtn.disabled = false;
    if (hintEl) { hintEl.remove(); hintEl = null; }
  }
  function onFinished(d, isExam) {
    if (d.unlocked) unlock();
    if (d.passed) {
      showStatus(true, T(isExam ? "gotExam" : "gotQuiz", d.correct, d.total, d.score_percent));
      if (window.c4kConfetti) window.c4kConfetti();
      if (retryWrap) retryWrap.classList.add("d-none");
    } else {
      showStatus(false, T("retry", d.correct, d.total, d.score_percent, d.needed));
      if (retryWrap) retryWrap.classList.remove("d-none");
    }
  }

  /* ---------- practice quiz: instant feedback, checked by the server ---------- */
  function markAnswered(question, d) {
    var options = question.querySelectorAll(".mcq-option");
    options.forEach(function (b) {
      b.disabled = true;
      if (idx(b) === d.correct_index) b.classList.add("is-correct");
      if (idx(b) === d.chosen && !d.correct) b.classList.add("is-incorrect");
      if (idx(b) === d.chosen) b.classList.add("is-selected");
    });
    question.classList.add("is-answered");
    question.setAttribute("data-chosen", String(d.chosen));
    question.setAttribute("data-right", d.correct ? "1" : "0");
    if (d.explain && !question.querySelector(".mcq-explain")) {
      var ex = document.createElement("div");
      ex.className = "mcq-explain";
      ex.innerHTML = d.explain;
      question.appendChild(ex);
    }
  }

  function setupPractice(questions) {
    var queue = Promise.resolve();  // answers go to the server one at a time, so none is lost if a child taps quickly
    var finishing = false;
    questions.forEach(function (question) {
      var qi = qid(question);
      question.querySelectorAll(".mcq-option").forEach(function (btn) {
        btn.addEventListener("click", function () {
          if (question.classList.contains("is-answered") || question.getAttribute("data-pending")) return;
          question.setAttribute("data-pending", "1");
          question.querySelectorAll(".mcq-option").forEach(function (b) { b.disabled = true; });
          var choice = idx(btn);
          queue = queue.then(function () {
            return post(cfg.dataset.checkUrl, { q: qi, choice: choice }).then(function (d) {
              question.removeAttribute("data-pending");
              if (d.error) {
                question.querySelectorAll(".mcq-option").forEach(function (b) { b.disabled = false; });
                showStatus(false, T(d.stale ? "stale" : "checkFailed"));
                return;
              }
              markAnswered(question, d);
              var answered = document.querySelectorAll(".mcq-question.is-answered").length;
              if (answered < questions.length) { info(T("answered", answered, questions.length)); return; }
              if (finishing) return;
              finishing = true;
              return post(cfg.dataset.finishUrl).then(function (f) {
                finishing = false;
                if (f.error) { showStatus(false, T(f.stale ? "stale" : "saveFailed")); return; }
                onFinished(f, false);
              });
            });
          }).catch(function () {
            question.removeAttribute("data-pending");
            finishing = false;
            question.querySelectorAll(".mcq-option").forEach(function (b) { b.disabled = false; });
            showStatus(false, T("offline"));
          });
        });
      });
    });

    /* Trying again reloads the page: the server then deals a new set of questions in a new order. */
    var retry = document.getElementById("quiz-retry");
    if (retry) retry.addEventListener("click", function () { window.location.reload(); });
  }

  /* ---------- module exam: pick answers, then the server grades them all ---------- */
  function updateExamProgress(form) {
    var qs = form.querySelectorAll(".mcq-question");
    var answered = form.querySelectorAll(".mcq-question[data-chosen-pending]").length;
    var bar = form.querySelector(".exam-progress-bar"), label = form.querySelector(".exam-progress-label");
    if (bar) bar.style.width = (qs.length ? Math.round(answered / qs.length * 100) : 0) + "%";
    if (label) label.textContent = T("answeredExam", answered, qs.length);
  }

  function setupExam(form) {
    var questions = form.querySelectorAll(".mcq-question");
    questions.forEach(function (question) {
      var options = question.querySelectorAll(".mcq-option");
      options.forEach(function (btn) {
        btn.addEventListener("click", function () {
          if (question.classList.contains("is-answered")) return;
          options.forEach(function (b) { b.classList.remove("is-selected"); });
          btn.classList.add("is-selected");
          question.setAttribute("data-chosen-pending", String(idx(btn)));
          updateExamProgress(form);
        });
      });
    });

    var submit = form.querySelector(".exam-submit-btn");
    if (!submit) return;
    submit.addEventListener("click", function () {
      var answers = {};
      questions.forEach(function (q) {
        var v = q.getAttribute("data-chosen-pending");
        answers[qid(q)] = v === null ? -1 : parseInt(v, 10);
      });
      submit.disabled = true;
      post(cfg.dataset.gradeUrl, { answers: answers }).then(function (d) {
        if (d.error) {
          submit.disabled = !!d.stale;
          var box0 = form.querySelector(".exam-result");
          if (d.stale && box0) { box0.classList.add("show", "fail"); box0.innerHTML = "<p class=\"mb-0\">" + T("stale") + "</p>"; }
          showStatus(false, T(d.stale ? "stale" : "gradeFailed"));
          return;
        }
        var items = [];
        questions.forEach(function (q, i) {
          var r = d.results[qid(q)], chosen = answers[qid(q)];
          q.querySelectorAll(".mcq-option").forEach(function (b) {
            b.disabled = true;
            if (idx(b) === r.correct_index) b.classList.add("is-correct");
            if (idx(b) === chosen && !r.correct) b.classList.add("is-incorrect");
          });
          q.classList.add("is-answered");
          var p = q.querySelector(".mcq-prompt");
          items.push("<li><span class=\"" + (r.correct ? "tag-correct" : "tag-incorrect") + "\">" +
            (r.correct ? "<i class=\"bi bi-check-circle-fill\"></i> " + T("correct") : "<i class=\"bi bi-x-circle-fill\"></i> " + T("review")) +
            "</span> &mdash; " + (p ? p.textContent : "Question " + (i + 1)) + "</li>");
        });
        var box = form.querySelector(".exam-result");
        if (box) {
          box.classList.add("show", d.passed ? "pass" : "fail");
          box.classList.remove(d.passed ? "fail" : "pass");
          box.innerHTML = "<div class=\"exam-score\">" + d.score_percent + "%</div>" +
            "<p class=\"fw-bold mb-1\">" + T("outOf", d.correct, d.total) + "</p>" +
            "<p class=\"mb-0\">" + (d.passed
              ? "<i class=\"bi bi-trophy-fill\"></i> " + T("examPass")
              : T("examFail", d.needed)) + "</p>" +
            (d.passed ? "" : "<button type=\"button\" class=\"btn btn-cloud mt-3 exam-retry\">" + T("tryAgain") + "</button>") +
            "<ul class=\"exam-result-list\">" + items.join("") + "</ul>";
          var again = box.querySelector(".exam-retry");
          if (again) again.addEventListener("click", function () { window.location.reload(); });
          box.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        if (d.unlocked) unlock();
        if (d.passed && window.c4kConfetti) window.c4kConfetti();
        updateExamProgress(form);
      }).catch(function () { submit.disabled = false; showStatus(false, T("offline")); });
    });
  }

  onReady(function () {
    cfg = document.getElementById("quiz-cfg");
    if (!cfg) return;
    statusEl = document.getElementById("quiz-status");
    retryWrap = document.getElementById("quiz-retry-wrap");
    completeBtn = document.getElementById("complete-btn");
    hintEl = document.getElementById("quiz-hint");
    lockQuiz();

    if (cfg.dataset.passed === "1") {
      unlock();
      showStatus(true, T("passedQuiz", cfg.dataset.score ? " (" + cfg.dataset.score + "%)" : ""));
    }

    var exam = document.querySelector(".exam-form");
    if (exam) { setupExam(exam); return; }

    /* Lesson quiz: move it into the side panel, then wire it up */
    var slot = document.getElementById("quiz-slot");
    if (slot) {
      var block = document.querySelector(".lesson-content .mcq-block");
      var section = block && block.closest(".lesson-section");
      if (section) slot.appendChild(section);
    }
    var questions = Array.prototype.slice.call(document.querySelectorAll(".mcq-question"));
    if (questions.length) setupPractice(questions);
  });
})();
