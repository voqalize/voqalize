/**
 * Node 26 defines a global `localStorage` that is `undefined` unless node runs
 * with --localstorage-file, and it shadows happy-dom's. Tests get an
 * in-memory one instead.
 */
class MemoryStorage implements Storage {
  private m = new Map<string, string>();
  get length() {
    return this.m.size;
  }
  clear() {
    this.m.clear();
  }
  getItem(k: string) {
    return this.m.has(k) ? (this.m.get(k) as string) : null;
  }
  key(i: number) {
    return [...this.m.keys()][i] ?? null;
  }
  removeItem(k: string) {
    this.m.delete(k);
  }
  setItem(k: string, v: string) {
    this.m.set(k, String(v));
  }
}
for (const name of ["localStorage", "sessionStorage"] as const) {
  if (!(globalThis as Record<string, unknown>)[name]) {
    Object.defineProperty(globalThis, name, { value: new MemoryStorage(), configurable: true, writable: true });
  }
}
