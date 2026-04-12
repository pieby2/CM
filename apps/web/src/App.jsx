import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createCard,
  createDeck,
  createUser,
  deleteDeck,
  generateCardsFromImport,
  getDeckStats,
  getDueCards,
  getStreak,
  getWeakConcepts,
  gradeCard,
  listDecks,
  processImport,
  uploadPdf,
  getCardMnemonic,
  deckChat,
} from "./api";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

// ── Constants ──────────────────────────────────────────

const TABS = [
  { key: "review", label: "Review", icon: "⚡" },
  { key: "decks", label: "Decks", icon: "📚" },
  { key: "chat", label: "Chat", icon: "💬" },
  { key: "import", label: "Import PDF", icon: "📄" },
  { key: "add", label: "Add Card", icon: "✏️" },
];

const RATINGS = [
  { key: "again", label: "Again", hint: "Press 1", cls: "rating-again" },
  { key: "hard", label: "Hard", hint: "Press 2", cls: "rating-hard" },
  { key: "good", label: "Good", hint: "Press 3", cls: "rating-good" },
  { key: "easy", label: "Easy", hint: "Press 4", cls: "rating-easy" },
];

const EMPTY_STATS = { new_count: 0, learning_count: 0, mature_count: 0, total_count: 0 };
const EMPTY_STREAK = { current_streak: 0, longest_streak: 0, total_review_days: 0, last_review_date: null };
const CONFETTI_COLORS = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#f97316", "#ec4899"];

// ── Main App ───────────────────────────────────────────

export default function App() {
  const [email, setEmail] = useState("student@cue.local");
  const [user, setUser] = useState(null);
  const [tab, setTab] = useState("review");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [msgType, setMsgType] = useState("");

  // Deck state
  const [decks, setDecks] = useState([]);
  const [selectedDeckId, setSelectedDeckId] = useState("");
  const [deckSearch, setDeckSearch] = useState("");
  const [deckName, setDeckName] = useState("");

  // Review state
  const [sessionCards, setSessionCards] = useState([]);
  const [sessionIndex, setSessionIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [answerStart, setAnswerStart] = useState(Date.now());
  const [sessionComplete, setSessionComplete] = useState(false);
  const [mnemonic, setMnemonic] = useState(null);
  const [loadingMnemonic, setLoadingMnemonic] = useState(false);

  // Chat state
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);

  // Stats
  const [stats, setStats] = useState(EMPTY_STATS);
  const [weakConcepts, setWeakConcepts] = useState([]);
  const [streak, setStreak] = useState(EMPTY_STREAK);

  // Card authoring
  const [cardFront, setCardFront] = useState("");
  const [cardBack, setCardBack] = useState("");
  const [cardType, setCardType] = useState("definition");

  // PDF import
  const [importFile, setImportFile] = useState(null);
  const [importDeckName, setImportDeckName] = useState("");
  const [importSubject, setImportSubject] = useState("general");
  const [importStep, setImportStep] = useState("idle");
  const [importJobId, setImportJobId] = useState("");
  const [importResult, setImportResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  // Confetti
  const [confetti, setConfetti] = useState([]);

  // Settings dialog
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("cue_groq_api_key") || "");

  const fileInputRef = useRef(null);
  const msgTimeout = useRef(null);

  const currentCard = sessionCards[sessionIndex] ?? null;
  const reviewedCount = Math.min(sessionIndex, sessionCards.length);
  const totalCount = sessionCards.length;
  const progressPercent = totalCount === 0 ? 0 : Math.round((reviewedCount / totalCount) * 100);
  const selectedDeck = useMemo(() => decks.find((d) => d.id === selectedDeckId), [decks, selectedDeckId]);

  // ── Notifications ────────────────────────────────────

  const notify = useCallback((msg, type = "") => {
    setMessage(msg);
    setMsgType(type);
    if (msgTimeout.current) clearTimeout(msgTimeout.current);
    msgTimeout.current = setTimeout(() => setMessage(""), 4000);
  }, []);

  // ── Confetti ─────────────────────────────────────────

  const fireConfetti = useCallback(() => {
    const pieces = Array.from({ length: 40 }, (_, i) => ({
      id: i,
      left: Math.random() * 100,
      color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      delay: Math.random() * 0.8,
      size: 6 + Math.random() * 6,
    }));
    setConfetti(pieces);
    setTimeout(() => setConfetti([]), 3000);
  }, []);

  // ── Data refresh ─────────────────────────────────────

  async function refreshDecks(userId, preferredId = null) {
    const list = await listDecks(userId);
    setDecks(list);
    const nextId = preferredId || selectedDeckId || list[0]?.id || "";
    setSelectedDeckId(nextId);
    if (nextId) refreshInsights(userId, nextId);
  }

  async function refreshInsights(userId, deckId) {
    if (!deckId) {
      setStats(EMPTY_STATS);
      setWeakConcepts([]);
      return;
    }
    const [s, w, st] = await Promise.all([
      getDeckStats(deckId, userId).catch(() => EMPTY_STATS),
      getWeakConcepts(userId, deckId, 8).catch(() => []),
      getStreak(userId).catch(() => EMPTY_STREAK),
    ]);
    setStats(s);
    setWeakConcepts(w);
    setStreak(st);
  }

  useEffect(() => {
    if (user && selectedDeckId) {
      refreshInsights(user.id, selectedDeckId).catch(() => {});
    }
  }, [user, selectedDeckId]);

  // ── Keyboard shortcuts ───────────────────────────────

  useEffect(() => {
    function handleKey(e) {
      if (tab !== "review" || !currentCard || busy) return;
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

      if (!flipped && (e.code === "Space" || e.code === "Enter")) {
        e.preventDefault();
        setFlipped(true);
        return;
      }

      if (flipped) {
        const keyMap = { Digit1: "again", Digit2: "hard", Digit3: "good", Digit4: "easy" };
        const rating = keyMap[e.code];
        if (rating) {
          e.preventDefault();
          onGradeCard(rating);
        }
      }
    }

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [tab, currentCard, flipped, busy]);

  // ── Handlers ─────────────────────────────────────────

  async function onLogin(e) {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    try {
      const u = await createUser(email.trim().toLowerCase());
      setUser(u);
      await refreshDecks(u.id);
      notify(`Welcome, ${u.email}!`, "success");
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function onCreateDeck(e) {
    e.preventDefault();
    if (!user || !deckName.trim()) return;
    setBusy(true);
    try {
      const d = await createDeck({ user_id: user.id, name: deckName.trim(), tags: [] });
      await refreshDecks(user.id, d.id);
      setDeckName("");
      notify(`Deck "${d.name}" created`, "success");
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteDeck(deckId) {
    if (!confirm("Delete this deck and all its cards?")) return;
    setBusy(true);
    try {
      await deleteDeck(deckId);
      await refreshDecks(user.id);
      notify("Deck deleted", "success");
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function onCreateCard(e) {
    e.preventDefault();
    if (!selectedDeckId || !cardFront.trim() || !cardBack.trim()) return;
    setBusy(true);
    try {
      await createCard({
        deck_id: selectedDeckId,
        front: cardFront.trim(),
        back: cardBack.trim(),
        tags: [],
        type: cardType,
        difficulty_estimate: 1.0,
      });
      setCardFront("");
      setCardBack("");
      await refreshInsights(user.id, selectedDeckId);
      notify("Card added!", "success");
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function onLoadSession() {
    if (!user || !selectedDeckId) return;
    setBusy(true);
    setSessionComplete(false);
    try {
      const res = await getDueCards(user.id, selectedDeckId, 60);
      setSessionCards(res.items);
      setSessionIndex(0);
      setFlipped(false);
      setMnemonic(null);
      setAnswerStart(Date.now());
      if (res.items.length === 0) {
        notify("No cards due — you're all caught up! 🎉");
      } else {
        notify(`${res.items.length} cards ready for review`);
      }
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function onGradeCard(rating) {
    if (!user || !currentCard) return;
    setBusy(true);
    try {
      await gradeCard({
        user_id: user.id,
        card_id: currentCard.card_id,
        rating,
        response_time_ms: Math.max(0, Date.now() - answerStart),
      });

      const nextIdx = sessionIndex + 1;
      setSessionIndex(nextIdx);
      setFlipped(false);
      setMnemonic(null);
      setAnswerStart(Date.now());

      if (nextIdx >= sessionCards.length) {
        setSessionComplete(true);
        fireConfetti();
      }

      await refreshInsights(user.id, selectedDeckId);
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  // ── Mnemonic ─────────────────────────────────────────

  async function onGenerateMnemonic() {
    if (!currentCard) return;
    setLoadingMnemonic(true);
    try {
      const res = await getCardMnemonic(currentCard.card_id, apiKey);
      setMnemonic(res.mnemonic);
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setLoadingMnemonic(false);
    }
  }

  // ── Chat ─────────────────────────────────────────────
  
  async function onSendChat(e) {
    e.preventDefault();
    if (!chatInput.trim() || !selectedDeckId) return;
    
    const userMsg = { role: "user", text: chatInput };
    setChatMessages((prev) => [...prev, userMsg]);
    setChatInput("");
    setChatBusy(true);

    try {
      const res = await deckChat(selectedDeckId, userMsg.text, apiKey);
      setChatMessages((prev) => [...prev, { role: "ai", text: res.reply }]);
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setChatBusy(false);
    }
  }

  // ── PDF Import ───────────────────────────────────────

  function onFileSelect(e) {
    const file = e.target.files?.[0];
    if (file) {
      setImportFile(file);
      if (!importDeckName) setImportDeckName(file.name.replace(/\.pdf$/i, ""));
    }
  }

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.name.toLowerCase().endsWith(".pdf")) {
      setImportFile(file);
      if (!importDeckName) setImportDeckName(file.name.replace(/\.pdf$/i, ""));
    }
  }

  async function onImportPdf() {
    if (!user || !importFile || !importDeckName.trim()) return;
    setBusy(true);

    try {
      // Step 1: Upload
      setImportStep("uploading");
      const job = await uploadPdf(user.id, importDeckName.trim(), importFile);
      setImportJobId(job.id);

      // Step 2: Extract & chunk
      setImportStep("processing");
      await processImport(job.id);

      // Step 3: Generate cards
      setImportStep("generating");
      const result = await generateCardsFromImport(job.id, {
        subject: importSubject,
        card_count_hint: 10,
      }, apiKey || null);
      setImportResult(result);
      setImportStep("done");

      // Refresh decks to show the new one
      await refreshDecks(user.id, result.deck_id);
      fireConfetti();
      notify(`Generated ${result.cards_created} cards from PDF!`, "success");
    } catch (err) {
      setImportStep("error");
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function resetImport() {
    setImportFile(null);
    setImportDeckName("");
    setImportStep("idle");
    setImportJobId("");
    setImportResult(null);
  }

  // ── Render Helpers ───────────────────────────────────
  function renderText(text, isFront) {
    if (!text) return null;
    let html = text.replace(/!\[.*?\]\((.*?)\)/g, (match, url) => {
      const fullUrl = url.startsWith("/") ? API_BASE.replace(/\/api$/, "") + url : url;
      return `<img src="${fullUrl}" style="max-width: 100%; border-radius: 8px; margin-top: 10px;" />`;
    });
    if (isFront) {
      html = html.replace(/{{(.*?)}}/g, `<span class="cloze-hidden">[...]</span>`);
    } else {
      html = html.replace(/{{(.*?)}}/g, `<span class="cloze-revealed">$1</span>`);
    }
    return <span dangerouslySetInnerHTML={{ __html: html }} />;
  }

  // ── Render ───────────────────────────────────────────

  if (!user) {
    return (
      <div className="app-shell">
        <div className="glow glow-left" />
        <div className="glow glow-right" />
        <div style={{ maxWidth: 420, margin: "12vh auto", textAlign: "center" }}>
          <div className="logo" style={{ width: 56, height: 56, fontSize: "1.6rem", margin: "0 auto 1.5rem" }}>C</div>
          <h1 style={{ fontFamily: "Fraunces, serif", fontSize: "2.2rem", marginBottom: "0.5rem" }}>Cue Math</h1>
          <p className="muted" style={{ marginBottom: "2rem" }}>Smart flashcards powered by AI and spaced repetition</p>
          <form onSubmit={onLogin} className="panel" style={{ textAlign: "left" }}>
            <div className="form-group">
              <label>Email</label>
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoFocus
              />
            </div>
            <button type="submit" className="btn btn-primary btn-lg" style={{ width: "100%" }} disabled={busy}>
              {busy ? <span className="spinner" /> : "Get Started"}
            </button>
          </form>
        </div>
        {message && <div className={`status-bar ${msgType}`}>{message}</div>}
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="glow glow-left" />
      <div className="glow glow-right" />

      {/* Confetti */}
      {confetti.map((p) => (
        <div
          key={p.id}
          className="confetti-piece"
          style={{
            left: `${p.left}%`,
            background: p.color,
            width: p.size,
            height: p.size,
            animationDelay: `${p.delay}s`,
          }}
        />
      ))}

      {/* Header */}
      <header className="page-header">
        <div className="header-left">
          <div className="logo">C</div>
          <span className="brand-name">Cue Math</span>
        </div>
        <div className="header-right">
          {streak.current_streak > 0 && (
            <div className="streak-badge">🔥 {streak.current_streak} day streak</div>
          )}
          <div style={{ display: "flex", alignItems: "center" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: "600", marginRight: "0.5rem" }}>Groq API Key:</span>
            <input
              type="password"
              placeholder="gsk_..."
              value={apiKey}
              onChange={(e) => {
                const val = e.target.value.trim();
                setApiKey(val);
                if (val) localStorage.setItem("cue_groq_api_key", val);
                else localStorage.removeItem("cue_groq_api_key");
              }}
              style={{
                padding: "0.35rem 0.6rem",
                fontSize: "0.82rem",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-default)",
                background: "var(--bg-surface)",
                color: "var(--text-primary)",
                width: "180px",
                outline: "none",
              }}
              onFocus={(e) => {
                e.target.style.borderColor = "var(--accent-primary)";
                e.target.style.boxShadow = "0 0 0 2px var(--accent-primary-glow)";
              }}
              onBlur={(e) => {
                e.target.style.borderColor = "var(--border-default)";
                e.target.style.boxShadow = "none";
              }}
            />
          </div>
          <div className="user-badge">{user.email}</div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="nav-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`nav-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            <span className="tab-icon">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </nav>

      {/* ── Review Tab ──────────────────────────────── */}
      {tab === "review" && (
        <div className="layout-grid">
          <div>
            {/* Stats Panel */}
            <div className="panel">
              <h2 className="panel-title">📊 Mastery Overview</h2>
              <div className="stats-grid">
                <div className="stat-box">
                  <p className="stat-value accent">{stats.new_count}</p>
                  <p className="stat-label">New</p>
                </div>
                <div className="stat-box">
                  <p className="stat-value warning">{stats.learning_count}</p>
                  <p className="stat-label">Learning</p>
                </div>
                <div className="stat-box">
                  <p className="stat-value success">{stats.mature_count}</p>
                  <p className="stat-label">Mastered</p>
                </div>
                <div className="stat-box">
                  <p className="stat-value">{stats.total_count}</p>
                  <p className="stat-label">Total</p>
                </div>
              </div>
            </div>

            {/* Weak Concepts */}
            <div className="panel">
              <h2 className="panel-title">🎯 Focus Areas</h2>
              {weakConcepts.length === 0 ? (
                <p className="muted" style={{ fontSize: "0.88rem" }}>Review cards to see concept insights.</p>
              ) : (
                <ul className="weak-list">
                  {weakConcepts.map((item) => {
                    const pct = Math.round(item.avg_mastery * 100);
                    const cls = pct < 40 ? "mastery-low" : pct < 70 ? "mastery-mid" : "mastery-high";
                    return (
                      <li key={item.concept_id} className="weak-item">
                        <span className="weak-name">{item.concept_name}</span>
                        <div className="flex items-center gap-05">
                          <span className="weak-mastery">{pct}%</span>
                          <div className="mastery-bar-bg">
                            <div className={`mastery-bar-fill ${cls}`} style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>

          {/* Review Session */}
          <div>
            <div className="panel">
              <div className="flex justify-between items-center" style={{ marginBottom: "1rem" }}>
                <div>
                  <h2 className="panel-title" style={{ marginBottom: 0 }}>⚡ Review Session</h2>
                  <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                    {selectedDeck?.name || "Select a deck from the Decks tab"}
                  </p>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={onLoadSession}
                  disabled={busy || !selectedDeckId}
                >
                  {busy ? <span className="spinner" /> : "Load Due Cards"}
                </button>
              </div>

              {totalCount > 0 && (
                <>
                  <div className="progress-wrap">
                    <div className="progress-bar" style={{ width: `${progressPercent}%` }} />
                  </div>
                  <div className="progress-info">
                    <span>{reviewedCount} / {totalCount} reviewed</span>
                    <span>{progressPercent}%</span>
                  </div>
                </>
              )}

              {/* Session complete */}
              {sessionComplete && (
                <div className="celebration">
                  <div className="celebration-icon">🏆</div>
                  <h3 className="celebration-title">Session Complete!</h3>
                  <p className="celebration-text">
                    You reviewed {totalCount} cards. Great work keeping up with your studies!
                  </p>
                  <button className="btn btn-primary btn-lg" onClick={onLoadSession}>
                    Load More Cards
                  </button>
                </div>
              )}

              {/* No cards */}
              {!sessionComplete && totalCount === 0 && (
                <div className="empty-state" style={{ marginTop: "1rem" }}>
                  <div className="empty-state-icon">📖</div>
                  <p className="empty-state-title">Ready to study?</p>
                  <p className="muted mt-05">Click "Load Due Cards" to start your review session.</p>
                </div>
              )}

              {/* Active card */}
              {!sessionComplete && currentCard && (
                <>
                  <div
                    className="review-area"
                    style={{ marginTop: "1rem" }}
                    onClick={() => !flipped && setFlipped(true)}
                  >
                    <div className={`flashcard-wrapper ${flipped ? "flipped" : ""}`}>
                      {/* Front face */}
                      <div className="flashcard-face">
                        <div className="card-type-badge">{currentCard.type}</div>
                        <p className="flashcard-label">Question</p>
                        <p className="flashcard-text">{renderText(currentCard.front, true)}</p>
                        {!flipped && (
                          <p className="flashcard-hint">
                            Click or press <kbd className="kbd">Space</kbd> to reveal
                          </p>
                        )}
                      </div>
                      {/* Back face */}
                      <div className="flashcard-face flashcard-back">
                        <p className="flashcard-label">Answer</p>
                        <p className="flashcard-text">{renderText(currentCard.back, false)}</p>
                      </div>
                    </div>
                  </div>

                  {flipped && !mnemonic && (
                      <div style={{ textAlign: "center", marginTop: "1rem" }}>
                         <button className="btn btn-secondary" onClick={onGenerateMnemonic} disabled={loadingMnemonic}>
                            {loadingMnemonic ? <span className="spinner" /> : "💡 Need a mnemonic?"}
                         </button>
                      </div>
                  )}

                  {flipped && mnemonic && (
                      <div className="panel" style={{ marginTop: "1rem", background: "var(--bg-surface)", border: "1px dashed var(--accent-primary)" }}>
                         <h4 style={{ margin: "0 0 0.5rem 0", color: "var(--accent-primary)" }}>💡 Memory Trick</h4>
                         <p style={{ margin: 0, fontSize: "0.95rem" }}>{mnemonic}</p>
                      </div>
                  )}

                  {flipped && (
                    <div className="rating-grid" style={{ marginTop: "1rem" }}>
                      {RATINGS.map((r) => (
                        <button
                          key={r.key}
                          className={`rating-btn ${r.cls}`}
                          onClick={() => onGradeCard(r.key)}
                          disabled={busy}
                        >
                          {r.label}
                          <span className="rating-hint">{r.hint}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Decks Tab ───────────────────────────────── */}
      {tab === "decks" && (
        <div className="layout-single">
          <div className="panel">
            <h2 className="panel-title">📚 Your Decks</h2>

            <div className="flex gap-05" style={{ marginBottom: "1rem" }}>
              <div className="search-wrap" style={{ flex: 1 }}>
                <span className="search-icon">🔍</span>
                <input
                  placeholder="Search decks..."
                  value={deckSearch}
                  onChange={(e) => setDeckSearch(e.target.value)}
                />
              </div>
            </div>

            <form onSubmit={onCreateDeck} className="flex gap-05 mb-1">
              <input
                value={deckName}
                onChange={(e) => setDeckName(e.target.value)}
                placeholder="New deck name..."
                style={{ flex: 1 }}
              />
              <button type="submit" className="btn btn-primary" disabled={busy || !deckName.trim()}>
                + Create
              </button>
            </form>

            {decks.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">📚</div>
                <p className="empty-state-title">No decks yet</p>
                <p className="muted mt-05">Create a deck or import a PDF to get started.</p>
              </div>
            ) : (
              <div className="deck-grid">
                {decks
                  .filter((d) => !deckSearch || d.name.toLowerCase().includes(deckSearch.toLowerCase()))
                  .map((d) => (
                    <div
                      key={d.id}
                      className={`deck-card ${d.id === selectedDeckId ? "active" : ""}`}
                      onClick={() => { setSelectedDeckId(d.id); setTab("review"); }}
                    >
                      <p className="deck-card-name">{d.name}</p>
                      <p className="deck-card-meta">
                        {d.tags?.length > 0 ? d.tags.join(", ") : "No tags"} · {new Date(d.created_at).toLocaleDateString()}
                      </p>
                      <div className="deck-card-actions" onClick={(e) => e.stopPropagation()}>
                        <button
                          className="deck-action-btn delete"
                          onClick={() => onDeleteDeck(d.id)}
                          title="Delete deck"
                        >
                          🗑️ Delete
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Chat Tab ────────────────────────────────── */}
      {tab === "chat" && (
        <div className="layout-single" style={{ maxWidth: 640, margin: "0 auto" }}>
          <div className="panel" style={{ display: "flex", flexDirection: "column", height: "70vh" }}>
            <h2 className="panel-title">💬 Chat with {selectedDeck?.name || "your Deck"}</h2>
            
            {!selectedDeckId ? (
              <div className="empty-state" style={{flex: 1, justifyContent: "center", display: "flex", flexDirection: "column"}}>
                <p className="muted">Please select a deck from the Decks tab to chat with it.</p>
              </div>
            ) : (
              <>
                <div style={{ flex: 1, overflowY: "auto", padding: "1rem", border: "1px solid var(--border-default)", borderRadius: "var(--radius-md)", marginBottom: "1rem", background: "var(--bg-app)" }}>
                  {chatMessages.length === 0 ? (
                    <p className="muted" style={{ textAlign: "center", marginTop: "2rem" }}>Ask me anything about the concepts in this deck!</p>
                  ) : (
                    chatMessages.map((msg, i) => (
                      <div key={i} style={{
                        textAlign: msg.role === "user" ? "right" : "left",
                        marginBottom: "1rem"
                      }}>
                        <div style={{
                          display: "inline-block",
                          padding: "0.75rem 1rem",
                          borderRadius: "1rem",
                          maxWidth: "80%",
                          background: msg.role === "user" ? "var(--accent-primary)" : "var(--bg-surface)",
                          color: msg.role === "user" ? "#fff" : "var(--text-primary)",
                          boxShadow: "0 2px 8px rgba(0,0,0,0.05)",
                          border: msg.role === "ai" ? "1px solid var(--border-default)" : "none",
                          borderBottomRightRadius: msg.role === "user" ? 0 : "1rem",
                          borderBottomLeftRadius: msg.role === "ai" ? 0 : "1rem",
                        }}>
                          {msg.text}
                        </div>
                      </div>
                    ))
                  )}
                  {chatBusy && (
                    <div style={{ textAlign: "left" }}>
                      <div style={{ display: "inline-block", padding: "0.75rem", background: "var(--bg-surface)", borderRadius: "1rem", borderBottomLeftRadius: 0 }}>
                        <span className="spinner" style={{ borderColor: "var(--text-muted)", borderRightColor: "transparent" }}></span>
                      </div>
                    </div>
                  )}
                </div>
                
                <form onSubmit={onSendChat} style={{ display: "flex", gap: "0.5rem" }}>
                  <input 
                    placeholder="Ask a question..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    style={{ flex: 1 }}
                    autoFocus
                  />
                  <button type="submit" className="btn btn-primary" disabled={!chatInput.trim() || chatBusy}>Send</button>
                </form>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Import PDF Tab ──────────────────────────── */}
      {tab === "import" && (
        <div className="layout-single" style={{ maxWidth: 640, margin: "0 auto" }}>
          <div className="panel">
            <h2 className="panel-title">📄 Import PDF</h2>
            <p className="panel-subtitle">
              Drop a PDF and our AI will generate smart flashcards covering key concepts, definitions, relationships, and edge cases.
            </p>

            {importStep === "idle" && (
              <>
                <div
                  className={`upload-zone ${dragOver ? "drag-over" : ""}`}
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={onDrop}
                >
                  <div className="upload-icon">📤</div>
                  <p className="upload-title">
                    {importFile ? importFile.name : "Drop PDF here or click to browse"}
                  </p>
                  <p className="upload-hint">
                    {importFile
                      ? `${(importFile.size / 1024 / 1024).toFixed(1)} MB`
                      : "Supports textbook chapters, class notes, study guides"}
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf"
                    onChange={onFileSelect}
                    style={{ display: "none" }}
                  />
                </div>

                {importFile && (
                  <div style={{ marginTop: "1rem" }}>
                    <div className="form-row">
                      <div className="form-group">
                        <label>Deck Name</label>
                        <input
                          value={importDeckName}
                          onChange={(e) => setImportDeckName(e.target.value)}
                          placeholder="My Study Notes"
                        />
                      </div>
                      <div className="form-group">
                        <label>Subject</label>
                        <select value={importSubject} onChange={(e) => setImportSubject(e.target.value)}>
                          <option value="general">General</option>
                          <option value="math">Mathematics</option>
                          <option value="science">Science</option>
                          <option value="history">History</option>
                          <option value="literature">Literature</option>
                          <option value="cs">Computer Science</option>
                        </select>
                      </div>
                    </div>

                    <button
                      className="btn btn-success btn-lg"
                      style={{ width: "100%", marginTop: "0.5rem" }}
                      onClick={onImportPdf}
                      disabled={busy || !importDeckName.trim()}
                    >
                      {busy ? <><span className="spinner" /> Generating...</> : "✨ Generate Flashcards"}
                    </button>
                  </div>
                )}
              </>
            )}

            {importStep !== "idle" && importStep !== "done" && importStep !== "error" && (
              <div className="upload-progress">
                <UploadStep label="Uploading PDF..." status={importStep === "uploading" ? "active" : "done"} />
                <UploadStep
                  label="Extracting text & chunking..."
                  status={importStep === "processing" ? "active" : importStep === "generating" ? "done" : "pending"}
                />
                <UploadStep
                  label="AI generating flashcards..."
                  status={importStep === "generating" ? "active" : "pending"}
                />
              </div>
            )}

            {importStep === "done" && importResult && (
              <div className="celebration">
                <div className="celebration-icon">🎉</div>
                <h3 className="celebration-title">Flashcards Ready!</h3>
                <p className="celebration-text">
                  Created {importResult.cards_created} cards from {importResult.section_count} sections.
                </p>
                <div className="btn-row" style={{ justifyContent: "center" }}>
                  <button className="btn btn-primary btn-lg" onClick={() => { setTab("review"); resetImport(); }}>
                    Start Reviewing
                  </button>
                  <button className="btn btn-secondary btn-lg" onClick={resetImport}>
                    Import Another
                  </button>
                </div>
              </div>
            )}

            {importStep === "error" && (
              <div style={{ textAlign: "center", marginTop: "1.5rem" }}>
                <p style={{ color: "var(--accent-danger)", marginBottom: "1rem" }}>Import failed. Please try again.</p>
                <button className="btn btn-secondary" onClick={resetImport}>Try Again</button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Add Card Tab ────────────────────────────── */}
      {tab === "add" && (
        <div className="layout-single" style={{ maxWidth: 580, margin: "0 auto" }}>
          <div className="panel">
            <h2 className="panel-title">✏️ Add Card</h2>
            {!selectedDeckId ? (
              <div className="empty-state">
                <div className="empty-state-icon">📚</div>
                <p className="empty-state-title">No deck selected</p>
                <p className="muted mt-05">Go to the Decks tab and select or create a deck first.</p>
              </div>
            ) : (
              <form onSubmit={onCreateCard}>
                <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
                  Adding to: <strong style={{ color: "var(--text-primary)" }}>{selectedDeck?.name}</strong>
                </p>
                <div className="form-group">
                  <label>Question (Front)</label>
                  <textarea
                    value={cardFront}
                    onChange={(e) => setCardFront(e.target.value)}
                    rows={3}
                    placeholder="What is the discriminant of ax² + bx + c?"
                  />
                </div>
                <div className="form-group">
                  <label>Answer (Back)</label>
                  <textarea
                    value={cardBack}
                    onChange={(e) => setCardBack(e.target.value)}
                    rows={4}
                    placeholder="b² − 4ac. It determines the number and nature of the roots."
                  />
                </div>
                <div className="form-group">
                  <label>Card Type</label>
                  <select value={cardType} onChange={(e) => setCardType(e.target.value)}>
                    <option value="definition">Definition</option>
                    <option value="relationship">Relationship</option>
                    <option value="worked_example">Worked Example</option>
                    <option value="edge_case">Edge Case</option>
                  </select>
                </div>
                <button
                  type="submit"
                  className="btn btn-primary btn-lg"
                  style={{ width: "100%" }}
                  disabled={busy || !cardFront.trim() || !cardBack.trim()}
                >
                  Add Card
                </button>
              </form>
            )}
          </div>
        </div>
      )}


      {/* Status toast */}
      {message && <div className={`status-bar ${msgType}`}>{message}</div>}
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────

function UploadStep({ label, status }) {
  const icons = { done: "✓", active: "●", pending: "○" };
  const cls = { done: "step-done", active: "step-active", pending: "step-pending" };

  return (
    <div className="upload-step">
      <div className={`upload-step-icon ${cls[status]}`}>{icons[status]}</div>
      <span style={{ color: status === "pending" ? "var(--text-muted)" : "var(--text-primary)" }}>{label}</span>
      {status === "active" && <span className="spinner" style={{ marginLeft: "auto" }} />}
    </div>
  );
}
