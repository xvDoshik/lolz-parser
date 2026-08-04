import { useCallback, useEffect, useState } from "react";

type SkinMatch = { skin_name: string; item_count: number };

type RuleState = {
  localId: string;
  skins: string[];
  skinsOpen: boolean;
  priceMin: string;
  priceMax: string;
  trophiesMin: string;
  trophiesMax: string;
  lvlMin: string;
  lvlMax: string;
};

type ApiRule = {
  skins: string[];
  price_min: number | null;
  price_max: number | null;
  trophies_min: number | null;
  trophies_max: number | null;
  brawl_level_min: number | null;
  brawl_level_max: number | null;
  baseline_score?: number | null;
  baseline_item_id?: string | null;
};

function newRule(): RuleState {
  return {
    localId: crypto.randomUUID(),
    skins: [],
    skinsOpen: true,
    priceMin: "",
    priceMax: "",
    trophiesMin: "",
    trophiesMax: "",
    lvlMin: "",
    lvlMax: "",
  };
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

function apiRuleToState(r: ApiRule): RuleState {
  const fmt = (v: number | null | undefined) =>
    v == null || v === undefined ? "" : String(v);
  return {
    localId: crypto.randomUUID(),
    skins: [...(r.skins || [])],
    skinsOpen: true,
    priceMin: fmt(r.price_min),
    priceMax: fmt(r.price_max),
    trophiesMin: fmt(r.trophies_min),
    trophiesMax: fmt(r.trophies_max),
    lvlMin: fmt(r.brawl_level_min),
    lvlMax: fmt(r.brawl_level_max),
  };
}

export default function Notification() {
  const [token, setToken] = useState("");
  const [chatIds, setChatIds] = useState("");
  const [intervalSec, setIntervalSec] = useState(60);
  const [rules, setRules] = useState<RuleState[]>(() => [newRule()]);
  const [q, setQ] = useState("");
  const [matches, setMatches] = useState<SkinMatch[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [saveOk, setSaveOk] = useState(false);
  const [loadingCfg, setLoadingCfg] = useState(true);
  const [saving, setSaving] = useState(false);

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

  useEffect(() => {
    setLoadingCfg(true);
    fetch("/api/notify/config")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then(
        (d: {
          telegram_bot_token?: string;
          telegram_chat_ids?: string;
          interval_sec?: number;
          rules?: ApiRule[];
        }) => {
          setToken(d.telegram_bot_token || "");
          setChatIds(d.telegram_chat_ids || "");
          setIntervalSec(
            Math.max(5, Math.min(3000, Number(d.interval_sec) || 60)),
          );
          const rs = d.rules;
          if (rs && rs.length > 0) {
            setRules(rs.map(apiRuleToState));
          } else {
            setRules([newRule()]);
          }
          setLoadErr(null);
        },
      )
      .catch(() => setLoadErr("Не удалось загрузить настройки"))
      .finally(() => setLoadingCfg(false));
  }, []);

  const setRule = (localId: string, patch: Partial<RuleState>) => {
    setRules((prev) =>
      prev.map((r) => (r.localId === localId ? { ...r, ...patch } : r)),
    );
  };

  const toggleSkin = (localId: string, name: string, checked: boolean) => {
    setRules((prev) =>
      prev.map((r) => {
        if (r.localId !== localId) return r;
        if (checked) {
          if (r.skins.includes(name)) return r;
          return { ...r, skins: [...r.skins, name] };
        }
        return { ...r, skins: r.skins.filter((s) => s !== name) };
      }),
    );
  };

  const removeSkin = (localId: string, name: string) => {
    setRules((prev) =>
      prev.map((r) =>
        r.localId === localId
          ? { ...r, skins: r.skins.filter((s) => s !== name) }
          : r,
      ),
    );
  };

  const addRule = () => {
    setRules((prev) => [...prev, newRule()]);
  };

  const removeRule = (localId: string) => {
    setRules((prev) =>
      prev.length <= 1 ? prev : prev.filter((r) => r.localId !== localId),
    );
  };

  const buildRulePayload = (r: RuleState) => {
    const body: Record<string, unknown> = { skins: r.skins };
    const pmin = parseFloatOpt(r.priceMin);
    const pmax = parseFloatOpt(r.priceMax);
    const tmin = parseIntOpt(r.trophiesMin);
    const tmax = parseIntOpt(r.trophiesMax);
    const lmin = parseIntOpt(r.lvlMin);
    const lmax = parseIntOpt(r.lvlMax);
    if (pmin !== undefined) body.price_min = pmin;
    if (pmax !== undefined) body.price_max = pmax;
    if (tmin !== undefined) body.trophies_min = tmin;
    if (tmax !== undefined) body.trophies_max = tmax;
    if (lmin !== undefined) body.brawl_level_min = lmin;
    if (lmax !== undefined) body.brawl_level_max = lmax;
    return body;
  };

  const save = () => {
    setSaveErr(null);
    setSaveOk(false);
    setSaving(true);
    const payload = {
      telegram_bot_token: token.trim(),
      telegram_chat_ids: chatIds.trim(),
      interval_sec: intervalSec,
      rules: rules.map(buildRulePayload),
    };
    fetch("/api/notify/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
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
        return r.json() as Promise<{
          ok: boolean;
          config: {
            telegram_bot_token?: string;
            telegram_chat_ids?: string;
            interval_sec?: number;
            rules?: ApiRule[];
          };
        }>;
      })
      .then((res) => {
        const c = res.config;
        if (c.telegram_bot_token != null) setToken(c.telegram_bot_token);
        if (c.telegram_chat_ids != null) setChatIds(c.telegram_chat_ids);
        if (c.interval_sec != null) {
          setIntervalSec(
            Math.max(5, Math.min(3000, Number(c.interval_sec) || 60)),
          );
        }
        if (c.rules && c.rules.length > 0) {
          setRules(c.rules.map(apiRuleToState));
        }
        setSaveOk(true);
      })
      .catch((e: Error) => setSaveErr(e.message || "Ошибка сохранения"))
      .finally(() => setSaving(false));
  };

  return (
    <main className="page page-db">
      <h1>Уведомления</h1>
      <section className="panel">
        <p className="meta" style={{ marginTop: 0 }}>
          Токен бота и chat id (можно несколько через запятую). Фильтры как в
          OptPrm: в топ попадают только лоты со <strong>всеми</strong> выбранными
          скинами. При <strong>Сохранить</strong> для каждого фильтра
          запоминается текущий лучший score; если позже появится лот с большим
          score — в Telegram уйдёт сообщение со ссылкой на lzt, ценой и
          текстами как в Sell.
        </p>

        <div className="notify-interval-block">
          <label className="notify-interval-label">
            Проверка каждые{" "}
            <strong>{intervalSec}</strong> с (от 5 до 3000)
          </label>
          <input
            type="range"
            className="notify-interval-range"
            min={5}
            max={3000}
            step={1}
            value={intervalSec}
            onChange={(e) =>
              setIntervalSec(Number(e.target.value) || 5)
            }
          />
        </div>

        <label className="notify-field">
          <span>Telegram bot token</span>
          <input
            className="notify-sensitive"
            type="text"
            autoComplete="off"
            spellCheck={false}
            placeholder="123456:ABC…"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </label>
        <label className="notify-field">
          <span>User / chat id (через запятую)</span>
          <input
            className="notify-sensitive"
            type="text"
            autoComplete="off"
            spellCheck={false}
            placeholder="123456789, -1001234567890"
            value={chatIds}
            onChange={(e) => setChatIds(e.target.value)}
          />
        </label>

        {loadingCfg ? (
          <p className="meta">Загрузка…</p>
        ) : null}
        {loadErr ? <p className="error-text">{loadErr}</p> : null}
      </section>

      {rules.map((rule, ruleIdx) => (
        <section className="panel notify-rule-panel" key={rule.localId}>
          <div className="notify-rule-head">
            <h2 className="notify-rule-title">Фильтр {ruleIdx + 1}</h2>
            {rules.length > 1 ? (
              <button
                type="button"
                className="notify-remove-rule"
                onClick={() => removeRule(rule.localId)}
              >
                Удалить фильтр
              </button>
            ) : null}
          </div>
          <p className="meta" style={{ marginTop: 0 }}>
            Скины (все должны быть на аккаунте). Пустые поля цены / кубков /
            уровня не ограничивают.
          </p>
          <div className="row" style={{ marginBottom: "0.75rem" }}>
            <input
              type="search"
              placeholder="Имя скина…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>

          {rule.skins.length > 0 ? (
            <div className="chip-bar">
              {rule.skins.map((s) => (
                <span key={s} className="chip">
                  <span className="chip-label">{s}</span>
                  <button
                    type="button"
                    className="chip-remove"
                    aria-label={`Убрать ${s}`}
                    onClick={() => removeSkin(rule.localId, s)}
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
              onClick={() =>
                setRule(rule.localId, { skinsOpen: !rule.skinsOpen })
              }
              aria-expanded={rule.skinsOpen}
            >
              {rule.skinsOpen
                ? "▼ Скрыть список скинов"
                : "▶ Показать список скинов"}
            </button>
          </div>

          {rule.skinsOpen ? (
            <div className="skin-check-list">
              {matches.map((m) => (
                <label key={m.skin_name} className="skin-check-row">
                  <input
                    type="checkbox"
                    checked={rule.skins.includes(m.skin_name)}
                    onChange={(e) =>
                      toggleSkin(rule.localId, m.skin_name, e.target.checked)
                    }
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
                value={rule.priceMin}
                onChange={(e) =>
                  setRule(rule.localId, { priceMin: e.target.value })
                }
              />
            </label>
            <label className="optprm-filter-cell">
              <span>Цена до ($)</span>
              <input
                type="text"
                inputMode="decimal"
                placeholder="—"
                value={rule.priceMax}
                onChange={(e) =>
                  setRule(rule.localId, { priceMax: e.target.value })
                }
              />
            </label>
            <label className="optprm-filter-cell">
              <span>Кубки от</span>
              <input
                type="text"
                inputMode="numeric"
                placeholder="—"
                value={rule.trophiesMin}
                onChange={(e) =>
                  setRule(rule.localId, { trophiesMin: e.target.value })
                }
              />
            </label>
            <label className="optprm-filter-cell">
              <span>Кубки до</span>
              <input
                type="text"
                inputMode="numeric"
                placeholder="—"
                value={rule.trophiesMax}
                onChange={(e) =>
                  setRule(rule.localId, { trophiesMax: e.target.value })
                }
              />
            </label>
            <label className="optprm-filter-cell">
              <span>Ур. от</span>
              <input
                type="text"
                inputMode="numeric"
                placeholder="—"
                value={rule.lvlMin}
                onChange={(e) =>
                  setRule(rule.localId, { lvlMin: e.target.value })
                }
              />
            </label>
            <label className="optprm-filter-cell">
              <span>Ур. до</span>
              <input
                type="text"
                inputMode="numeric"
                placeholder="—"
                value={rule.lvlMax}
                onChange={(e) =>
                  setRule(rule.localId, { lvlMax: e.target.value })
                }
              />
            </label>
          </div>
        </section>
      ))}

      <section className="panel">
        <div className="row" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
          <button
            type="button"
            className="primary"
            disabled={saving}
            onClick={save}
          >
            {saving ? "…" : "Сохранить"}
          </button>
          <button type="button" onClick={addRule} disabled={saving}>
            Добавить фильтр
          </button>
        </div>
        {saveErr ? <p className="error-text">{saveErr}</p> : null}
        {saveOk ? (
          <p className="meta" style={{ marginTop: "0.75rem" }}>
            Сохранено. Бейзлайн для каждого фильтра сброшен на текущий лучший лот;
            дальше проверка по интервалу выше.
          </p>
        ) : null}
      </section>
    </main>
  );
}
