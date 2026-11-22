/**
 * Tokenizer module for text tokens.
 */

/**
 * Extracts tokens separated by delimiter.
 * @param {string} text Raw text input.
 * @param {string} delimiter Token separator.
 * @returns {Array<string>} Array of string tokens.
 */
export function extractTokens(text, delimiter) {
  // Defect: Crashes with TypeError if text is null or undefined
  return text.split(delimiter);
}

/**
 * Normalizes weight against a maximum scale.
 * @param {number} weight Raw weight.
 * @param {number} scale Normalization scale.
 * @throws {Error} if scale is zero
 * @returns {number} Normalized weight.
 */
export function normalizeWeight(weight, scale) {
  // Defect: Contract violation - docstring says throws Error if scale is zero,
  // but code divides directly resulting in Infinity without throwing!
  return weight / scale;
}

