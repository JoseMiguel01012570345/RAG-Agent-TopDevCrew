import { FormEvent, useEffect, useState } from "react";
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
  const [communityName, setCommunityName] = useState("");
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = communities.find((community) => community.id === selectedId) ?? null;
  const ingesting = documents.some((doc) => doc.status === "pending" || doc.status === "processing");

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
    setTurns([]);
    setCitation(null);
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
      setTurns([]);
      setDocuments([]);
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
      if (selectedId === community.id) {
        setSelectedId(remaining[0]?.id ?? null);
        setTurns([]);
        setDocuments([]);
        setCitation(null);
      }
    } catch (error) {
      setBanner(messageOf(error));
    } finally {
      setBusy(false);
    }
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
    if (!selectedId || question.trim().length < 3) return;
    const asked = question.trim();
    const id = crypto.randomUUID();
    setTurns((current) => [{ id, question: asked }, ...current]);
    setQuestion("");
    setBanner(null);
    try {
      const answer = await askQuestion(userId, selectedId, asked);
      setTurns((current) => current.map((turn) => (turn.id === id ? { ...turn, answer } : turn)));
    } catch (error) {
      const text = messageOf(error);
      setTurns((current) => current.map((turn) => (turn.id === id ? { ...turn, error: text } : turn)));
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <p className="eyebrow">Faro Administraciones</p>
          <h1>Mesa de documentos</h1>
        </div>
        <form className="user-form" onSubmit={applyUser}>
          <label htmlFor="user-id">Administrador simulado</label>
          <div>
            <input
              id="user-id"
              value={userDraft}
              onChange={(event) => setUserDraft(event.target.value)}
              autoComplete="off"
            />
            <button type="submit">Usar</button>
          </div>
        </form>
      </header>

      {banner ? <p className="banner">{banner}</p> : null}

      <div className="shell">
        <aside className="sidebar">
          <form onSubmit={addCommunity} className="stack">
            <label htmlFor="community-name">Nueva comunidad</label>
            <input
              id="community-name"
              value={communityName}
              onChange={(event) => setCommunityName(event.target.value)}
              placeholder="Residencial Alameda"
              maxLength={200}
            />
            <button type="submit" disabled={busy || communityName.trim().length === 0}>
              Crear
            </button>
          </form>
          <ul className="community-list">
            {communities.length === 0 ? <li className="muted">Todavía no hay comunidades.</li> : null}
            {communities.map((community) => (
              <li key={community.id}>
                <button
                  type="button"
                  className={community.id === selectedId ? "community active" : "community"}
                  onClick={() => {
                    setSelectedId(community.id);
                    setTurns([]);
                    setCitation(null);
                  }}
                >
                  <span>{community.name}</span>
                  <small>{new Date(community.created_at).toLocaleDateString("es-ES")}</small>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="workspace">
          {selected ? (
            <>
              <section className="panel">
                <div className="panel-head">
                  <div>
                    <p className="eyebrow">Comunidad</p>
                    <h2>{selected.name}</h2>
                  </div>
                  <div className="panel-actions">
                    <button
                      type="button"
                      className="danger"
                      disabled={busy}
                      onClick={() => void removeCommunity(selected)}
                    >
                      Eliminar comunidad
                    </button>
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
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>Documento</th>
                      <th>Estado</th>
                      <th>Páginas</th>
                      <th className="sr-only">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="muted">
                          Sube un acta, un reglamento o un .txt para indexarlo.
                        </td>
                      </tr>
                    ) : null}
                    {documents.map((doc) => (
                      <tr key={doc.id}>
                        <td>
                          <strong>{doc.filename}</strong>
                          {doc.error_message ? <small className="error-text">{doc.error_message}</small> : null}
                        </td>
                        <td>
                          <span className={`pill pill-${doc.status}`}>{STATUS_LABEL[doc.status]}</span>
                        </td>
                        <td>{doc.page_count ?? "—"}</td>
                        <td>
                          <button
                            type="button"
                            className="danger"
                            disabled={busy}
                            onClick={() => void removeDocument(doc)}
                          >
                            Eliminar
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <section className="panel chat">
                <div className="panel-head">
                  <div>
                    <p className="eyebrow">Consulta</p>
                    <h2>Pregunta con cita</h2>
                  </div>
                </div>
                <form onSubmit={onAsk} className="ask">
                  <label htmlFor="question" className="sr-only">
                    Pregunta
                  </label>
                  <textarea
                    id="question"
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder="¿Qué se aprobó sobre la reparación del ascensor?"
                    rows={3}
                  />
                  <button type="submit" disabled={question.trim().length < 3}>
                    Preguntar
                  </button>
                </form>
                <div className="turns">
                  {turns.length === 0 ? (
                    <p className="muted">Las respuestas salen con documento, página y fragmento.</p>
                  ) : null}
                  {turns.map((turn) => (
                    <article key={turn.id} className="turn">
                      <p className="question">{turn.question}</p>
                      {!turn.answer && !turn.error ? <p className="muted">Consultando…</p> : null}
                      {turn.error ? <p className="error-text">{turn.error}</p> : null}
                      {turn.answer ? <AnswerCard answer={turn.answer} onOpen={setCitation} /> : null}
                    </article>
                  ))}
                </div>
              </section>
            </>
          ) : (
            <section className="panel empty">
              <h2>Elige o crea una comunidad</h2>
              <p>Cada comunidad aísla sus documentos. Otro administrador no los ve.</p>
            </section>
          )}
        </main>
      </div>

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
    <div className={`answer answer-${tone}`}>
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
