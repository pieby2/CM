const LOCALHOSTS = new Set(["localhost", "127.0.0.1"]);
const DEFAULT_API_BASE =
  typeof window !== "undefined" && !LOCALHOSTS.has(window.location.hostname)
    ? `${window.location.origin}/api`
    : "http://localhost:8000/api";

const API_BASE = import.meta.env.VITE_API_URL || DEFAULT_API_BASE;

const DEFAULT_LOCAL_TIMEOUT_MS = 12000;
const DEFAULT_REMOTE_TIMEOUT_MS = 45000;

function isLocalApiBase(apiBase) {
  try {
    const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost";
    const url = new URL(apiBase, origin);
    return LOCALHOSTS.has(url.hostname);
  } catch {
    return false;
  }
}

const parsedTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS);
const API_TIMEOUT_MS = Number.isFinite(parsedTimeout) && parsedTimeout > 0
  ? parsedTimeout
  : isLocalApiBase(API_BASE)
    ? DEFAULT_LOCAL_TIMEOUT_MS
    : DEFAULT_REMOTE_TIMEOUT_MS;

async function apiRequest(path, options = {}) {
  const { timeoutMs = API_TIMEOUT_MS, ...requestOptions } = options;
  const effectiveTimeoutMs = Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : API_TIMEOUT_MS;
  const isFormData = options.body instanceof FormData;

  const headers = isFormData
    ? { ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...(options.headers || {}) };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), effectiveTimeoutMs);

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...requestOptions,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") {
      const coldStartHint = isLocalApiBase(API_BASE)
        ? "Please ensure the API is running."
        : "The API may be cold-starting. Please retry in a few seconds.";
      throw new Error(
        `Request timed out after ${Math.round(effectiveTimeoutMs / 1000)}s. ${coldStartHint} Endpoint: ${API_BASE}.`
      );
    }

    if (err instanceof TypeError) {
      throw new Error(
        `Unable to reach API at ${API_BASE}. Start the backend or set VITE_API_URL to a reachable API.`
      );
    }

    throw err;
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const data = await response.json();
      if (data?.detail) {
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // ignore parse error and keep fallback detail
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function buildAiHeaders(apiKey = null, provider = "auto") {
  const headers = {};
  const normalizedKey = typeof apiKey === "string" ? apiKey.trim() : "";
  const normalizedProvider = typeof provider === "string" ? provider.trim().toLowerCase() : "";

  if (normalizedKey) {
    headers["X-AI-Api-Key"] = normalizedKey;
  }

  if (normalizedProvider && normalizedProvider !== "auto") {
    headers["X-AI-Provider"] = normalizedProvider;
  }

  return headers;
}

// ── Users ──────────────────────────────────────────────

export function createUser(email) {
  return apiRequest("/users", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

// ── Decks ──────────────────────────────────────────────

export function listDecks(userId, search = "") {
  const query = new URLSearchParams({ user_id: userId });
  if (search) query.set("search", search);
  return apiRequest(`/decks?${query.toString()}`);
}

export function createDeck(payload) {
  return apiRequest("/decks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateDeck(deckId, payload) {
  return apiRequest(`/decks/${encodeURIComponent(deckId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteDeck(deckId) {
  return apiRequest(`/decks/${encodeURIComponent(deckId)}`, {
    method: "DELETE",
  });
}

export function getDeckStats(deckId, userId) {
  return apiRequest(`/decks/${encodeURIComponent(deckId)}/stats?user_id=${encodeURIComponent(userId)}`);
}

// ── Cards ──────────────────────────────────────────────

export function listCards(deckId) {
  return apiRequest(`/cards?deck_id=${encodeURIComponent(deckId)}`);
}

export function createCard(payload) {
  return apiRequest("/cards", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCard(cardId, payload) {
  return apiRequest(`/cards/${encodeURIComponent(cardId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteCard(cardId) {
  return apiRequest(`/cards/${encodeURIComponent(cardId)}`, {
    method: "DELETE",
  });
}

// ── Reviews ────────────────────────────────────────────

export function getDueCards(userId, deckId, limit = 30) {
  const query = new URLSearchParams({
    user_id: userId,
    limit: String(limit),
  });
  if (deckId) {
    query.set("deck_id", deckId);
  }
  return apiRequest(`/reviews/today?${query.toString()}`);
}

export function gradeCard(payload) {
  return apiRequest("/reviews/grade", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getReviewHistory(userId, days = 30) {
  const query = new URLSearchParams({ user_id: userId, days: String(days) });
  return apiRequest(`/reviews/history?${query.toString()}`);
}

export function getStreak(userId) {
  return apiRequest(`/reviews/streak?user_id=${encodeURIComponent(userId)}`);
}

// ── Concepts ───────────────────────────────────────────

export function getWeakConcepts(userId, deckId, limit = 10) {
  const query = new URLSearchParams({
    user_id: userId,
    limit: String(limit),
  });
  if (deckId) {
    query.set("deck_id", deckId);
  }
  return apiRequest(`/concepts/weak?${query.toString()}`);
}

// ── Imports (PDF) ──────────────────────────────────────

export function uploadPdf(userId, deckName, file) {
  const formData = new FormData();
  formData.append("user_id", userId);
  formData.append("deck_name", deckName);
  formData.append("file", file);

  return apiRequest("/imports/pdf", {
    method: "POST",
    body: formData,
  });
}

export function getImportJob(jobId) {
  return apiRequest(`/imports/${encodeURIComponent(jobId)}`);
}

export function processImport(jobId) {
  return apiRequest(`/imports/${encodeURIComponent(jobId)}/process`, {
    method: "POST",
  });
}

export function getImportSections(jobId) {
  return apiRequest(`/imports/${encodeURIComponent(jobId)}/sections`);
}

export function generateCardsFromImport(jobId, payload = {}, apiKey = null, provider = "auto") {
  const headers = buildAiHeaders(apiKey, provider);
  return apiRequest(`/imports/${encodeURIComponent(jobId)}/generate`, {
    method: "POST",
    body: JSON.stringify(payload),
    headers,
  });
}

// ── Chat & Mnemonics ───────────────────────────────────

export function getCardMnemonic(cardId, apiKey = null, provider = "auto") {
  const headers = buildAiHeaders(apiKey, provider);
  return apiRequest(`/cards/${encodeURIComponent(cardId)}/mnemonic`, { headers });
}

export function deckChat(deckId, message, apiKey = null, provider = "auto") {
  const headers = buildAiHeaders(apiKey, provider);
  return apiRequest(`/chat/deck/${encodeURIComponent(deckId)}`, {
    method: "POST",
    body: JSON.stringify({ message }),
    headers,
  });
}
