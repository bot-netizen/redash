import { DOMPurify } from "@/services/sanitize";

/**
 * Whether a URL built from a cell may be a link or an image source.
 *
 * A template of `{{ @ }}` over a column that holds `javascript:...` made a
 * link that ran it; only the page's script policy stood in the way. DOMPurify
 * already knows which schemes an href or a src may carry, and it is the same
 * answer the sanitizer gives a textbox.
 */
export function isSafeHref(url: string): boolean {
  return DOMPurify.isValidAttribute("a", "href", url);
}

export function isSafeImageSource(url: string): boolean {
  return DOMPurify.isValidAttribute("img", "src", url);
}
