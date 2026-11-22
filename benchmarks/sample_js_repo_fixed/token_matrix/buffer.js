/**
 * Token buffer manager (Fixed revision).
 */
export class TokenBuffer {
  constructor() {
    this.buffer = [];
  }

  push(token) {
    this.buffer.push(token);
  }

  drain() {
    if (this.buffer.length === 0) {
      return null;
    }
    return this.buffer.pop();
  }
}

