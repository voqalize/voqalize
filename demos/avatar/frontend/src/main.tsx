/**
 * Avatar demo entrypoint — the open-source talking head explaining itself.
 *
 * One page, one call, one face: the brain puts an architecture slide on screen,
 * answers against it, and demonstrates its own wire protocol on the avatar the
 * visitor is looking at. `AvatarDemo` owns the session; there is nothing else on
 * the page.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AvatarDemo } from "./AvatarDemo";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AvatarDemo />
  </StrictMode>,
);
