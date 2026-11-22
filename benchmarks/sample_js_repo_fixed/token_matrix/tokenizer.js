/**
 * Tokenizer module for text tokens (Fixed revision).
 */

/**
 * Extracts tokens separated by delimiter safely.
 * @param {string} text Raw text input.
 * @param {string} delimiter Token separator.
 * @returns {Array<string>} Array of string tokens.
 */
export function extractTokens(text, delimiter) {
  if (text === null || text === undefined) {
    return [];
  }
  return String(text).split(delimiter || ",");
}

/**
 * Normalizes weight against a maximum scale.
 * @param {number} weight Raw weight.
 * @param {number} scale Normalization scale.
 * @throws {Error} if scale is zero
 * @returns {number} Normalized weight.
 */
export function normalizeWeight(weight, scale) {
  if (scale === 0 || !scale) {
    throw new Error("scale cannot be zero");
  }
  return weight / scale;
}

