# TradingView Market-Intelligence Integration — Implementation Plan

สถานะ: Ready for implementation (ยังไม่เริ่ม)
เป้าหมาย: เพิ่มความสามารถดึงข้อมูล technical rating จาก TradingView เข้ามาใน MindMesh
เอกสารอ้างอิง: `docs/PRODUCT_PLAN.md`, `docs/EXECUTION_PLAN.md`

> เอกสารนี้เขียนให้ AI coding agent อีกตัวหนึ่งที่ไม่มี context เดิมสามารถอ่านแล้ว implement ต่อได้ทันที ทุก path เป็น absolute reference จาก repo root (`/Users/codex074/Desktop/personal-llm/MindMesh`)

## Context

MindMesh เป็น FastAPI app ที่แสดงข้อมูลตลาดจาก `yfinance` พร้อมฟีเจอร์วิเคราะห์ด้วย AI แบบ BYOK (bring-your-own-key) หลาย provider เจ้าของโปรเจกต์ต้องการเพิ่มความสามารถดึงข้อมูลจาก TradingView เข้ามาในแอปโดยตรง (ไม่ใช่แค่ผ่าน MCP tool ที่ใช้คุยกับ Claude เท่านั้น)

**ทำไมไม่เรียกผ่าน MCP server:** MCP server (`tradingview-data`, ติดตั้งแยกไว้ใน Claude Code จาก github.com/atilaahmettaner/tradingview-mcp) เป็น protocol endpoint สำหรับ AI client คุยผ่าน stdio — การให้ FastAPI request handler ไป spawn/คุยกับ MCP server ตอน runtime จะช้า เปราะบาง และไม่ตรงกับสถาปัตยกรรมเดิมของแอปนี้เลย แผนนี้จึงเพิ่ม dependency ที่ MCP server ตัวนั้น wrap อยู่ภายใน (`tradingview-ta`, `tradingview-screener`) เข้ามาเป็น dependency ตรงของ MindMesh แทน — วิธีเดียวกัน แต่ native

**ข้อค้นพบสถาปัตยกรรมสำคัญ (ตรวจสอบกับซอร์สจริงของแพ็กเกจ `tradingview-ta==3.3.0` โดยการ `pip download` มาอ่านโดยตรง):** ไลบรารีสาธารณะของ TradingView **ไม่มี** historical OHLCV candle series ต่อ symbol ให้ — มีแค่ point-in-time technical-rating snapshot (RSI/MACD/moving-averages/overall BUY-SELL-NEUTRAL consensus ผ่าน `tradingview-ta`) และ cross-symbol screening (`tradingview-screener`) เท่านั้น ฟีเจอร์กราฟ/ประวัติราคาเดิมของ MindMesh (`app/market/module.py`'s `MarketDataService`, ใช้ `yfinance`) จะแทนที่ด้วย TradingView ไม่ได้โดยไม่ทำให้ chart data เพี้ยนแบบเงียบๆ — ซึ่งขัดกับข้อกำหนดเรื่อง data-provenance ของ repo นี้เอง (`docs/PRODUCT_PLAN.md` §9.4: ห้ามให้ข้อมูลที่ AI เห็นบิดเบือนแหล่งที่มา)

**ข้อสรุป:** นี่คือฟีเจอร์เสริม (additive) ไม่ใช่การสลับ provider `MarketDataService`, `MarketQuery.provider`, และ yfinance path เดิม **ห้ามแตะ** โมดูลใหม่แยกต่างหากจะแสดง TradingView's technical-rating consensus สำหรับ symbol ที่ผู้ใช้กำลังดูอยู่ ผ่าน route ใหม่และ UI card เล็กๆ — สอดคล้องกับ `docs/PRODUCT_PLAN.md` บรรทัด 130 ที่บอกไว้แล้วว่าควรสร้าง data-provider abstraction ก็ต่อเมื่อมี provider ตัวที่สองจริงๆ (ตอนนี้มีแล้ว)

แผนนี้ถูกออกแบบโดย Plan sub-agent แล้วตรวจสอบซ้ำกับ repo จริง (เลขบรรทัดที่อ้างถึงใน `dashboard.html`, `app.js`, `context.py`, adapter ทั้งสามไฟล์) และกับซอร์สจริงของ `tradingview-ta` (ยืนยันว่า `get_analysis()` return `None` ได้โดยไม่ raise, `add_indicators()` mutate class-level list ทั้งกระบวนการ — ห้ามเรียกใช้ — และ string constant ของ `RECOMMENDATION` ตรงตัว: `STRONG_BUY`/`BUY`/`NEUTRAL`/`SELL`/`STRONG_SELL`/`ERROR`)

---

## Phase 1 — TradingView technical snapshot (required)

### 1. Dependencies — `pyproject.toml`

ใน `[project] dependencies` (ปัจจุบันจบด้วย `"yfinance>=0.2.40",`) เพิ่ม:

```toml
    "tradingview-ta>=3.3.0",
    # Pinned exactly (not >=): 3.2.0 makes a bare Query() default to a stock
    # preset filter that silently returns 0 rows for crypto/futures scans.
    # Staged for a future screener follow-up; not imported by Phase 1 code.
    "tradingview-screener==3.0.0",
```

`tradingview-ta` ไม่ต้องใช้ API key และดึง `requests` เข้ามาเป็น transitive dependency ของตัวเองอยู่แล้ว — ไม่ต้องเพิ่มอะไรอีก

### 2. Config — `app/config.py` + `.env.example`

เพิ่มใน `Settings` frozen dataclass ใกล้ๆ field `market_timeout_seconds` เดิม:

```python
    market_tv_default_exchange: str
    market_tv_default_screener: str
    market_tv_timeout_seconds: int
    market_tv_cache_ttl_seconds: int
```

เพิ่มใน `get_settings()`:

```python
        market_tv_default_exchange=os.getenv("APP_MARKET_TV_DEFAULT_EXCHANGE", "NASDAQ"),
        market_tv_default_screener=os.getenv("APP_MARKET_TV_DEFAULT_SCREENER", "america"),
        market_tv_timeout_seconds=_as_int(os.getenv("APP_MARKET_TV_TIMEOUT_SECONDS"), 10),
        market_tv_cache_ttl_seconds=_as_int(os.getenv("APP_MARKET_TV_CACHE_TTL_SECONDS"), 120),
```

เพิ่มใน `.env.example` ต่อจากบรรทัด `APP_MARKET_CACHE_TTL_SECONDS=120` เดิม:

```
APP_MARKET_TV_DEFAULT_EXCHANGE=NASDAQ
APP_MARKET_TV_DEFAULT_SCREENER=america
APP_MARKET_TV_TIMEOUT_SECONDS=10
APP_MARKET_TV_CACHE_TTL_SECONDS=120
```

### 3. กลยุทธ์ resolve symbol → exchange/screener (ไม่ทำ auto-detection)

`TA_Handler` ต้องการ `exchange` (เช่น `"NASDAQ"`) และ `screener` (เช่น `"america"`) ซึ่ง ticker เปล่าๆ อย่าง `"AAPL"` ไม่มีข้อมูลนี้ ตามแนวทางเดิมของ repo ที่หลีกเลี่ยง premature abstraction: **ห้าม** สร้างระบบเดา exchange จาก symbol

- Route ใหม่รับ query param `exchange`/`screener`/`interval` แบบ optional, ค่า default มาจาก `settings.market_tv_default_exchange`/`market_tv_default_screener`/`"1d"`
- ตรวจสอบ `exchange`/`screener` ด้วย `^[A-Za-z0-9_]{1,20}$` ฝั่ง server ก่อนใช้งาน, reject ด้วย 422 (ตรงกับ convention เดิมของ repo)
- กรณี exchange/symbol ผิดคู่กัน ไลบรารีจะ raise exception ที่มีคำว่า `"not found"` → map เป็น `TradingViewSymbolNotFoundError` → 404 ส่วนกรณีอื่นๆ → `TradingViewTimeoutError` → 504
- **ห้าม** เอา `Period` (`1M`/`3M`/...) มาใช้แทน TradingView's `interval` — คนละแกนกัน (ความยาวย้อนหลัง vs. ความละเอียดแท่งเทียน) ให้รับ `interval` param แยกต่างหาก
- แถบ index-overview บน dashboard (`^GSPC`, `^IXIC` ฯลฯ ใน `app.js`) ไม่อยู่ในขอบเขตนี้ — ไม่มี mapping ที่สะอาดไปยัง TradingView ภายใต้กลยุทธ์ง่ายๆ นี้ card ใหม่จะแสดงเฉพาะ symbol ที่ผู้ใช้ค้นหาเท่านั้น

### 4. Models ใหม่ — เพิ่มต่อท้าย `app/market/models.py`

```python
class TechnicalRating(BaseModel):
    recommendation: str  # STRONG_BUY | BUY | NEUTRAL | SELL | STRONG_SELL | ERROR
    buy: int
    sell: int
    neutral: int


class TradingViewSnapshot(BaseModel):
    symbol: str
    exchange: str
    screener: str
    interval: str
    as_of: str
    summary: TechnicalRating
    oscillators: TechnicalRating
    moving_averages: TechnicalRating
    indicators: dict[str, float | int | str | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
```

`indicators` เป็น curated allowlist (ดูด้านล่าง) ไม่ใช่ raw dict จากไลบรารีโดยตรง

### 5. โมดูลใหม่ — `app/market/tradingview.py`

โมดูลแยกต่างหาก จงใจไม่ใช้ `MarketDataService`/`_TtlCache` ร่วมกัน (สองตัวนั้น type สำหรับ `MarketSnapshot`; การใช้ร่วมกันจะทำให้เส้นแบ่ง additive/non-replacement เบลอ)

```python
"""TradingView Technical Intelligence module (additive to app/market/module.py).

Wraps tradingview-ta's TA_Handler to surface TradingView's own rule-based
technical rating (RSI/MACD/moving-averages/overall BUY-SELL-NEUTRAL
consensus) for a single symbol. Not a replacement for the yfinance
market-data path in app/market/module.py: TradingView's public libraries do
not return a historical OHLCV series for one symbol, only point-in-time
indicator snapshots. No API key required.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from tradingview_ta import TA_Handler

from .models import TechnicalRating, TradingViewSnapshot


class TradingViewError(Exception):
    """Normalised, user-safe TradingView failure."""


class TradingViewSymbolNotFoundError(TradingViewError):
    pass


class TradingViewTimeoutError(TradingViewError):
    pass


# Curated allowlist of raw tradingview_ta indicator keys. Deliberately not the
# full Analysis.indicators dict, which is populated via a class-level mutation
# inside the library and can carry ~90 unreviewed fields.
_INDICATOR_ALLOWLIST = (
    "RSI", "MACD.macd", "MACD.signal", "SMA20", "SMA50", "SMA200",
    "EMA20", "BB.upper", "BB.lower", "close", "volume", "change",
)


class _TtlCache:
    """Keyed by (symbol, exchange, screener, interval). Not shared with
    app/market/module.py's cache — that one is typed for MarketSnapshot."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._store: dict[tuple[str, str, str, str], tuple[float, TradingViewSnapshot]] = {}

    def get(self, key):
        item = self._store.get(key)
        if item is None:
            return None
        inserted, snapshot = item
        if time.monotonic() - inserted > self._ttl:
            self._store.pop(key, None)
            return None
        return snapshot

    def put(self, key, snapshot) -> None:
        self._store[key] = (time.monotonic(), snapshot)


def _rating(block: dict) -> TechnicalRating:
    return TechnicalRating(
        recommendation=block.get("RECOMMENDATION", "ERROR"),
        buy=block.get("BUY", 0),
        sell=block.get("SELL", 0),
        neutral=block.get("NEUTRAL", 0),
    )


def _fetch_sync(symbol: str, exchange: str, screener: str, interval: str, timeout: int) -> TradingViewSnapshot:
    """Blocking — always invoke via asyncio.to_thread, never inline in an
    async def. TA_Handler.get_analysis() uses synchronous `requests`; calling
    it directly in an async handler would block the whole event loop,
    including any in-flight SSE analysis streams."""
    handler = TA_Handler(
        symbol=symbol,
        exchange=exchange,
        screener=screener,
        interval=interval,
        timeout=timeout,  # TA_Handler defaults to timeout=None (hangs forever) — always pass explicitly
    )
    try:
        analysis = handler.get_analysis()
    except Exception as exc:  # tradingview_ta raises bare Exception for all failures
        message = str(exc)
        if "not found" in message.lower():
            raise TradingViewSymbolNotFoundError(
                f"no TradingView analysis for {exchange}:{symbol} ({screener})"
            ) from exc
        raise TradingViewTimeoutError(f"TradingView provider error for {symbol}") from exc

    # get_analysis() can return None (not raise) when TradingView's core
    # Recommend.Other/Recommend.All columns come back null for this pair.
    # Verified directly against tradingview_ta 3.3.0 source (main.py calculate()).
    if analysis is None:
        raise TradingViewSymbolNotFoundError(
            f"no TradingView analysis for {exchange}:{symbol} ({screener})"
        )

    indicators = {k: analysis.indicators.get(k) for k in _INDICATOR_ALLOWLIST}

    return TradingViewSnapshot(
        symbol=symbol,
        exchange=exchange,
        screener=screener,
        interval=interval,
        as_of=datetime.now(timezone.utc).isoformat(),  # analysis.time is naive local time; don't use it
        summary=_rating(analysis.summary),
        oscillators=_rating(analysis.oscillators),
        moving_averages=_rating(analysis.moving_averages),
        indicators=indicators,
        warnings=[],
    )


_cache: _TtlCache | None = None


async def get_technical_snapshot(
    symbol: str,
    exchange: str,
    screener: str,
    interval: str = "1d",
) -> TradingViewSnapshot:
    """Module-level entrypoint; mirrors get_market_snapshot's lazy-default
    shape but stays fully independent of it."""
    global _cache
    from app.config import get_settings

    settings = get_settings()
    if _cache is None:
        _cache = _TtlCache(settings.market_tv_cache_ttl_seconds)

    symbol = symbol.strip().upper()
    exchange = exchange.strip().upper()
    screener = screener.strip().lower()
    key = (symbol, exchange, screener, interval)

    cached = _cache.get(key)
    if cached is not None:
        return cached

    snapshot = await asyncio.to_thread(
        _fetch_sync, symbol, exchange, screener, interval, settings.market_tv_timeout_seconds
    )
    _cache.put(key, snapshot)
    return snapshot
```

**ห้ามเรียก `TA_Handler.add_indicators()` เด็ดขาด** — ตรวจสอบกับซอร์ส 3.3.0 จริงแล้วว่า `self.indicators += indicators` mutate class-level list ที่ใช้ร่วมกัน (`indicators = TradingView.indicators.copy()` เป็น class attribute; `+=` ครั้งแรกบน instance ที่ยังไม่มี instance attribute ของตัวเองจะไป mutate ตัวกลาง) ทำให้ indicator ที่เพิ่มเองรั่วไปยัง `TA_Handler` ทุกตัวที่สร้างขึ้นหลังจากนั้นในกระบวนการเดียวกัน แผนนี้ใช้แค่ indicator ชุด default เท่านั้น จึงเป็นกับดักที่ต้องรู้ไว้ ไม่ใช่สิ่งที่ต้อง trigger

### 6. Route ใหม่ — `app/web/routes.py`

เพิ่มเข้าไปใน import block ของ market ที่มีอยู่แล้ว:

```python
from app.market.models import MarketQuery, Period, TradingViewSnapshot
from app.market.tradingview import (
    TradingViewSymbolNotFoundError,
    TradingViewTimeoutError,
    get_technical_snapshot,
)
```

Import `get_technical_snapshot` โดยตรง (ไม่ใช่เรียกผ่าน `app.market.tradingview.get_technical_snapshot` ตอน call) เพื่อให้ test สามารถ monkeypatch `app.web.routes.get_technical_snapshot` ได้ ตรงกับ pattern เดิมของ `get_market_snapshot` ใน `tests/test_web.py`

เพิ่มต่อจาก handler `market_data` เดิม (`app/web/routes.py`, ปัจจุบันบรรทัด 93-104):

```python
import re

_EXCHANGE_SCREENER_RE = re.compile(r"^[A-Za-z0-9_]{1,20}$")


@router.get("/api/market/{symbol}/technical")
async def market_technical(symbol: str, exchange: str | None = None, screener: str | None = None, interval: str = "1d"):
    settings = get_settings()
    resolved_exchange = (exchange or settings.market_tv_default_exchange).strip()
    resolved_screener = (screener or settings.market_tv_default_screener).strip()

    if not _EXCHANGE_SCREENER_RE.match(resolved_exchange) or not _EXCHANGE_SCREENER_RE.match(resolved_screener):
        return JSONResponse(status_code=422, content={"detail": "invalid exchange or screener"})

    try:
        snapshot = await get_technical_snapshot(symbol, resolved_exchange, resolved_screener, interval)
        return JSONResponse(content=snapshot.model_dump())
    except TradingViewSymbolNotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    except TradingViewTimeoutError as exc:
        return JSONResponse(status_code=504, content={"detail": str(exc)})
    except (ValueError, ValidationError) as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
```

รูปแบบ try/except/status-code เดียวกับ handler `market_data` เดิมทุกประการ — แค่เปลี่ยน exception class

### 7. UI — `app/web/templates/dashboard.html`

`#summary` ปิดที่บรรทัด 127, section ปิดที่บรรทัด 128-129 (ตรวจสอบแล้ว) แทรก card ใหม่ต่อจาก `#summary` ปิด:

```html
        <div id="summary" class="summary-cards" aria-live="polite">
          ...
        </div>

        <div id="tv-signal-card" class="tv-signal-card hidden" aria-live="polite"></div>
      </div>
    </section>
```

ใช้ utility class `.hidden { display: none; }` ที่มีอยู่แล้ว (นิยามที่ `app.css:101`) — **ห้าม** เพิ่ม rule `.tv-signal-card.hidden` ซ้ำซ้อน

### 8. UI — `app/web/static/app.js`

`loadMarket()` ปัจจุบันตั้งค่า `currentSnapshot`/`renderSnapshot`/`setMarketActionsEnabled` ที่บรรทัด 124-125 (ตรวจสอบแล้ว) เพิ่มเรียกต่อท้าย:

```javascript
    currentSnapshot = await response.json();
    renderSnapshot(currentSnapshot);
    setMarketActionsEnabled(true);
    loadTechnicalSignal(symbol);
```

ฟังก์ชันใหม่ (วางไว้ใกล้ `loadMarket` เช่นต่อท้ายเลย):

```javascript
async function loadTechnicalSignal(symbol) {
  const card = $('tv-signal-card');
  card.classList.add('hidden');
  try {
    const response = await fetch(`/api/market/${encodeURIComponent(symbol)}/technical`);
    if (!response.ok) {
      // Unknown exchange/symbol under the default mapping: degrade
      // gracefully. The rest of the dashboard must keep working.
      return;
    }
    renderTechnicalSignal(await response.json());
  } catch (error) {
    // Network failure: same graceful degradation.
  }
}

function renderTechnicalSignal(tv) {
  const card = $('tv-signal-card');
  const ratingClass = {
    STRONG_BUY: 'is-buy', BUY: 'is-buy',
    STRONG_SELL: 'is-sell', SELL: 'is-sell',
    NEUTRAL: 'is-neutral', ERROR: 'is-neutral',
  }[tv.summary.recommendation] || 'is-neutral';
  card.innerHTML = `
    <div class="tv-signal-header">
      <span class="metric-label">TradingView technical signal</span>
      <span class="tv-signal-badge ${ratingClass}">${escapeHtml(tv.summary.recommendation.replace('_', ' '))}</span>
    </div>
    <div class="tv-signal-body">
      <span>Oscillators: ${escapeHtml(tv.oscillators.recommendation.replace('_', ' '))} (${tv.oscillators.buy} buy / ${tv.oscillators.sell} sell / ${tv.oscillators.neutral} neutral)</span>
      <span>Moving averages: ${escapeHtml(tv.moving_averages.recommendation.replace('_', ' '))} (${tv.moving_averages.buy} buy / ${tv.moving_averages.sell} sell / ${tv.moving_averages.neutral} neutral)</span>
      <span class="tv-signal-note">Rule-based technical consensus from TradingView — not MindMesh's own calculation, not financial advice.</span>
    </div>`;
  card.classList.remove('hidden');
}
```

ทั้งสองฟังก์ชันเป็น `function` declaration ธรรมดา (hoisted) จึงไม่มีปัญหา temporal-dead-zone — ตรวจสอบแล้วว่า `escapeHtml` (บรรทัด 786) และ `$` (บรรทัด 3) พร้อมใช้งานปลอดภัย ไม่มีการเพิ่ม module-level `const` ใหม่ จึงไม่กระทบ regression test ของ `providerModels` TDZ ที่มีอยู่แล้ว

### 9. CSS — `app/web/static/app.css`

เพิ่มใกล้ๆ rule `.summary-cards`/`.metric-card` เดิม:

```css
.tv-signal-card {
  margin-top: 24px;
  padding: 20px 24px;
  border: 1px solid var(--hairline);
  border-radius: 12px;
}

.tv-signal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tv-signal-badge {
  padding: 4px 12px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 600;
}

.tv-signal-badge.is-buy { background: #e6f4ea; color: #1e7e34; }
.tv-signal-badge.is-sell { background: #fdecea; color: #c62828; }
.tv-signal-badge.is-neutral { background: #f1f1f4; color: var(--muted); }

.tv-signal-body {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
  color: var(--muted);
}

.tv-signal-note {
  margin-top: 4px;
  font-size: 12px;
}
```

---

## Phase 2 — AI-context wiring แบบ optional (ปิดไว้เป็น default, เปิดผ่าน flag)

ไม่จำเป็นสำหรับให้ฟีเจอร์ทำงาน — implement เฉพาะถ้ามีเวลาเหลือ

เพิ่ม `market_tv_include_in_analysis_context: bool` ใน `Settings` (default `False` ผ่าน `APP_MARKET_TV_INCLUDE_IN_ANALYSIS_CONTEXT`, เพิ่มใน `.env.example` เป็น `false`)

`app/analysis/context.py`'s `build_analysis_context` สร้าง facts string ด้วย (บรรทัดที่ตรวจสอบแล้ว): `full = f"{instruction}\n\nDeterministic data (computed, not opinion):\n{facts}"` ตัวเลข BUY/SELL/NEUTRAL ของ TradingView เป็นความเห็นแบบ rule-based ของ third-party ไม่ใช่ fact ที่ MindMesh คำนวณเอง — ถ้าเอาไปต่อท้ายใต้ header เดิมจะขัดกับหลักการแยก fact/opinion ของโมดูลนี้ ให้เพิ่ม keyword-only param ใหม่แทน:

```python
def build_analysis_context(
    snapshot: MarketSnapshot,
    analysis_type: AnalysisType,
    user_question: str | None,
    max_chars: int = 16000,
    *,
    tv_snapshot: "TradingViewSnapshot | None" = None,
) -> AnalysisContext:
    ...
    if tv_snapshot is not None:
        tv_lines = [
            f"Overall rating: {tv_snapshot.summary.recommendation} "
            f"({tv_snapshot.summary.buy} buy / {tv_snapshot.summary.sell} sell / {tv_snapshot.summary.neutral} neutral)",
            f"Oscillators: {tv_snapshot.oscillators.recommendation}",
            f"Moving averages: {tv_snapshot.moving_averages.recommendation}",
        ]
        full += (
            "\n\nThird-party technical consensus (TradingView rule-based ratings, "
            "not MindMesh calculations, not financial advice):\n" + "\n".join(tv_lines)
        )
        if len(full) > max_chars:
            full = full[: max_chars - 1] + "…"
```

จากนั้นใน `app/analysis/adapters/openai_compatible.py:62`, `anthropic.py:47`, `gemini.py:47` (เลขบรรทัด call site ที่ตรวจสอบแล้ว) เพิ่ม best-effort fetch ให้ TradingView ล้มเหลวแล้วไม่ทำให้ AI analysis request พัง:

```python
        tv_snapshot = None
        if self._settings.market_tv_include_in_analysis_context:
            try:
                tv_snapshot = await get_technical_snapshot(
                    request.symbol,
                    self._settings.market_tv_default_exchange,
                    self._settings.market_tv_default_screener,
                )
            except Exception:
                tv_snapshot = None  # best-effort only

        context = build_analysis_context(
            snapshot, request.analysis_type, request.user_question,
            max_chars=self._settings.ai_max_prompt_chars,
            tv_snapshot=tv_snapshot,
        )
```

`app/analysis/adapters/deep_debate.py` ไม่ได้เรียก `build_analysis_context` (TradingAgents ทำ tool-based data gathering ของตัวเอง) — ไม่ต้องแก้

---

## Tests

### `tests/test_market_tradingview.py` (ไฟล์ใหม่ — mirror pattern แบบ fake-based ไม่มี network ของ `tests/test_market_module.py`)

```python
"""TradingView technical-intelligence module tests via a fake, no network."""

from __future__ import annotations

import pytest

from app.market.tradingview import (
    TradingViewSymbolNotFoundError,
    TradingViewTimeoutError,
    _fetch_sync,
)


class _FakeAnalysis:
    summary = {"RECOMMENDATION": "BUY", "BUY": 10, "SELL": 2, "NEUTRAL": 3}
    oscillators = {"RECOMMENDATION": "NEUTRAL", "BUY": 3, "SELL": 3, "NEUTRAL": 5, "COMPUTE": {}}
    moving_averages = {"RECOMMENDATION": "BUY", "BUY": 7, "SELL": 0, "NEUTRAL": 5, "COMPUTE": {}}
    indicators = {"RSI": 55.2, "MACD.macd": 1.1, "MACD.signal": 0.9, "SMA20": 190.0,
                  "SMA50": 185.0, "SMA200": 170.0, "EMA20": 191.0, "BB.upper": 200.0,
                  "BB.lower": 180.0, "close": 195.0, "volume": 5000000, "change": 1.2}


class _FakeHandler:
    def __init__(self, **kwargs):
        pass

    def get_analysis(self):
        return _FakeAnalysis()


class _FakeHandlerNone:
    def __init__(self, **kwargs):
        pass

    def get_analysis(self):
        return None  # simulates get_analysis() returning None without raising


class _FakeHandlerNotFound:
    def __init__(self, **kwargs):
        pass

    def get_analysis(self):
        raise Exception("Exchange or symbol not found.")


class _FakeHandlerOtherError:
    def __init__(self, **kwargs):
        pass

    def get_analysis(self):
        raise Exception("Can't access TradingView's API. HTTP status code: 500.")


def test_snapshot_maps_ratings_and_allowlisted_indicators(monkeypatch):
    monkeypatch.setattr("app.market.tradingview.TA_Handler", _FakeHandler)
    snapshot = _fetch_sync("AAPL", "NASDAQ", "america", "1d", 10)
    assert snapshot.summary.recommendation == "BUY"
    assert snapshot.oscillators.buy == 3
    assert snapshot.indicators["RSI"] == 55.2
    assert "COMPUTE" not in snapshot.indicators


def test_none_analysis_raises_symbol_not_found(monkeypatch):
    monkeypatch.setattr("app.market.tradingview.TA_Handler", _FakeHandlerNone)
    with pytest.raises(TradingViewSymbolNotFoundError):
        _fetch_sync("NOPE", "NASDAQ", "america", "1d", 10)


def test_not_found_message_raises_symbol_not_found(monkeypatch):
    monkeypatch.setattr("app.market.tradingview.TA_Handler", _FakeHandlerNotFound)
    with pytest.raises(TradingViewSymbolNotFoundError):
        _fetch_sync("XXXX", "NASDAQ", "america", "1d", 10)


def test_other_error_raises_timeout_error(monkeypatch):
    monkeypatch.setattr("app.market.tradingview.TA_Handler", _FakeHandlerOtherError)
    with pytest.raises(TradingViewTimeoutError):
        _fetch_sync("AAPL", "NASDAQ", "america", "1d", 10)
```

เพิ่ม cache-path test แบบ mirror `test_market_module.py::test_cache_returns_same_object`, monkeypatch `app.market.tradingview._fetch_sync` แล้วเรียก `get_technical_snapshot` สองครั้งเพื่อยืนยันว่าครั้งที่สอง return object เดิมจาก cache

### `tests/test_web.py` เพิ่มเติม

เพิ่ม fixture `client_with_tv` ต่อยอดจาก fixture `client` เดิม พร้อม monkeypatch `app.web.routes.get_technical_snapshot`:

```python
@pytest.fixture
def client_with_tv(monkeypatch, snapshot_factory):
    async def fake_snapshot(query):
        return snapshot_factory(query.symbol)

    async def fake_tv_snapshot(symbol, exchange, screener, interval="1d"):
        from app.market.models import TechnicalRating, TradingViewSnapshot
        return TradingViewSnapshot(
            symbol=symbol, exchange=exchange, screener=screener, interval=interval,
            as_of="2026-01-01T00:00:00+00:00",
            summary=TechnicalRating(recommendation="BUY", buy=10, sell=2, neutral=3),
            oscillators=TechnicalRating(recommendation="NEUTRAL", buy=3, sell=3, neutral=5),
            moving_averages=TechnicalRating(recommendation="BUY", buy=7, sell=0, neutral=5),
        )

    monkeypatch.setattr("app.web.routes.get_market_snapshot", fake_snapshot)
    monkeypatch.setattr("app.web.routes.get_technical_snapshot", fake_tv_snapshot)
    return TestClient(create_app())


def test_market_technical_returns_rating(client_with_tv):
    resp = client_with_tv.get("/api/market/AAPL/technical")
    assert resp.status_code == 200
    assert resp.json()["summary"]["recommendation"] == "BUY"


def test_market_technical_rejects_invalid_exchange(client_with_tv):
    resp = client_with_tv.get("/api/market/AAPL/technical?exchange=bad;drop")
    assert resp.status_code == 422
```

### Phase 2 tests (implement เฉพาะถ้าทำ Phase 2)

เพิ่ม test ว่า `build_analysis_context(..., tv_snapshot=<snapshot>)` สร้าง facts string ที่มี `"Third-party technical consensus"` เป็น header แยกจาก `"Deterministic data (computed, not opinion):"` และรัน test เดิมของ context ซ้ำโดยไม่แก้ไข เพื่อยืนยันว่า call site เดิมทั้งสามจุด (ที่ไม่ได้ส่ง `tv_snapshot`) ไม่ได้รับผลกระทบ

---

## Verification

1. ติดตั้ง dependency: `cd /Users/codex074/Desktop/personal-llm/MindMesh && python3 -m pip install -e ".[dev]"`
2. Unit test ของโค้ดใหม่: `python3 -m pytest tests/test_market_tradingview.py tests/test_web.py -v`
3. Regression เต็ม: `python3 -m pytest -v` — ยืนยันว่า `test_market_module.py` และ `test_analysis_*` ทั้งหมดไม่กระทบ (yfinance path และ AI adapter เดิมไม่ถูกแตะ)
4. รันแอป (`mindmesh` หรือ `python3 -m app.main`) แล้วเปิด shell อีกอันทดสอบ:
   - `curl -s localhost:8000/api/market/AAPL/technical | python3 -m json.tool` → 200, `summary.recommendation` เป็นหนึ่งใน `STRONG_BUY|BUY|NEUTRAL|SELL|STRONG_SELL|ERROR`, `indicators` มีเฉพาะ key ที่อยู่ใน allowlist
   - `curl -s "localhost:8000/api/market/AAPL/technical?exchange=NYSE" -o /dev/null -w "%{http_code}\n"` → 404 (AAPL อยู่ NASDAQ ไม่ใช่ NYSE) — ยืนยัน path exchange-mismatch ทำงานถูกต้อง ไม่ crash
   - `curl -s "localhost:8000/api/market/AAPL/technical?exchange=bad;value" -o /dev/null -w "%{http_code}\n"` → 422
   - `curl -s localhost:8000/api/market/AAPL` → ยืนยันว่า endpoint yfinance เดิมมี response shape เหมือนเดิมทุกประการ ไม่เปลี่ยนแปลง
5. ตรวจสอบ UI ด้วยมือ: เปิด `http://localhost:8000/`, ค้นหา `AAPL`, ยืนยันว่า card "TradingView technical signal" แสดงพร้อม badge สีใต้ summary metrics; ค้นหา symbol ที่ไม่ใช่ NASDAQ แล้วยืนยันว่า card ซ่อนแบบเงียบๆ ไม่มี error ระดับหน้าเว็บ และส่วนอื่นของ dashboard (กราฟ, CSV, Analyse with AI) ยังทำงานปกติ
6. ตรวจสอบ non-blocking: เริ่ม deep-mode analysis stream ที่ช้า (`POST /api/analysis`, `analysis_mode="deep"`) พร้อมกับยิง `/api/market/AAPL/technical` ไปพร้อมกัน — SSE stream ต้องยังคง emit ต่อเนื่อง ยืนยันว่า `asyncio.to_thread` offload blocking call จริง ไม่ทำให้ event loop ค้าง
7. Phase 2 เท่านั้น (ถ้า implement): ตั้ง `APP_MARKET_TV_INCLUDE_IN_ANALYSIS_CONTEXT=true`, รัน quick-mode analysis, แล้วยืนยัน (ผ่าน debug print หรือ local echo `base_url`) ว่า prompt ที่ส่งออกไปมีทั้ง section `"Deterministic data..."` และ section แยกต่างหากท้ายสุด `"Third-party technical consensus..."`

---

## Critical files

- `app/market/tradingview.py` — ใหม่, โมดูลหลัก
- `app/market/models.py` — เพิ่ม `TechnicalRating`, `TradingViewSnapshot`
- `app/web/routes.py` — route ใหม่ `GET /api/market/{symbol}/technical`
- `app/config.py` + `.env.example` — settings ใหม่ `APP_MARKET_TV_*`
- `app/web/templates/dashboard.html`, `app/web/static/app.js`, `app/web/static/app.css` — signal card ใหม่
- `pyproject.toml` — dependency ใหม่
- `tests/test_market_tradingview.py` — ใหม่, fake-based unit test
- `tests/test_web.py` — route test เพิ่ม
- (Phase 2 เท่านั้น) `app/analysis/context.py`, `app/analysis/adapters/{openai_compatible,anthropic,gemini}.py`
