/**
 * The shape every controller here exposes, and the one React's
 * `useSyncExternalStore(store.subscribe, store.getSnapshot)` reads directly.
 *
 * A snapshot is immutable and replaced whole on a change, so a reader can
 * compare it by identity; `getSnapshot()` returns the same object until
 * something changes, which `useSyncExternalStore` requires.
 */
export interface ReadableStore<T> {
  subscribe(listener: () => void): () => void;
  getSnapshot(): T;
}

/** A small store: hold a snapshot, replace it, tell subscribers. */
export class Store<T> implements ReadableStore<T> {
  private snapshot: T;
  readonly #listeners = new Set<() => void>();

  constructor(initial: T) {
    this.snapshot = initial;
  }

  readonly subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener);
    return () => {
      this.#listeners.delete(listener);
    };
  };

  readonly getSnapshot = (): T => this.snapshot;

  /** Replace the snapshot. A patch that changes no field notifies nobody. */
  protected set(patch: Partial<T>): void {
    const next = { ...this.snapshot, ...patch };
    let changed = false;
    for (const key of Object.keys(patch) as (keyof T)[]) {
      if (!Object.is(next[key], this.snapshot[key])) {
        changed = true;
        break;
      }
    }
    if (!changed) return;
    this.snapshot = next;
    for (const listener of [...this.#listeners]) listener();
  }
}
