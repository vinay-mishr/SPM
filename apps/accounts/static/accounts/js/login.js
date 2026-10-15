/* Accounts — login & password-reset pages
 * - Show/hide password buttons ([data-toggle-password="<input id>"])
 * - Inline required-field validation for forms marked [data-validate]
 * - Prevents double submission
 */
(function () {
  "use strict";

  function initPasswordToggles() {
    document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
      var input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;

      button.addEventListener("click", function () {
        var show = input.type === "password";
        input.type = show ? "text" : "password";
        button.setAttribute("aria-pressed", String(show));
        button.setAttribute("aria-label", show ? "Hide password" : "Show password");
        input.focus({ preventScroll: true });
      });
    });
  }

  function setFieldError(input, message) {
    var field = input.closest(".field");
    var error = document.getElementById(input.getAttribute("aria-describedby"));
    if (field) field.classList.toggle("field--invalid", Boolean(message));
    if (error) error.textContent = message || "";
    if (message) {
      input.setAttribute("aria-invalid", "true");
    } else {
      input.removeAttribute("aria-invalid");
    }
  }

  function validateInput(input) {
    var value = input.value.trim();
    if (input.required && !value) {
      return input.dataset.requiredMessage || "This field is required.";
    }
    if (input.type === "email" && value && !input.checkValidity()) {
      return "Please enter a valid email address.";
    }
    return "";
  }

  function initValidation() {
    document.querySelectorAll("form[data-validate]").forEach(function (form) {
      var inputs = Array.prototype.slice.call(form.querySelectorAll(".field__input"));

      inputs.forEach(function (input) {
        input.addEventListener("input", function () {
          if (input.getAttribute("aria-invalid") === "true") {
            setFieldError(input, validateInput(input));
          }
        });
      });

      form.addEventListener("submit", function (event) {
        var firstInvalid = null;

        inputs.forEach(function (input) {
          var message = validateInput(input);
          setFieldError(input, message);
          if (message && !firstInvalid) firstInvalid = input;
        });

        if (firstInvalid) {
          event.preventDefault();
          firstInvalid.focus();
          return;
        }

        var submit = form.querySelector('[type="submit"]');
        if (submit) {
          if (form.dataset.submitting) {
            event.preventDefault();
            return;
          }
          form.dataset.submitting = "true";
          submit.classList.add("is-loading");
          submit.setAttribute("aria-busy", "true");
        }
      });
    });
  }

  // Restore the button if the page is shown again from the back/forward cache.
  window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[data-validate]").forEach(function (form) {
      delete form.dataset.submitting;
      var submit = form.querySelector('[type="submit"]');
      if (submit) {
        submit.classList.remove("is-loading");
        submit.removeAttribute("aria-busy");
      }
    });
  });

  initPasswordToggles();
  initValidation();
})();
