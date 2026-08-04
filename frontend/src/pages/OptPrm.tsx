import { useCallback, useEffect, useState } from "react";

type SkinMatch = { skin_name: string; item_count: number };

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

function parseIntOpt(s: string): number | undefined {
  const t = s.trim();
  if (!t) return undefined;
  const n = parseInt(t, 10);
  return Number.isFinite(n) ? n : undefined;
}

function parseFloatOpt(s: string): number | undefined {
  const t = s.trim().replace(",", ".");
  if (!t) return undefined;
  const n = parseFloat(t);
  return Number.isFinite(n) ? n : undefined;
}

export default function OptPrm() {
  const [q, setQ] = useState("");
  const [matches, setMatches] = useState<SkinMatch[]>([]);
  const [selectedSkins, setSelectedSkins] = useState<string[]>([]);
  const [skinsOpen, setSkinsOpen] = useState(true);
  const [priceMin, setPriceMin] = useState("");
  const [priceMax, setPriceMax] = useState("");
  const [trophiesMin, setTrophiesMin] = useState("");
  const [trophiesMax, setTrophiesMax] = useState("");
  const [lvlMin, setLvlMin] = useState("");
  const [lvlMax, setLvlMax] = useState("");
  const [data, setData] = useState<Payload | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [optErr, setOptErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchSkins = useCallback((query: string) => {
    const url = new URL("/api/search/skins", window.location.origin);
    url.searchParams.set("q", query);
    fetch(url.toString())
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((d: { matches: SkinMatch[] }) => {
        setMatches(d.matches);
        setLoadErr(null);
      })
      .catch(() => setLoadErr("Список не загрузился"));
  }, []);

  useEffect(() => {
    const delay = q.trim() ? 320 : 0;
    const id = window.setTimeout(() => fetchSkins(q), delay);
    return () => window.clearTimeout(id);
  }, [q, fetchSkins]);

  const toggleSkin = (name: string, checked: boolean) => {
    setSelectedSkins((prev) => {
      if (checked) {
        if (prev.includes(name)) return prev;
        return [...prev, name];
      }
      return prev.filter((s) => s !== name);
    });
  };

  const removeSkin = (name: string) => {
    setSelectedSkins((prev) => prev.filter((s) => s !== name));
  };

  const run = () => {
    if (selectedSkins.length === 0) return;
    setOptErr(null);
    setLoading(true);
    setData(null);
    const body: Record<string, unknown> = { skins: selectedSkins };
    const pmin = parseFloatOpt(priceMin);
    const pmax = parseFloatOpt(priceMax);
    const tmin = parseIntOpt(trophiesMin);
    const tmax = parseIntOpt(trophiesMax);
    const lmin = parseIntOpt(lvlMin);
    const lmax = parseIntOpt(lvlMax);
    if (pmin !== undefined) body.price_min = pmin;
    if (pmax !== undefined) body.price_max = pmax;
    if (tmin !== undefined) body.trophies_min = tmin;
    if (tmax !== undefined) body.trophies_max = tmax;
    if (lmin !== undefined) body.brawl_level_min = lmin;
    if (lmax !== undefined) body.brawl_level_max = lmax;

    fetch("/api/optimize/prm?limit=120", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(async (r) => {
        if (!r.ok) {
          let msg = String(r.status);
          try {
            const j = (await r.json()) as { detail?: unknown };
            if (typeof j.detail === "string") msg = j.detail;
          } catch {}
          throw new Error(msg);
        }
        return r.json() as Promise<Payload>;
      })
      .then(setData)
      .catch((e: Error) => setOptErr(e.message || "Ошибка"))
      .finally(() => setLoading(false));
  };

  return (
    <main className="page page-db">
      <h1>OptPrm</h1>
      <section className="panel">
        <p className="meta" style={{ marginTop: 0 }}>
          Выбери скины — в топ только лоты, у которых в базе есть <strong>все</strong> выбранные скины,
          с рейтингом как в Opt. Пустые поля фильтров не ограничивают.
        </p>
        <div className="row" style={{ marginBottom: "0.75rem" }}>
          <input
            type="search"
            placeholder="Имя скина…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        {selectedSkins.length > 0 ? (
          <div className="chip-bar">
            {selectedSkins.map((s) => (
              <span key={s} className="chip">
                <span className="chip-label">{s}</span>
                <button
                  type="button"
                  className="chip-remove"
                  aria-label={`Убрать ${s}`}
                  onClick={() => removeSkin(s)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <div className="optprm-skin-toolbar">
          <button
            type="button"
            className="optprm-toggle"
            onClick={() => setSkinsOpen((o) => !o)}
            aria-expanded={skinsOpen}
          >
            {skinsOpen ? "▼ Скрыть список скинов" : "▶ Показать список скинов"}
          </button>
        </div>

        {skinsOpen ? (
          <div className="skin-check-list">
            {matches.map((m) => (
              <label key={m.skin_name} className="skin-check-row">
                <input
                  type="checkbox"
                  checked={selectedSkins.includes(m.skin_name)}
                  onChange={(e) => toggleSkin(m.skin_name, e.target.checked)}
                />
                <span className="skin-check-name">{m.skin_name}</span>
                <span className="skin-check-meta">{m.item_count}</span>
              </label>
            ))}
          </div>
        ) : null}

        <div className="optprm-filters">
          <label className="optprm-filter-cell">
            <span>Цена от ($)</span>
            <input
              type="text"
              inputMode="decimal"
              placeholder="—"
              value={priceMin}
              onChange={(e) => setPriceMin(e.target.value)}
            />
          </label>
          <label className="optprm-filter-cell">
            <span>Цена до ($)</span>
            <input
              type="text"
              inputMode="decimal"
              placeholder="—"
              value={priceMax}
              onChange={(e) => setPriceMax(e.target.value)}
            />
          </label>
          <label className="optprm-filter-cell">
            <span>Кубки от</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="—"
              value={trophiesMin}
              onChange={(e) => setTrophiesMin(e.target.value)}
            />
          </label>
          <label className="optprm-filter-cell">
            <span>Кубки до</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="—"
              value={trophiesMax}
              onChange={(e) => setTrophiesMax(e.target.value)}
            />
          </label>
          <label className="optprm-filter-cell">
            <span>Ур. от</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="—"
              value={lvlMin}
              onChange={(e) => setLvlMin(e.target.value)}
            />
          </label>
          <label className="optprm-filter-cell">
            <span>Ур. до</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="—"
              value={lvlMax}
              onChange={(e) => setLvlMax(e.target.value)}
            />
          </label>
        </div>

        <div className="row" style={{ marginTop: "0.75rem" }}>
          <button
            type="button"
            className="primary"
            disabled={selectedSkins.length === 0 || loading}
            onClick={run}
          >
            {loading ? "…" : "Подобрать"}
          </button>
        </div>
        {loadErr ? <p className="error-text">{loadErr}</p> : null}
        {optErr ? <p className="error-text">{optErr}</p> : null}
      </section>

      {data && data.items.length === 0 ? (
        <p className="meta">
          Нет лотов под критерии (скины + цена/кубки/lvl в БД). Ослабь фильтры или набор скинов.
        </p>
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
