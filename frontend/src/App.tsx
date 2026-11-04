import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ApiError,
  Answer,
  Citation,
  Community,
  DocumentRow,
  askQuestion,
  createCommunity,
  deleteCommunity,
  deleteDocument,
  listCommunities,
  listDocuments,
  loadUserId,
  saveUserId,
  uploadDocument,
} from "./api";

type Turn = {
  id: string;
  question: string;
  answer?: Answer;
  error?: string;
};

const STATUS_LABEL: Record<DocumentRow["status"], string> = {
  pending: "Pendiente",
  processing: "Procesando",
  ready: "Listo",
  failed: "Fallido",
};

export function App() {
  const [userId, setUserId] = useState(loadUserId);
  const [userDraft, setUserDraft] = useState(loadUserId);
  const [communities, setCommunities] = useState<Community[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [communityName, setCommunityName] = useState("");
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [docsOpen, setDocsOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [histories, setHistories] = useState<Record<string, Turn[]>>({});
  const [citation, setCitation] = useState<Citation | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const transcriptEnd = useRef<HTMLDivElement>(null);

  const selected = communities.find((community) => community.id === selectedId) ?? null;
  const turns = selectedId ? (histories[selectedId] ?? []) : [];
  const waiting = turns.some((turn) => !turn.answer && !turn.error);
  const ingesting = documents.some((doc) => doc.status === "pending" || doc.status === "processing");
  const readyCount = documents.filter((doc) => doc.status === "ready").length;

  useEffect(() => {
    let cancelled = false;
    listCommunities(userId)
      .then((rows) => {
        if (cancelled) return;
        setCommunities(rows);
        setSelectedId((current) => current ?? rows[0]?.id ?? null);
      })
      .catch((error: unknown) => {
        if (!cancelled) setBanner(messageOf(error));
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    if (!selectedId) {
      setDocuments([]);
      return;
    }
    let cancelled = false;
    const pull = () => {
      listDocuments(userId, selectedId)
        .then((rows) => {
          if (!cancelled) setDocuments(rows);
        })
        .catch((error: unknown) => {
          if (!cancelled) setBanner(messageOf(error));
        });
    };
    pull();
    if (!ingesting) {
      return () => {
        cancelled = true;
      };
    }
    const timer = window.setInterval(pull, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedId, userId, ingesting]);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: "end" });
  }, [turns, selectedId]);

  function updateTurns(communityId: string, updater: (current: Turn[]) => Turn[]) {
    setHistories((current) => ({
      ...current,
      [communityId]: updater(current[communityId] ?? []),
    }));
  }

  function applyUser(event: FormEvent) {
    event.preventDefault();
    const next = userDraft.trim();
    if (!/^[A-Za-z0-9._@-]{1,120}$/.test(next)) {
      setBanner("El identificador solo admite letras, números y . _ @ -");
      return;
    }
    saveUserId(next);
    setUserId(next);
    setSelectedId(null);
    setHistories({});
    setCitation(null);
    setDocsOpen(false);
    setBanner(null);
  }

  async function addCommunity(event: FormEvent) {
    event.preventDefault();
    const name = communityName.trim();
    if (!name) return;
    setBusy(true);
    setBanner(null);
    try {
      const created = await createCommunity(userId, name);
      setCommunities((current) => [created, ...current]);
      setSelectedId(created.id);
      setCommunityName("");
      setCreating(false);
      setDocsOpen(true);
      setDocuments([]);
      setQuestion("");
    } catch (error) {
      setBanner(messageOf(error));
    } finally {
      setBusy(false);
    }
  }

  async function removeCommunity(community: Community) {
    const confirmed = window.confirm(
      `¿Eliminar la comunidad «${community.name}» y todos sus documentos?`,
    );
    if (!confirmed) return;
    setBusy(true);
    setBanner(null);
    try {
      await deleteCommunity(userId, community.id);
      const remaining = communities.filter((item) => item.id !== community.id);
      setCommunities(remaining);
      setHistories((current) => {
        const next = { ...current };
        delete next[community.id];
        return next;
      });
      if (selectedId === community.id) {
        setSelectedId(remaining[0]?.id ?? null);
        setDocuments([]);
        setCitation(null);
        setDocsOpen(false);
      }
    } catch (error) {
      setBanner(messageOf(error));
    } finally {
      setBusy(false);
    }
  }

  function clearHistory() {
    if (!selectedId || turns.length === 0) return;
    const confirmed = window.confirm("¿Borrar las preguntas y respuestas de esta comunidad?");
    if (!confirmed) return;
    setHistories((current) => ({ ...current, [selectedId]: [] }));
    setCitation(null);
  }

  async function removeDocument(doc: DocumentRow) {
    if (!selectedId) return;
    const confirmed = window.confirm(
      `¿Eliminar «${doc.filename}»? Dejará de usarse en las respuestas.`,
    );
    if (!confirmed) return;
    setBusy(true);
    setBanner(null);
    try {
      await deleteDocument(userId, selectedId, doc.id);
      setDocuments((current) => current.filter((item) => item.id !== doc.id));
      setCitation((current) => (current?.document_id === doc.id ? null : current));
    } catch (error) {
      setBanner(messageOf(error));
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(file: File | undefined) {
    if (!file || !selectedId) return;
    setBusy(true);
    setBanner(null);
    try {
      const document = await uploadDocument(userId, selectedId, file);
      setDocuments((current) => {
        const rest = current.filter((item) => item.id !== document.id);
        return [document, ...rest];
      });
    } catch (error) {
      setBanner(messageOf(error));
    } finally {
      setBusy(false);
    }
  }

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || waiting || question.trim().length < 3) return;
    const communityId = selectedId;
    const asked = question.trim();
    const id = crypto.randomUUID();
    updateTurns(communityId, (current) => [...current, { id, question: asked }]);
    setQuestion("");
    setBanner(null);
    try {
      const answer = await askQuestion(userId, communityId, asked);
      updateTurns(communityId, (current) =>
        current.map((turn) => (turn.id === id ? { ...turn, answer } : turn)),
      );
    } catch (error) {
      const text = messageOf(error);
      updateTurns(communityId, (current) =>
        current.map((turn) => (turn.id === id ? { ...turn, error: text } : turn)),
      );
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <p className="eyebrow">Faro Administraciones</p>
          <h1>Chat de actas</h1>
        </div>
        <button type="button" onClick={() => setCreating(true)}>
          Nueva comunidad
        </button>
        <form className="user-form" onSubmit={applyUser}>
          <label htmlFor="user-id">Administrador</label>
          <div>
            <input
              id="user-id"
              value={userDraft}
              onChange={(event) => setUserDraft(event.target.value)}
              autoComplete="off"
            />
            <button type="submit" className="ghost">
              Usar
            </button>
          </div>
        </form>
      </header>

      {banner ? <p className="banner">{banner}</p> : null}

      <div className="shell">
        <aside className="sidebar">
          <p className="side-label">Comunidades</p>
          <ul className="community-list">
            {communities.length === 0 ? (
              <li className="muted empty-side">Crea una comunidad para empezar.</li>
            ) : null}
            {communities.map((community) => (
              <li key={community.id}>
                <button
                  type="button"
                  className={community.id === selectedId ? "community active" : "community"}
                  onClick={() => {
                    setSelectedId(community.id);
                    setCitation(null);
                    setDocsOpen(false);
                    setQuestion("");
                  }}
                >
                  <span>{community.name}</span>
                  <small>{new Date(community.created_at).toLocaleDateString("es-ES")}</small>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="chat-screen">
          {selected ? (
            <>
              <header className="chat-head">
                <div>
                  <h2>{selected.name}</h2>
                  <p className="muted">
                    {readyCount === 1 ? "1 documento listo" : `${readyCount} documentos listos`}
                  </p>
                </div>
                <div className="chat-actions">
                  <button
                    type="button"
                    className={docsOpen ? "ghost active-toggle" : "ghost"}
                    onClick={() => setDocsOpen((open) => !open)}
                  >
                    Documentos{documents.length > 0 ? ` (${documents.length})` : ""}
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    disabled={turns.length === 0}
                    onClick={clearHistory}
                  >
                    Limpiar historial
                  </button>
                  <button
                    type="button"
                    className="danger"
                    disabled={busy}
                    onClick={() => void removeCommunity(selected)}
                  >
                    Eliminar
                  </button>
                </div>
              </header>

              {docsOpen ? (
                <section className="docs-drawer" aria-label="Documentos de la comunidad">
                  <div className="docs-toolbar">
                    <p className="muted">Estos archivos son la evidencia del chat.</p>
                    <label className="upload">
                      Subir PDF o texto
                      <input
                        type="file"
                        accept=".pdf,.txt,application/pdf,text/plain"
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          void onUpload(file);
                          event.target.value = "";
                        }}
                        disabled={busy}
                      />
                    </label>
                  </div>
                  {documents.length === 0 ? (
                    <p className="muted">Todavía no hay documentos.</p>
                  ) : (
                    <ul className="doc-list">
                      {documents.map((doc) => (
                        <li key={doc.id}>
                          <div>
                            <strong>{doc.filename}</strong>
                            <span className={`pill pill-${doc.status}`}>{STATUS_LABEL[doc.status]}</span>
                            {doc.page_count ? <small className="muted">{doc.page_count} pág.</small> : null}
                            {doc.error_message ? <small className="error-text">{doc.error_message}</small> : null}
                          </div>
                          <button
                            type="button"
                            className="danger"
                            disabled={busy}
                            onClick={() => void removeDocument(doc)}
                          >
                            Eliminar
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ) : null}

              <div className="transcript" aria-live="polite">
                {turns.length === 0 ? (
                  <div className="chat-empty">
                    <h3>Pregunta sobre {selected.name}</h3>
                    <p>La respuesta cita el documento, la página y el fragmento. Si no hay evidencia, el asistente se abstiene.</p>
                  </div>
                ) : null}
                {turns.map((turn) => (
                  <article key={turn.id} className="exchange">
                    <p className="bubble bubble-user">{turn.question}</p>
                    {!turn.answer && !turn.error ? (
                      <p className="bubble bubble-bot pending">Consultando los documentos…</p>
                    ) : null}
                    {turn.error ? <p className="bubble bubble-bot error-text">{turn.error}</p> : null}
                    {turn.answer ? <AnswerCard answer={turn.answer} onOpen={setCitation} /> : null}
                  </article>
                ))}
                <div ref={transcriptEnd} />
              </div>

              <form className="composer" onSubmit={onAsk}>
                <label htmlFor="question" className="sr-only">
                  Pregunta
                </label>
                <textarea
                  id="question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder="Escribe una pregunta sobre esta comunidad"
                  rows={2}
                  disabled={waiting}
                />
                <button
                  type="submit"
                  className="send"
                  aria-label="Enviar"
                  disabled={waiting || question.trim().length < 3}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path fill="currentColor" d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z" />
                  </svg>
                </button>
              </form>
            </>
          ) : (
            <section className="chat-empty welcome">
              <h2>Elige una comunidad</h2>
              <p>La lista de la izquierda abre su chat. Nueva comunidad está siempre arriba.</p>
            </section>
          )}
        </main>
      </div>

      {creating ? (
        <div className="modal-backdrop" onClick={() => setCreating(false)} role="presentation">
          <form
            className="modal"
            onSubmit={addCommunity}
            onClick={(event) => event.stopPropagation()}
          >
            <h2>Nueva comunidad</h2>
            <p className="muted">Aparece en la lista de la izquierda y abre su propio chat.</p>
            <label htmlFor="community-name">Nombre</label>
            <input
              id="community-name"
              value={communityName}
              onChange={(event) => setCommunityName(event.target.value)}
              placeholder="Residencial Alameda"
              maxLength={200}
              autoFocus
            />
            <div className="modal-actions">
              <button type="button" className="ghost" onClick={() => setCreating(false)}>
                Cancelar
              </button>
              <button type="submit" disabled={busy || communityName.trim().length === 0}>
                Crear
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {citation ? (
        <div className="drawer-backdrop" onClick={() => setCitation(null)} role="presentation">
          <aside
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="citation-title"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="eyebrow">Fragmento fuente</p>
            <h2 id="citation-title">{citation.document_name}</h2>
            <p className="page">Página {citation.page}</p>
            <blockquote>{citation.fragment}</blockquote>
            <button type="button" onClick={() => setCitation(null)}>
              Cerrar
            </button>
          </aside>
        </div>
      ) : null}
    </div>
  );
}

function AnswerCard({ answer, onOpen }: { answer: Answer; onOpen: (citation: Citation) => void }) {
  const tone = !answer.sufficient_evidence ? "thin" : answer.degraded ? "degraded" : "solid";
  const label = !answer.sufficient_evidence
    ? "Sin evidencia suficiente"
    : answer.degraded
      ? "Respuesta degradada"
      : "Evidencia citada";
  return (
    <div className={`bubble bubble-bot answer answer-${tone}`}>
      <p className="flag">{label}</p>
      <p className="answer-text">{answer.answer}</p>
      {answer.citations.length > 0 ? (
        <ul className="citations">
          {answer.citations.map((item, index) => (
            <li key={`${item.document_id}-${item.page}-${index}`}>
              <button type="button" onClick={() => onOpen(item)}>
                {item.document_name} · p. {item.page}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "No se pudo completar la operación";
}
