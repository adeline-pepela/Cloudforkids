/**
 * Cloud for Kids — lesson quiz + module exam interactivity.
 *
 * Markup contract:
 *   Practice quiz (instant feedback), used inside a lesson's "Quiz Time" section:
 *     <div class="mcq-question" data-correct="1">
 *       <p class="mcq-prompt">...</p>
 *       <div class="mcq-options">
 *         <button type="button" class="mcq-option" data-index="0">...</button>
 *         ...
 *       </div>
 *       <div class="mcq-explain">...</div>
 *     </div>
 *
 *   Full module exam (graded only once "Submit" is pressed), wraps the same
 *   .mcq-question markup inside:
 *     <div class="exam-form" data-pass="70">
 *       <div class="exam-progress-wrap">...</div>
 *       ...mcq-question blocks...
 *       <div class="exam-submit-row"><button class="exam-submit-btn">...</button></div>
 *       <div class="exam-result"></div>
 *     </div>
 */
(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function gradeQuestion(question, optionBtn) {
    var correctIndex = parseInt(question.getAttribute("data-correct"), 10);
    var chosenIndex = parseInt(optionBtn.getAttribute("data-index"), 10);
    var options = question.querySelectorAll(".mcq-option");

    options.forEach(function (btn) {
      btn.disabled = true;
      var idx = parseInt(btn.getAttribute("data-index"), 10);
      if (idx === correctIndex) btn.classList.add("is-correct");
    });

    optionBtn.classList.add("is-selected");
    if (chosenIndex !== correctIndex) optionBtn.classList.add("is-incorrect");

    question.classList.add("is-answered");
    question.setAttribute("data-chosen", String(chosenIndex));
    return chosenIndex === correctIndex;
  }

  function setupPracticeQuizzes() {
    var practiceQuestions = document.querySelectorAll(".mcq-question");
    practiceQuestions.forEach(function (question) {
      if (question.closest(".exam-form")) return; // handled separately
      var options = question.querySelectorAll(".mcq-option");
      options.forEach(function (btn) {
        btn.addEventListener("click", function () {
          if (question.classList.contains("is-answered")) return;
          gradeQuestion(question, btn);
        });
      });
    });
  }

  function updateExamProgress(examForm) {
    var questions = examForm.querySelectorAll(".mcq-question");
    var answered = examForm.querySelectorAll(".mcq-question[data-chosen-pending]").length;
    var bar = examForm.querySelector(".exam-progress-bar");
    var label = examForm.querySelector(".exam-progress-label");
    var total = questions.length;
    var pct = total ? Math.round((answered / total) * 100) : 0;
    if (bar) bar.style.width = pct + "%";
    if (label) label.textContent = "Answered " + answered + " of " + total;
  }

  function setupExams() {
    var exams = document.querySelectorAll(".exam-form");
    exams.forEach(function (examForm) {
      var questions = examForm.querySelectorAll(".mcq-question");

      questions.forEach(function (question) {
        var options = question.querySelectorAll(".mcq-option");
        options.forEach(function (btn) {
          btn.addEventListener("click", function () {
            // Single-select: just mark the chosen option, no grading yet.
            options.forEach(function (b) { b.classList.remove("is-selected"); });
            btn.classList.add("is-selected");
            question.setAttribute("data-chosen-pending", btn.getAttribute("data-index"));
            updateExamProgress(examForm);
          });
        });
      });

      var submitBtn = examForm.querySelector(".exam-submit-btn");
      if (!submitBtn) return;

      submitBtn.addEventListener("click", function () {
        var total = questions.length;
        var correctCount = 0;
        var resultItems = [];

        questions.forEach(function (question, i) {
          var correctIndex = parseInt(question.getAttribute("data-correct"), 10);
          var chosenAttr = question.getAttribute("data-chosen-pending");
          var chosenIndex = chosenAttr === null ? -1 : parseInt(chosenAttr, 10);
          var options = question.querySelectorAll(".mcq-option");
          var isCorrect = chosenIndex === correctIndex;
          if (isCorrect) correctCount++;

          options.forEach(function (btn) {
            btn.disabled = true;
            var idx = parseInt(btn.getAttribute("data-index"), 10);
            if (idx === correctIndex) btn.classList.add("is-correct");
            if (idx === chosenIndex && !isCorrect) btn.classList.add("is-incorrect");
          });
          question.classList.add("is-answered");

          var promptEl = question.querySelector(".mcq-prompt");
          var promptText = promptEl ? promptEl.textContent : "Question " + (i + 1);
          resultItems.push(
            "<li>" +
              "<span class=\"" + (isCorrect ? "tag-correct" : "tag-incorrect") + "\">" +
              (isCorrect ? "\u2713 Correct" : "\u2717 Review") +
              "</span> &mdash; " + promptText +
              "</li>"
          );
        });

        var pct = total ? Math.round((correctCount / total) * 100) : 0;
        var passMark = parseInt(examForm.getAttribute("data-pass"), 10) || 70;
        var passed = pct >= passMark;

        var resultBox = examForm.querySelector(".exam-result");
        if (resultBox) {
          resultBox.classList.add("show", passed ? "pass" : "fail");
          resultBox.classList.remove(passed ? "fail" : "pass");
          resultBox.innerHTML =
            "<div class=\"exam-score\">" + pct + "%</div>" +
            "<p class=\"fw-bold mb-1\">" + correctCount + " out of " + total + " correct</p>" +
            "<p class=\"mb-0\">" +
              (passed
                ? "\uD83C\uDF89 Great job \u2014 you passed this module exam! Scroll down and mark it complete."
                : "You need " + passMark + "% to pass. Review the questions below, revisit the lessons you're unsure about, then try again.") +
            "</p>" +
            "<ul class=\"exam-result-list\">" + resultItems.join("") + "</ul>";
          resultBox.scrollIntoView({ behavior: "smooth", block: "center" });
        }

        submitBtn.disabled = true;
        updateExamProgress(examForm);
      });
    });
  }

  onReady(function () {
    setupPracticeQuizzes();
    setupExams();
  });
})();
