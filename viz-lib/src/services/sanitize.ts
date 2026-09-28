import { isString } from "lodash";
import DOMPurify from "dompurify";

DOMPurify.setConfig({
  ADD_ATTR: ["target"],
  // No script runs, but a form still posts: a textbox reading "Session
  // expired, sign in" with a password field posting to another site looked
  // like SQLDesk to every viewer. `style=""` on an element stays, so an
  // author's layout survives; a `<style>` sheet that could hide the page
  // around such a form does not.
  FORBID_TAGS: ["form", "input", "button", "select", "textarea", "style"],
  FORBID_ATTR: ["action", "formaction"],
});

DOMPurify.addHook("afterSanitizeAttributes", function (node) {
  // Fix elements with `target` attribute:
  // - allow only `target="_blank"
  // - add `rel="noopener noreferrer"` to prevent https://www.owasp.org/index.php/Reverse_Tabnabbing

  const target = node.getAttribute("target");
  if (isString(target) && target.toLowerCase() === "_blank") {
    node.setAttribute("rel", "noopener noreferrer");
  } else {
    node.removeAttribute("target");
  }
});

export { DOMPurify };

export default DOMPurify.sanitize;
