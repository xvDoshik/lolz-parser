import { useCallback, useEffect, useRef, useState } from "react";

type SkinRow = {
  skin_name: string;
  url: string;
  item_count: number;
  fetched_at: string;
  error: string | null;
};

type SkinItemRow = {
  skin_name: string;
  item_id: string;
  brawl_level: number | null;
  trophies: number | null;
  brawlers: number | null;
  legendary: number | null;
  hypercharges: number | null;
  price: number | null;
  currency: string | null;
};

type Snapshot = {
  server_time: string;
  skins: SkinRow[];
  skin_items: SkinItemRow[];
  skin_items_total: number;
  skin_items_truncated: boolean;
};

function fmtNum(n: number | null | undefined) {
  if (n == null) return "—";
  return String(n);
}

function fmtPrice(p: number | null | undefined, cur: string | null | undefined) {
  if (p == null) return "—";
  const c = cur ? ` ${cur}` : "";
  return `${p.toFixed(2)}${c}`;
}

function fmtTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export default function Db() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const snapshotInflight = useRef(false);

  const refresh = useCallback(() => {
    if (snapshotInflight.current) return;
    snapshotInflight.current = true;
    fetch("/api/db/snapshot")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data: Snapshot) => {
        setSnap(data);
        setErr(null);
      })
      .catch(() => setErr("Снимок не загрузился"))
      .finally(() => {
        snapshotInflight.current = false;
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 5000);
    return () => window.clearInterval(id);
  }, [refresh]);

  return (
    <main className="page page-db">
      <h1>БД</h1>
      <p className="meta db-intro">
        5 с
        {snap ? (
          <>
            {" · "}
            {fmtTime(snap.server_time)} · skins {snap.skins.length} · items{" "}
            {snap.skin_items_total}
            {snap.skin_items_truncated
              ? ` · ≤${snap.skin_items.length} в таблице ниже`
              : ""}
          </>
        ) : null}
        {loading && snap === null ? " · …" : null}
      </p>
      {err && <p className="error-text">{err}</p>}

      <section className="panel db-panel">
        <h2 className="db-h2">skins</h2>
        <div className="db-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>skin_name</th>
                <th>item_count</th>
                <th>fetched_at</th>
                <th>error</th>
                <th>url</th>
              </tr>
            </thead>
            <tbody>
              {(snap?.skins ?? []).map((r) => (
                <tr key={r.skin_name}>
                  <td className="cell-mono">{r.skin_name}</td>
                  <td className="cell-num">{r.item_count}</td>
                  <td className="cell-mono cell-tight">{r.fetched_at}</td>
                  <td className="cell-err">
                    {r.error ? (
                      <span title={r.error}>
                        {r.error.length > 120
                          ? `${r.error.slice(0, 120)}…`
                          : r.error}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="cell-url">
                    <a href={r.url} target="_blank" rel="noreferrer">
                      {r.url}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel db-panel">
        <h2 className="db-h2">skin_items</h2>
        {snap?.skin_items_truncated && (
          <p className="meta db-truncate-note">
            Лимит выборки · в БД {snap.skin_items_total}
          </p>
        )}
        <div className="db-table-wrap db-table-wrap-tall">
          <table className="data-table">
            <thead>
              <tr>
                <th>skin</th>
                <th>id</th>
                <th>lvl</th>
                <th>кубки</th>
                <th>б</th>
                <th>лег</th>
                <th>гз</th>
                <th>$</th>
                <th>lzt</th>
              </tr>
            </thead>
            <tbody>
              {(snap?.skin_items ?? []).map((r) => (
                <tr key={`${r.skin_name}:${r.item_id}`}>
                  <td className="cell-mono">{r.skin_name}</td>
                  <td className="cell-num">{r.item_id}</td>
                  <td className="cell-num">{fmtNum(r.brawl_level)}</td>
                  <td className="cell-num">{fmtNum(r.trophies)}</td>
                  <td className="cell-num">{fmtNum(r.brawlers)}</td>
                  <td className="cell-num">{fmtNum(r.legendary)}</td>
                  <td className="cell-num">{fmtNum(r.hypercharges)}</td>
                  <td className="cell-num cell-tight">
                    {fmtPrice(r.price, r.currency)}
                  </td>
                  <td>
                    <a
                      href={`https://lzt.market/${r.item_id}/`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      ↗
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
