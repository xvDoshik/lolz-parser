import { useCallback, useState } from "react";

type SellTexts = {
  title: string;
  description: string;
  title_en: string;
  description_en: string;
  title_de: string;
  description_de: string;
};

type ComposePayload = SellTexts & {
  item_id: string;
  url: string;
};

type LocaleCol = {
  badge: string;
  titleLabel: string;
  descLabel: string;
  title: string;
  description: string;
  flashTitle: string;
  flashDesc: string;
};

function IconCopy() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

function normalizeItemId(raw: string): string {
  const s = raw.trim();
  const m = s.match(/lzt\.market\/(\d+)/i);
  if (m) return m[1];
  return s.replace(/\D/g, "");
}

function toColumns(p: SellTexts): LocaleCol[] {
  return [
    {
      badge: "RU",
      titleLabel: "Название",
      descLabel: "Описание",
      title: p.title,
      description: p.description,
      flashTitle: "ru-title",
      flashDesc: "ru-desc",
    },
    {
      badge: "EN",
      titleLabel: "Title",
      descLabel: "Description",
      title: p.title_en,
      description: p.description_en,
      flashTitle: "en-title",
      flashDesc: "en-desc",
    },
    {
      badge: "DE",
      titleLabel: "Titel",
      descLabel: "Beschreibung",
      title: p.title_de,
      description: p.description_de,
      flashTitle: "de-title",
      flashDesc: "de-desc",
    },
  ];
}

export default function Sell() {
  const [itemId, setItemId] = useState("");
  const [texts, setTexts] = useState<SellTexts | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const compose = useCallback(() => {
    const id = itemId.trim();
    setErr(null);
    setTexts(null);
    if (!id) {
      setErr("Введите ID лота (только цифры).");
      return;
    }
    if (!/^\d+$/.test(id)) {
      setErr("ID должен быть числом, как на lzt.market.");
      return;
    }
    setLoading(true);
    fetch(`/api/sell/compose?id=${encodeURIComponent(id)}`)
      .then(async (r) => {
        if (r.status === 404) {
          const j = await r.json().catch(() => ({}));
          const d = (j as { detail?: unknown }).detail;
          throw new Error(typeof d === "string" ? d : "Лот не найден в БД");
        }
        if (!r.ok) throw new Error(`Ошибка ${r.status}`);
        return r.json() as Promise<ComposePayload>;
      })
      .then((p) => {
        setTexts({
          title: p.title,
          description: p.description,
          title_en: p.title_en,
          description_en: p.description_en,
          title_de: p.title_de,
          description_de: p.description_de,
        });
      })
      .catch((e: Error) => setErr(e.message || "Не удалось составить"))
      .finally(() => setLoading(false));
  }, [itemId]);

  const onCopy = (flashKey: string, text: string) => {
    void copyText(text).then((ok) => {
      if (ok) {
        setFlash(flashKey);
        window.setTimeout(() => setFlash(null), 1400);
      }
    });
  };

  const hasResult = texts !== null;
  const cols = texts ? toColumns(texts) : [];

  return (
    <main className="page page-db sell-page">
      <h1>Sell</h1>
      <section className="panel">
        <div className="row" style={{ flexWrap: "wrap", alignItems: "stretch" }}>
          <label className="sell-id-label">
            <span className="sell-id-caption">ID лота</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="ID или ссылка lzt.market/…"
              value={itemId}
              onChange={(e) => setItemId(normalizeItemId(e.target.value))}
              onPaste={(e) => {
                const t = e.clipboardData.getData("text");
                const id = normalizeItemId(t);
                if (id) {
                  e.preventDefault();
                  setItemId(id);
                }
              }}
              autoComplete="off"
            />
          </label>
          <button type="button" className="primary" onClick={compose} disabled={loading}>
            {loading ? "…" : "Составить"}
          </button>
        </div>
        {err ? <p className="error-text">{err}</p> : null}
      </section>

      {hasResult ? (
        <div className="sell-locales">
          {cols.map((c) => (
            <div key={c.badge} className="sell-locale-col">
              <p className="sell-lang-badge">{c.badge}</p>
              <article className="sell-card sell-card--compact">
                <div className="sell-card-head">
                  <h2 className="sell-card-title">{c.titleLabel}</h2>
                  <button
                    type="button"
                    className="sell-copy-btn"
                    title="Copy"
                    aria-label={`Copy ${c.badge} title`}
                    onClick={() => onCopy(c.flashTitle, c.title)}
                  >
                    <IconCopy />
                  </button>
                </div>
                <pre className="sell-card-body">{c.title}</pre>
                {flash === c.flashTitle ? (
                  <p className="sell-copied">Скопировано</p>
                ) : null}
              </article>
              <article className="sell-card sell-card--compact">
                <div className="sell-card-head">
                  <h2 className="sell-card-title">{c.descLabel}</h2>
                  <button
                    type="button"
                    className="sell-copy-btn"
                    title="Copy"
                    aria-label={`Copy ${c.badge} description`}
                    onClick={() => onCopy(c.flashDesc, c.description)}
                  >
                    <IconCopy />
                  </button>
                </div>
                <pre className="sell-card-body sell-card-body-tall">{c.description}</pre>
                {flash === c.flashDesc ? (
                  <p className="sell-copied">Скопировано</p>
                ) : null}
              </article>
            </div>
          ))}
        </div>
      ) : null}
    </main>
  );
}
