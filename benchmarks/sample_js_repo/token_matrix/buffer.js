/**
 * Token buffer manager.
 */
export class TokenBuffer {
  constructor() {
    this.buffer = [];
  }

  push(token) {
    this.buffer.push(token);
  }

  drain() {
    // Defect: Empty state handling - pops without check, returning undefined or corrupting index
    if (this.buffer.length === 0) {
      throw new RangeError("Buffer underflow: cannot drain empty buffer");
    }
    return this.buffer.pop();
  }
}

