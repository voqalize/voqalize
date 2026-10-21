/**
 * `avatar-runtime.mjs`: swap the runtime `@voqalize/avatar` loads when
 * `AVATAR_RUNTIME` is set. Typed structurally rather than as vite's `Plugin`
 * because `shared/` does not install vite; every demo that imports this does.
 */
export function avatarRuntime(url?: string): { name: string } | null;
/** `url`, if it names a runtime on a host of unreleased runtimes; otherwise throws. */
export function unreleasedRuntime(url: string): string;
