/**
 * Everything captions need, in one module the widget loads only when
 * captions are on: the element, its controller, and the binding to a
 * session's events.
 */

export { VqlCaptions } from "./captions.js";
export { CaptionsController } from "../controllers/captions.js";
export { bindCaptions } from "../controllers/bind-captions.js";
