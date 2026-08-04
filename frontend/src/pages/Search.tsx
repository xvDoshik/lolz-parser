import { useCallback, useEffect, useMemo, useState } from "react";

type SkinMatch = { skin_name: string; item_count: number };

type ItemHit = {
  item_id: string;
  url: string;
  skins: string[];
  brawl_level?: number | null;
  trophies?: number | null;
  brawlers?: number | null;
  legendary?: number | null;
  hypercharges?: number | null;
  price?: number | null;
  currency?: string | null;
};

type SortKey =
  | "item_id"
  | "trophies"
  | "price"
  | "brawl_level"
  | "brawlers"
  | "legendary"
  | "hypercharges";

type SortDir = "asc" | "desc";

function sortValue(it: ItemHit, key: SortKey): number | null {
  if (key === "item_id") {
    const n = parseInt(it.item_id, 10);
    return Number.isNaN(n) ? null : n;
  }
  const v = it[key];
  if (v == null || typeof v !== "number") return null;
  return v;
}

function cmpHit(a: ItemHit, b: ItemHit, key: SortKey, dir: SortDir): number {
  const av = sortValue(a, key);
  const bv = sortValue(b, key);
  if (av == null && bv == null) return 0;
  if (av == null) return 1;
  if (bv == null) return -1;
  const mul = dir === "asc" ? 1 : -1;
  return (av - bv) * mul;
}

function fmtNum(n: number | null | undefined) {
  if (n == null) return "—";
  return String(n);
}

function fmtPrice(p: number | null | undefined, cur: string | null | undefined) {
  if (p == null) return "—";
  const c = cur ? ` ${cur}` : "";
  return `${p.toFixed(2)}${c}`;
}

export default function Search() {
  const [q, setQ] = useState("");
  const [matches, setMatches] = useState<SkinMatch[]>([]);
  const [selectedSkins, setSelectedSkins] = useState<string[]>([]);
  const [itemId, setItemId] = useState("");
  const [byItemSkins, setByItemSkins] = useState<string[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalItems, setModalItems] = useState<ItemHit[]>([]);
  const [modalErr, setModalErr] = useState<string | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("trophies");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sortedModalItems = useMemo(() => {
    if (modalItems.length === 0) return [];
    const arr = [...modalItems];
    arr.sort((a, b) => cmpHit(a, b, sortKey, sortDir));
    return arr;
  }, [modalItems, sortKey, sortDir]);

  const fetchSkins = useCallback((query: string) => {
    const url = new URL("/api/search/skins", window.location.origin);
    url.searchParams.set("q", query);
    fetch(url.toString())
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data: { matches: SkinMatch[] }) => {
        setMatches(data.matches);
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

  const onSortHeader = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "item_id" ? "asc" : "desc");
    }
  };

  const sortMark = (key: SortKey) =>
    sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  const findBySkins = () => {
    if (selectedSkins.length === 0) return;
    setModalErr(null);
    setModalLoading(true);
    setModalOpen(true);
    setModalItems([]);
    setSortKey("trophies");
    setSortDir("desc");
    fetch("/api/search/by-skins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skins: selectedSkins }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data: { items: ItemHit[] }) => {
        setModalItems(data.items);
        setModalLoading(false);
      })
      .catch(() => {
        setModalErr("Поиск не удался");
        setModalLoading(false);
      });
  };

  const searchByItem = () => {
    const id = itemId.trim();
    if (!id || !/^\d+$/.test(id)) {
      setByItemSkins([]);
      return;
    }
    const url = new URL("/api/search/by-item", window.location.origin);
    url.searchParams.set("id", id);
    fetch(url.toString())
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data: { skin_names: string[] }) => setByItemSkins(data.skin_names))
      .catch(() => setByItemSkins([]));
  };

  const closeModal = () => {
    setModalOpen(false);
    setModalErr(null);
    setModalItems([]);
  };

  return (
    <main className="page">
      <h1>Поиск</h1>

      <div className="panel">
        <p className="meta" style={{ marginTop: 0 }}>
          Фильтр · чек · Найти
        </p>
        <div className="row" style={{ marginBottom: "0.75rem" }}>
          <input
            type="search"
            placeholder="Имя…"
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

        <div className="row" style={{ marginTop: "0.75rem" }}>
          <button
            type="button"
            className="primary"
            disabled={selectedSkins.length === 0}
            onClick={findBySkins}
          >
            Найти
          </button>
        </div>

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
        {loadErr ? <p className="error-text">{loadErr}</p> : null}
      </div>

      <div className="panel">
        <h2 style={{ margin: "0 0 1rem", fontSize: "1.1rem" }}>По ID</h2>
        <div className="row">
          <input
            type="text"
            inputMode="numeric"
            placeholder="ID"
            value={itemId}
            onChange={(e) => setItemId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && searchByItem()}
          />
          <button type="button" className="primary" onClick={searchByItem}>
            Скины
          </button>
        </div>
        {byItemSkins.length > 0 ? (
          <ul className="result-list">
            {byItemSkins.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        ) : itemId.trim() ? (
          <p className="meta" style={{ marginTop: "0.75rem" }}>
            Пусто
          </p>
        ) : null}
      </div>

      {modalOpen ? (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(e) => e.target === e.currentTarget && closeModal()}
        >
          <div
            className="modal-panel modal-panel--wide"
            role="dialog"
            aria-modal="true"
          >
            <div className="modal-head">
              <h2 className="modal-title">Лоты</h2>
              <button
                type="button"
                className="modal-close"
                aria-label="Закрыть"
                onClick={closeModal}
              >
                ×
              </button>
            </div>
            {modalLoading ? (
              <p className="meta">…</p>
            ) : modalErr ? (
              <p className="error-text">{modalErr}</p>
            ) : modalItems.length === 0 ? (
              <p className="meta">Нет</p>
            ) : (
              <div className="modal-table-wrap">
                <table className="modal-hit-table">
                  <thead>
                    <tr>
                      <th>
                        <button
                          type="button"
                          className={`sort-th${sortKey === "item_id" ? " sort-th--active" : ""}`}
                          onClick={() => onSortHeader("item_id")}
                        >
                          id{sortMark("item_id")}
                        </button>
                      </th>
                      <th>скины</th>
                      <th className="cell-num">
                        <button
                          type="button"
                          className={`sort-th${sortKey === "trophies" ? " sort-th--active" : ""}`}
                          onClick={() => onSortHeader("trophies")}
                        >
                          кубки{sortMark("trophies")}
                        </button>
                      </th>
                      <th className="cell-num">
                        <button
                          type="button"
                          className={`sort-th${sortKey === "price" ? " sort-th--active" : ""}`}
                          onClick={() => onSortHeader("price")}
                        >
                          цена{sortMark("price")}
                        </button>
                      </th>
                      <th className="cell-num">
                        <button
                          type="button"
                          className={`sort-th${sortKey === "brawl_level" ? " sort-th--active" : ""}`}
                          onClick={() => onSortHeader("brawl_level")}
                        >
                          lvl{sortMark("brawl_level")}
                        </button>
                      </th>
                      <th className="cell-num">
                        <button
                          type="button"
                          className={`sort-th${sortKey === "brawlers" ? " sort-th--active" : ""}`}
                          onClick={() => onSortHeader("brawlers")}
                        >
                          б{sortMark("brawlers")}
                        </button>
                      </th>
                      <th className="cell-num">
                        <button
                          type="button"
                          className={`sort-th${sortKey === "legendary" ? " sort-th--active" : ""}`}
                          onClick={() => onSortHeader("legendary")}
                        >
                          лег{sortMark("legendary")}
                        </button>
                      </th>
                      <th className="cell-num">
                        <button
                          type="button"
                          className={`sort-th${sortKey === "hypercharges" ? " sort-th--active" : ""}`}
                          onClick={() => onSortHeader("hypercharges")}
                        >
                          гз{sortMark("hypercharges")}
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedModalItems.map((it) => (
                      <tr key={it.item_id}>
                        <td className="cell-mono">
                          <a
                            href={it.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {it.item_id}
                          </a>
                        </td>
                        <td>
                          <div className="modal-hit-skins">
                            {it.skins.map((sk) => (
                              <span key={sk} className="skin-tag">
                                {sk}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="cell-num">{fmtNum(it.trophies)}</td>
                        <td className="cell-num">
                          {fmtPrice(it.price, it.currency)}
                        </td>
                        <td className="cell-num">{fmtNum(it.brawl_level)}</td>
                        <td className="cell-num">{fmtNum(it.brawlers)}</td>
                        <td className="cell-num">{fmtNum(it.legendary)}</td>
                        <td className="cell-num">{fmtNum(it.hypercharges)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </main>
  );
}
