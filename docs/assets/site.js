(function () {
  function getTrigger(dropdown) {
    return dropdown.querySelector("[data-nav-dropdown-trigger]");
  }

  function closeDropdown(dropdown) {
    const trigger = getTrigger(dropdown);
    dropdown.classList.remove("is-open");
    if (trigger) {
      trigger.setAttribute("aria-expanded", "false");
    }
    if (dropdown.contains(document.activeElement) && document.activeElement) {
      document.activeElement.blur();
    }
  }

  function openDropdown(dropdown) {
    const trigger = getTrigger(dropdown);
    dropdown.classList.add("is-open");
    if (trigger) {
      trigger.setAttribute("aria-expanded", "true");
    }
  }

  function initDropdowns() {
    const dropdowns = Array.from(document.querySelectorAll("[data-nav-dropdown]"));
    if (!dropdowns.length) {
      return;
    }

    function closeAll(except) {
      dropdowns.forEach((dropdown) => {
        if (dropdown !== except) {
          closeDropdown(dropdown);
        }
      });
    }

    dropdowns.forEach((dropdown) => {
      const trigger = getTrigger(dropdown);
      if (!trigger) {
        return;
      }

      dropdown.addEventListener("pointerenter", (event) => {
        if (event.pointerType === "touch") {
          return;
        }
        closeAll(dropdown);
        openDropdown(dropdown);
      });

      dropdown.addEventListener("pointerleave", (event) => {
        if (event.pointerType === "touch") {
          return;
        }
        closeDropdown(dropdown);
      });

      trigger.addEventListener("click", (event) => {
        event.preventDefault();
        const nextOpen = !dropdown.classList.contains("is-open");
        closeAll(dropdown);
        dropdown.classList.toggle("is-open", nextOpen);
        trigger.setAttribute("aria-expanded", nextOpen ? "true" : "false");
        if (!nextOpen) {
          trigger.blur();
        }
      });
    });

    document.addEventListener("click", (event) => {
      if (!(event.target instanceof Element)) {
        closeAll();
        return;
      }
      if (!event.target.closest("[data-nav-dropdown]")) {
        closeAll();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeAll();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDropdowns);
  } else {
    initDropdowns();
  }
})();
