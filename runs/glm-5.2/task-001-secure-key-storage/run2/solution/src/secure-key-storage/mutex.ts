/**
 * mutex.ts - Simple async mutex for serializing concurrent operations.
 *
 * Prevents race conditions when multiple async operations try to
 * read/write the same resource (e.g., IndexedDB, keychain).
 */

/**
 * Async mutex that serializes operations.
 * Each acquire() returns a release function that must be called.
 */
export class AsyncMutex {
  private queue: (() => void)[] = [];
  private locked = false;

  /**
   * Acquire the mutex. Returns a release function.
   * If the mutex is already held, waits until it is released.
   */
  async acquire(): Promise<() => void> {
    if (!this.locked) {
      this.locked = true;
      return this.createReleaser();
    }

    // Wait in queue
    return new Promise<() => void>((resolve) => {
      this.queue.push(() => {
        this.locked = true;
        resolve(this.createReleaser());
      });
    });
  }

  /**
   * Run a function while holding the mutex.
   * Automatically releases when the function completes or throws.
   */
  async run<T>(fn: () => Promise<T>): Promise<T> {
    const release = await this.acquire();
    try {
      return await fn();
    } finally {
      release();
    }
  }

  private createReleaser(): () => void {
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.locked = false;
      const next = this.queue.shift();
      if (next) {
        next();
      }
    };
  }
}
