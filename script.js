document.addEventListener("DOMContentLoaded", () => {

  const toggle = document.querySelector(".menu-toggle");

  const nav = document.querySelector(".nav-links");

  if (toggle && nav) {

    toggle.addEventListener("click", () => {

      const open = nav.classList.toggle("open");

      toggle.setAttribute("aria-expanded", String(open));

      toggle.textContent = open ? "✕" : "☰";

    });

  }

  document.querySelectorAll("form[data-confirm]").forEach((form) => {

    form.addEventListener("submit", (event) => {

      const message = form.dataset.confirm || "Are you sure?";

      if (!window.confirm(message)) event.preventDefault();

    });

  });

  document.querySelectorAll('input[type="file"]').forEach((input) => {

    input.addEventListener("change", () => {

      if (input.files && input.files[0]) {

        const maxSize = 8 * 1024 * 1024;

        if (input.files[0].size > maxSize) {

          alert("Please keep the image file size under 8 MB.");

          input.value = "";

        }

      }

    });

  });

});
