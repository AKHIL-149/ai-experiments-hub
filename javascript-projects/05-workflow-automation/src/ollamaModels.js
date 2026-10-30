/**
 * Helpers for choosing the model a run uses.
 */

// Ollama names look like "llama3.2:3b", "qwen3:14b" or "hf.co/user/model:Q4_K_M"
const MODEL_NAME = /^[A-Za-z0-9][\w.\-:/]{0,99}$/;

/** Throws an error with status 400 unless the value is a usable model name. null/undefined/'' mean "default". */
function validateModelName(model) {
  if (model === undefined || model === null || model === '') {
    return null;
  }
  if (typeof model !== 'string' || !MODEL_NAME.test(model)) {
    const error = new Error('model must be a model name such as "llama3.2:3b"');
    error.status = 400;
    throw error;
  }
  return model;
}

/**
 * Models that can write text, from Ollama's /api/tags response. Embedding models
 * (which cannot generate) are left out; the rest are sorted by name.
 */
function listGenerationModels(tags) {
  return ((tags && tags.models) || [])
    .filter(m => m && typeof m.name === 'string')
    .filter(m => !/bert/i.test(m.details?.family || '') && !/embed/i.test(m.name))
    .map(m => ({
      name: m.name,
      parameterSize: m.details?.parameter_size || null,
      sizeBytes: Number.isFinite(m.size) ? m.size : null
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

module.exports = { validateModelName, listGenerationModels, MODEL_NAME };
