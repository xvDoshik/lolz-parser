import { useCallback, useEffect, useState } from "react";

type Status = {
  running: boolean;
  html_count: number;
  total: number;
  percent: number;
  db_skins_rows?: number;
  current_index?: number;
  current_skin?: string | null;
};

export default function Parsing() {
  const [status, setStatus] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(() => {
    fetch("/api/pars/status")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then(setStatus)
      .catch(() => setErr("Нет статуса"));
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 1500);
    return () => window.clearInterval(id);
  }, [refresh]);

  const start = () => {
    setErr(null);
    fetch("/api/pars/start", { method: "POST" })
      .then((r) => {
        if (r.status === 409) throw new Error("Уже идёт");
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then(() => refresh())
      .catch((e: Error) => setErr(e.message));
  };

  const stop = () => {
    setErr(null);
    fetch("/api/pars/stop", { method: "POST" })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then(() => refresh())
      .catch(() => setErr("Стоп: ошибка"));
  };

  const pct =
    status && status.total > 0
      ? Math.min(100, (status.html_count / status.total) * 100)
      : 0;

  return (
    <main className="page">
      <h1>Парс</h1>
      <div className="panel">
        <div className="row">
          <button
            type="button"
            className="primary"
            onClick={start}
            disabled={status?.running === true}
          >
            Старт
          </button>
          <button
            type="button"
            className="danger"
            onClick={stop}
            disabled={status?.running !== true}
          >
            Стоп
          </button>
        </div>
        {err ? <p className="error-text">{err}</p> : null}
        <div className="progress-wrap">
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <p className="meta">
            {status ? (
              <>
                HTML на диске: {status.html_count}/{status.total} (
                {status.percent}%)
                {status.running ? " · идёт" : ""}
                <br />
                строк в БД skins: {status.db_skins_rows ?? 0}
                {status.running &&
                status.current_skin != null &&
                status.current_skin !== "" &&
                typeof status.current_index === "number" ? (
                  <>
                    <br />
                    сейчас в очереди URL: {status.current_index}/
                    {status.total} · {status.current_skin}
                  </>
                ) : null}
              </>
            ) : (
              "…"
            )}
          </p>
        </div>
      </div>
    </main>
  );
}
