/**
 * Convert unknown values (including objects like {message: ...}) to a safe string for UI rendering.
 * Prevents React runtime error: "Objects are not valid as a React child".
 */
export function toDisplayString(value) {
  if (value === null || value === undefined) return '';

  const t = typeof value;
  if (t === 'string') return value;
  if (t === 'number' || t === 'boolean' || t === 'bigint') return String(value);

  if (t === 'object') {
    // Common axios/backend error shape
    if (typeof value.message === 'string') return value.message;
    try {
      return JSON.stringify(value);
    } catch (e) {
      return String(value);
    }
  }

  return String(value);
}




