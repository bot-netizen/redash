/**
 * A value from a query result, as text for HTML that will be set as
 * innerHTML -- which is what ECharts and Leaflet do with a tooltip or a popup.
 * A cell reading `<img src=x onerror=...>` is data, and must stay data.
 */
export default function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string
  );
}
