const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

async function apiRequest(path, options = {}) {
  const isFormData = options.body instanceof FormData;

  const headers = isFormData
    ? { ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...(options.headers || {}) };

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

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

export function generateCardsFromImport(jobId, payload = {}, apiKey = null) {
  const headers = {};
  if (apiKey) {
    headers["X-Groq-Api-Key"] = apiKey;
  }

  return apiRequest(`/imports/${encodeURIComponent(jobId)}/generate`, {
    method: "POST",
    body: JSON.stringify(payload),
    headers,
  });
}
