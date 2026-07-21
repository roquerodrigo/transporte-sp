/**
 * Give wide tables a scrolling wrapper instead of scrolling the table itself.
 *
 * Starlight scrolls wide tables by setting `display: block` on the `<table>`, which removes
 * the element's table semantics — screen readers stop reporting rows, cells and header
 * association. Moving the overflow to a wrapper lets the table stay a table.
 *
 * The wrapper is also focusable, because a region that scrolls has to be reachable without
 * a pointer. `tabindex` is only set when the content actually overflows, so keyboard users
 * do not collect a stop on every table that fits.
 *
 * Plain JavaScript, injected into the head by the Astro config rather than loaded from a
 * component override: themes routinely override `Head`, and only one override wins.
 *
 * Technique borrowed from starlight-theme-exquisitus (MIT).
 */
(() => {
  const CLASSE = "tabela-rolavel";

  function envolver(tabela) {
    if (tabela.parentElement?.classList.contains(CLASSE)) return;

    const wrapper = document.createElement("div");
    wrapper.className = CLASSE;
    wrapper.setAttribute("role", "region");
    wrapper.setAttribute("aria-label", tabela.caption?.textContent?.trim() || "Tabela");
    tabela.replaceWith(wrapper);
    wrapper.append(tabela);

    const ajustarFoco = () => {
      if (wrapper.scrollWidth > wrapper.clientWidth) wrapper.setAttribute("tabindex", "0");
      else wrapper.removeAttribute("tabindex");
    };

    ajustarFoco();
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(ajustarFoco).observe(wrapper);
  }

  const envolverTodas = () =>
    document.querySelectorAll(".sl-markdown-content table").forEach(envolver);

  // The script runs in the head, so the content may not exist yet on the first load.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", envolverTodas);
  } else {
    envolverTodas();
  }
  document.addEventListener("astro:page-load", envolverTodas);
})();
