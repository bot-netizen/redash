import { map } from "lodash";
import escapeHtml from "@/lib/escapeHtml";

/**
 * What a marker says when no template is set. Leaflet sets these as innerHTML,
 * and every value is a cell from the query result. The template branch is
 * sanitized in initMap; these are the strings that were not.
 */
export function defaultTooltipHtml(lat: unknown, lon: unknown): string {
  return `<strong>${escapeHtml(lat)}, ${escapeHtml(lon)}</strong>`;
}

export function defaultPopupHtml(row: Record<string, unknown>, lat: unknown, lon: unknown): string {
  const rows = map(row, (v, k) => `<li>${escapeHtml(k)}: ${escapeHtml(v)}</li>`).join("");
  return `<ul style="list-style-type: none; padding-left: 0"><li>${defaultTooltipHtml(lat, lon)}${rows}</ul>`;
}
