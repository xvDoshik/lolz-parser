import { useCallback, useEffect, useState } from "react";

type Item = {
  item_id: string;
  url: string;
  price: number;
  currency: string | null;
  brawl_level: number | null;
  trophies: number | null;
  brawlers: number | null;
  legendary: number | null;
  hypercharges: number | null;
  skin_tags: number;
  value_numerator: number;
  score: number;
  score_v1: number;
  lvl_weight: number;
};

type Payload = { items: Item[] };

function fmtNum(n: number | null | undefined) {
  if (n == null) return "—";
  return String(n);
}

function fmtPrice(p: number, cur: string | null | undefined) {
  const c = cur ? ` ${cur}` : "";
  return `${Number(p).toFixed(2)}${c}`;
}

export default function Optimized() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetch("/api/optimize/top?limit=120")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((j: Payload) => {
        setData(j);
        setErr(null);
      })
      .catch(() => setErr("Нет данных"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="page page-db">
      <h1>Opt</h1>
      <div className="row" style={{ marginBottom: "0.75rem" }}>
        <button type="button" className="primary" onClick={load} disabled={loading}>
          Обновить
        </button>
      </div>
      {err ? <p className="error-text">{err}</p> : null}

      {data && data.items.length === 0 ? (
        <p className="meta">Пусто — нужны price в item_brawl_stats (краул).</p>
      ) : null}

      {data && data.items.length > 0 ? (
        <section className="panel db-panel">
          <div className="db-table-wrap db-table-wrap-tall">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>score</th>
                  <th>v1</th>
                  <th>w</th>
                  <th>num</th>
                  <th>$</th>
                  <th>lvl</th>
                  <th>куб</th>
                  <th>б</th>
                  <th>лег</th>
                  <th>гз</th>
                  <th>ск</th>
                  <th>id</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((it, i) => (
                  <tr key={it.item_id}>
                    <td className="cell-num">{i + 1}</td>
                    <td className="cell-num cell-tight">{it.score}</td>
                    <td className="cell-num cell-tight">{it.score_v1}</td>
                    <td className="cell-num cell-tight">{it.lvl_weight}</td>
                    <td className="cell-num">{it.value_numerator}</td>
                    <td className="cell-num">{fmtPrice(it.price, it.currency)}</td>
                    <td className="cell-num">{fmtNum(it.brawl_level)}</td>
                    <td className="cell-num">{fmtNum(it.trophies)}</td>
                    <td className="cell-num">{fmtNum(it.brawlers)}</td>
                    <td className="cell-num">{fmtNum(it.legendary)}</td>
                    <td className="cell-num">{fmtNum(it.hypercharges)}</td>
                    <td className="cell-num">{it.skin_tags}</td>
                    <td className="cell-mono cell-tight">
                      <a href={it.url} target="_blank" rel="noreferrer">
                        {it.item_id}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </main>
  );
}
