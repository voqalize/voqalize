/**
 * What Javier never does on Uno Salud's pages, enforced here rather than left
 * to the prompt. Every press and every fill the adapters make goes through
 * these checks; a move that would break one fails, with the reason, and the
 * visitor is shown the control instead (the ring).
 *
 *   - He never sends anything: no form's `.submit()` or `requestSubmit()` is
 *     ever called, no key event is ever dispatched (so no Enter), and he never
 *     presses the buttons that send or commit: the booking's "Continuar" after
 *     the RUT (`#ingresar-rut`), "Registrarse" (`#registro-paciente`, which
 *     creates a patient record), "Confirmar cita" (`#confirma-cita`), any
 *     Brevo ENVIAR, any Contact Form 7 or help-desk submit.
 *   - He never types a RUT (the booking's `#rut`, Brevo's `#RUT`, the
 *     help-desk's `#rut`/`#contact_rut`, any field named so), never ticks a
 *     box (the booking's `#conditions`, the reclamos' `#terms`, any consent),
 *     and never touches the captcha (`#recaptchaResponse`,
 *     `g-recaptcha-response`, Google's frames).
 *   - He never follows the payment link the booking may show at the end
 *     (`#container_link_pago`).
 *
 * The presses he may make on the booking are its step buttons that only move
 * on: an existing patient's "Continuar" (`#actualiza-datos`, which only sends
 * optional contact details), the motivo's and the clinic's "Continuar"
 * (`#selecciona-motivo`, `#continue_getSuc`), a day of the calendar, and an
 * hour (`.option_hora`, which moves on to the review by itself).
 */

/** Buttons and links he never presses: the visitor does. */
export const NEVER_PRESS = [
  "#ingresar-rut",
  "#registro-paciente",
  "#confirma-cita",
  "#container_link_pago",
  "#container_link_pago *",
  "#btn_link_pago",
  "#sib-form button",
  "#sib-form [type=submit]",
  ".sib-form-block__button",
  "form.wpcf7-form [type=submit]",
  ".wpcf7-submit",
  "#helpdesk-form [type=submit]",
  "#helpdesk-form button",
  ".g-recaptcha",
  ".g-recaptcha *",
  "iframe[src*='recaptcha']",
].join(", ");

/** Fields he never fills or ticks: the visitor does. */
export const NEVER_FILL = [
  "#rut",
  "#RUT",
  "#contact_rut",
  "#conditions",
  "#terms",
  "#recaptchaResponse",
  "#g-recaptcha-response",
  "[name=g-recaptcha-response]",
  "[name=recaptchaResponse]",
  "input[type=checkbox]",
  "input[type=radio][name*=condic i]",
  "input[type=file]",
].join(", ");

/** A field whose name or id says it holds a RUT, whatever the page calls it. */
const RUT_NAME = /(^|[^a-z])rut([^a-z]|$)/i;

export class GuardError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GuardError";
  }
}

/** Whether `el` is a field Javier must never fill. */
export function neverFill(el: Element): boolean {
  if (el.matches(NEVER_FILL)) return true;
  if (el.closest(".g-recaptcha")) return true;
  const named = `${el.getAttribute("name") ?? ""} ${el.id}`;
  return RUT_NAME.test(named);
}

/** Whether `el` is a control Javier must never press. */
export function neverPress(el: Element): boolean {
  if (el.matches(NEVER_PRESS)) return true;
  // A form's own submit, wherever it is, other than the booking's step
  // buttons that only move on (see `MAY_PRESS`).
  const submit =
    (el instanceof HTMLButtonElement && el.type === "submit" && el.form) ||
    (el instanceof HTMLInputElement && (el.type === "submit" || el.type === "image") && el.form);
  if (submit && !el.matches(MAY_PRESS)) return true;
  return false;
}

/** The booking's step buttons he may press: each only moves the wizard on. */
export const MAY_PRESS = "#actualiza-datos, #selecciona-motivo, #continue_getSuc";

export function assertFillable(el: Element): void {
  if (neverFill(el)) {
    const id = el.id ? `#${el.id}` : (el.getAttribute("name") ?? el.tagName.toLowerCase());
    throw new GuardError(`${id} is the visitor's to fill (a RUT, a consent box or the captcha); it is ringed for them instead`);
  }
}

/** Press `el` as a visitor's click does, unless it is one he never presses. */
export function press(el: HTMLElement): void {
  if (neverPress(el)) {
    const id = el.id ? `#${el.id}` : clean(el.textContent) || el.tagName.toLowerCase();
    throw new GuardError(`${id} is the visitor's to press; it is ringed for them instead`);
  }
  el.click();
}

const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
