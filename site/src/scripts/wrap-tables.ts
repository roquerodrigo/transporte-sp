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
 * Technique borrowed from starlight-theme-exquisitus (MIT).
 */
function wrap(table: HTMLTableElement): void {
  if (table.parentElement?.classList.contains("tabela-rolavel")) return;

  const wrapper = document.createElement("div");
  wrapper.className = "tabela-rolavel";
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", table.caption?.textContent?.trim() || "Tabela");
  table.replaceWith(wrapper);
  wrapper.append(table);

  const setFocusable = () => {
    const overflows = wrapper.scrollWidth > wrapper.clientWidth;
    if (overflows) wrapper.setAttribute("tabindex", "0");
    else wrapper.removeAttribute("tabindex");
  };

  setFocusable();
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(setFocusable).observe(wrapper);
  }
}

function wrapAll(): void {
  document
    .querySelectorAll<HTMLTableElement>(".sl-markdown-content table")
    .forEach(wrap);
}

wrapAll();
// Starlight swaps the main content on client-side navigation.
document.addEventListener("astro:page-load", wrapAll);
