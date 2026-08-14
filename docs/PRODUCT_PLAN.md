# แผนพัฒนา OpenBB MindMesh App สำหรับ VPS

สถานะ: Draft สำหรับเริ่ม implementation  
เป้าหมายหลัก: เว็บแอปวิเคราะห์หุ้นที่เปิดใช้ได้ทันที, deploy บน VPS ได้ง่าย และใช้ AI แบบ Bring Your Own Key (BYOK)

## 1. Product vision

สร้างเว็บแอปหน้าเดียวที่ลดความซับซ้อนของ OpenBB Desktop เหลือ workflow หลักดังนี้:

1. ผู้ใช้กรอกสัญลักษณ์หุ้น เช่น `AAPL`
2. เลือกช่วงเวลาและกดค้นหา
3. แอปแสดงราคา กราฟ ปริมาณซื้อขาย ตัวเลขสรุป และตารางย้อนหลัง
4. ถ้าต้องการการวิเคราะห์เชิง AI ผู้ใช้เลือก AI provider, ระบุ model และกรอก API key ของตนเอง
5. แอปส่งข้อมูลที่จำเป็นให้ provider โดยตรงจาก backend, stream คำตอบกลับ และไม่บันทึก API key

แอปต้องใช้งานฟังก์ชันข้อมูลพื้นฐานได้โดยไม่ต้องกรอก API key โดยใช้ `yfinance` ผ่าน OpenBB เป็นค่าเริ่มต้น

## 2. กลุ่มผู้ใช้เป้าหมาย

- นักลงทุนรายบุคคลที่ต้องการดูข้อมูลหุ้นโดยไม่ใช้ Notebook หรือ CLI
- ผู้ใช้ที่มี API key ของ AI provider อยู่แล้ว
- เจ้าของ VPS ที่ต้องการ self-host ระบบของตัวเอง
- นักพัฒนาที่ต้องการต่อยอด provider หรือแบบวิเคราะห์ในอนาคต

## 3. ขอบเขต MVP

### 3.1 ฟังก์ชันข้อมูลตลาด

- ค้นหาด้วย ticker symbol
- เลือกช่วงเวลา: `1M`, `3M`, `6M`, `1Y`, `5Y`, `MAX`
- เลือก interval ที่สัมพันธ์กับช่วงเวลาโดยอัตโนมัติ
- แสดง:
  - ราคาล่าสุด
  - การเปลี่ยนแปลงและเปอร์เซ็นต์การเปลี่ยนแปลง
  - ราคาเปิด, สูงสุด, ต่ำสุด และปริมาณซื้อขาย
  - กราฟ Candlestick หรือ Line
  - Volume chart
  - ตาราง OHLCV ย้อนหลัง
- ดาวน์โหลดข้อมูลที่กำลังแสดงเป็น CSV
- แสดงเวลาอัปเดตล่าสุดและชื่อ data provider อย่างชัดเจน

### 3.2 ฟังก์ชัน AI แบบ BYOK

- ปุ่ม `วิเคราะห์ด้วย AI` แยกจากการค้นหาข้อมูลปกติ
- แบบฟอร์มประกอบด้วย:
  - AI provider
  - Model
  - API key
  - Base URL เฉพาะ provider แบบ OpenAI-compatible
  - รูปแบบการวิเคราะห์
  - คำถามเพิ่มเติมจากผู้ใช้
- รูปแบบการวิเคราะห์เริ่มต้น:
  - สรุปแนวโน้มราคา
  - วิเคราะห์ความเสี่ยง
  - อธิบายความผันผวนและ Volume
  - สรุปเชิงเทคนิคจากข้อมูลที่มี โดยไม่สร้างคำแนะนำซื้อขาย
- Stream ผลลัพธ์กลับมาบนหน้าเว็บ
- มีปุ่มหยุดการสร้างคำตอบและคัดลอกผลลัพธ์
- แสดง disclaimer ว่าเป็นข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำทางการเงิน

### 3.3 AI providers ในรุ่นแรก

รองรับผ่าน interface กลางเดียว โดยมี adapters ดังนี้:

1. OpenAI-compatible
   - ใช้ได้กับผู้ให้บริการที่รองรับรูปแบบ OpenAI
   - รับ `base_url`, `model`, `api_key`
   - ครอบคลุม OpenAI, OpenRouter, Groq, Together, DeepSeek และ self-hosted endpoints ที่เข้ากันได้
2. Anthropic
   - รับ `model`, `api_key`
3. Google Gemini
   - รับ `model`, `api_key`

รายการ model ไม่ควร hard-code เป็นความจริงถาวร ผู้ใช้กรอก model เองได้ และ UI อาจเสนอค่าเริ่มต้นจาก config ที่แก้ไขได้

## 4. สิ่งที่ไม่ทำใน MVP

- ไม่ทำระบบซื้อขายหรือส่งคำสั่งซื้อขาย
- ไม่ทำ Portfolio accounting
- ไม่ทำระบบสมาชิกเต็มรูปแบบภายในแอป
- ไม่บันทึก API key ลงฐานข้อมูล, localStorage, cookie หรือไฟล์
- ไม่ให้ AI ตัดสินใจซื้อ/ขายโดยอัตโนมัติ
- ไม่เปิด MCP, Jupyter หรือ environment management ใน UI
- ไม่รองรับ data providers แบบเสียเงินทุกตัวตั้งแต่รุ่นแรก
- ไม่ทำแอปมือถือ native

## 5. สถาปัตยกรรมที่แนะนำ

ใช้ Python เป็นหลักเพื่อให้เชื่อม OpenBB โดยตรงและ deploy ง่าย:

- Backend และ web server: FastAPI + Uvicorn
- HTML rendering: Jinja2
- UI interaction: HTMX หรือ JavaScript ขนาดเล็กที่เขียนเฉพาะจุด
- Chart: Lightweight Charts ที่ bundle ไว้กับแอป
- Data layer: OpenBB Python SDK
- Default market provider: `yfinance`
- Cache: in-memory TTL cache ใน MVP
- Deployment: Docker image เดียว + Caddy reverse proxy
- Persistence: ไม่มี database ใน MVP

เหตุผลที่ไม่ใช้ React SPA ในรุ่นแรก:

- เพิ่ม build pipeline และ dependency โดยไม่จำเป็น
- เพิ่ม interface ระหว่าง frontend/backend ที่ต้องดูแล
- การใช้งานหลักมีเพียงหน้าเดียวและ state ไม่ซับซ้อน
- Server-rendered HTML ทำให้ image เล็กกว่าและ debug บน VPS ง่ายกว่า

## 6. Module design

แต่ละ module ควรมี interface เล็กและซ่อน implementation ที่ซับซ้อนไว้ภายใน

### 6.1 Market Data module

Interface หลัก:

```python
async def get_market_snapshot(query: MarketQuery) -> MarketSnapshot
```

สิ่งที่ implementation ต้องซ่อน:

- การเรียก OpenBB
- การ map ช่วงเวลาเป็น start/end/interval
- การ normalize dataframe และ timezone
- การตรวจข้อมูลว่างหรือ symbol ไม่ถูกต้อง
- การคำนวณตัวเลขสรุป
- cache และ timeout
- การแปลง error ของ provider เป็นข้อความที่ผู้ใช้เข้าใจได้

ใน MVP ใช้ OpenBB/yfinance adapter ตัวเดียวและ fake adapter สำหรับ test ไม่ควรสร้าง abstraction สำหรับ data providers มากเกินความจำเป็นก่อนมี provider ตัวที่สองจริง

### 6.2 AI Analysis module

Interface หลัก:

```python
async def stream_analysis(request: AnalysisRequest) -> AsyncIterator[AnalysisEvent]
```

สิ่งที่ implementation ต้องซ่อน:

- รูปแบบ request ของ AI provider แต่ละราย
- prompt construction
- การลดขนาดข้อมูลก่อนส่งให้โมเดล
- streaming protocol
- timeout, cancellation และ error normalization
- token/output limits
- การล้าง secret ออกจาก error และ log

AI provider seam เป็น seam จริง เพราะมีหลาย adapters ตั้งแต่รุ่นแรก และ test ใช้ fake adapter ผ่าน interface เดียวกัน

### 6.3 Analysis Context module

Interface หลัก:

```python
def build_analysis_context(
    snapshot: MarketSnapshot,
    analysis_type: AnalysisType,
    user_question: str | None,
) -> AnalysisContext
```

หน้าที่:

- ส่งเฉพาะข้อมูลที่จำเป็น ไม่ส่ง dataframe ทั้งหมดแบบไร้ขอบเขต
- คำนวณผลตอบแทน, volatility, moving averages, drawdown และ volume summary แบบ deterministic
- ระบุข้อจำกัดและเวลาของข้อมูลให้โมเดล
- แยกข้อเท็จจริงที่คำนวณได้ออกจากความเห็นของ AI

### 6.4 Secret Handling module

Interface หลัก:

```python
async with ephemeral_secret(raw_key) as secret:
    ...
```

ข้อกำหนด:

- key อยู่ใน memory เฉพาะช่วง request
- ไม่บันทึกลง session storage ฝั่ง server
- ไม่ส่งกลับ browser
- ไม่ปรากฏใน traceback, access log หรือ telemetry
- object ที่ถือ key ต้องมี representation แบบ redacted
- key ถูกปล่อย reference หลัง request จบหรือถูกยกเลิก

ไม่ควรอ้างว่าสามารถล้าง secret จากหน่วยความจำ Python ได้อย่างสมบูรณ์ แต่ต้องลดอายุและจำนวนสำเนาให้ต่ำที่สุด

### 6.5 Web module

Interface ของ HTTP routes:

```text
GET  /                         หน้า dashboard
GET  /api/market/{symbol}      ข้อมูลตลาดแบบ normalized
POST /api/analysis             stream การวิเคราะห์ด้วย AI
GET  /api/config               public UI configuration ที่ไม่มี secret
GET  /health/live              process health
GET  /health/ready             dependency readiness
```

Web module รับผิดชอบ validation, HTTP status และ rendering แต่ไม่ควรมี logic วิเคราะห์ข้อมูลหรือ logic เฉพาะ provider

## 7. Data contracts

### MarketQuery

```text
symbol: string                 required, normalized เป็น uppercase
period: enum                   1M | 3M | 6M | 1Y | 5Y | MAX
provider: string               default yfinance
```

### MarketSnapshot

```text
symbol
provider
currency
timezone
as_of
latest_price
absolute_change
percent_change
open/high/low/volume
summary_metrics
series[]: timestamp/open/high/low/close/volume
warnings[]
```

### AnalysisRequest

```text
symbol
period
analysis_type
user_question?
ai.provider
ai.model
ai.api_key
ai.base_url?
```

API key ต้องถูก exclude จาก request dump, validation error และ structured logging ทุกกรณี

## 8. UX flow

### 8.1 หน้า Dashboard

```text
┌──────────────────────────────────────────────────────┐
│ OpenBB Lean                                          │
│ [ AAPL             ] [1Y ▼] [ค้นหา]                 │
├──────────────────────────────────────────────────────┤
│ $231.40   +1.82%    High 233.10    Volume 48.2M      │
│                                                      │
│                 Price / Volume Chart                 │
│                                                      │
│ [ข้อมูลย้อนหลัง] [ดาวน์โหลด CSV] [วิเคราะห์ด้วย AI] │
└──────────────────────────────────────────────────────┘
```

สถานะที่ต้องออกแบบชัดเจน:

- Initial state พร้อมตัวอย่าง ticker
- Loading state
- Symbol ไม่ถูกต้องหรือไม่พบข้อมูล
- Provider timeout/rate limit
- Partial data พร้อม warning
- Mobile layout

### 8.2 AI drawer/modal

เปิดเมื่อผู้ใช้กด `วิเคราะห์ด้วย AI` เท่านั้น:

```text
Provider     [OpenAI-compatible ▼]
Model        [กรอกชื่อ model]
Base URL     [แสดงเฉพาะเมื่อจำเป็น]
API Key      [••••••••••••]
Analysis     [สรุปแนวโน้ม ▼]
คำถามเพิ่ม   [....................]

[ยกเลิก] [เริ่มวิเคราะห์]
```

ใต้ช่อง API key แสดงข้อความ:

> API key ใช้สำหรับคำขอนี้เท่านั้น และจะไม่ถูกบันทึกโดยแอป

## 9. Security requirements

### 9.1 Transport และ access

- Production ต้องให้บริการผ่าน HTTPS เท่านั้น
- FastAPI ไม่เปิด port สู่ public โดยตรง ให้ผ่าน Caddy
- Deployment ส่วนตัวใช้ Caddy Basic Auth หรือ Cloudflare Access เป็นค่าเริ่มต้น
- ตั้ง secure headers: CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`
- จำกัด request body และ input lengths

### 9.2 BYOK

- ส่ง API key ใน body ของ `POST /api/analysis` เท่านั้น
- ห้ามส่ง key ใน URL/query string
- ห้ามใช้ browser localStorage หรือ analytics capture บนฟอร์มนี้
- ปิด request-body logging
- redact headers และ fields ที่อาจมี secret
- ไม่ retry ข้าม provider โดยอัตโนมัติเพราะอาจส่งข้อมูลไปยังปลายทางที่ผู้ใช้ไม่ได้เลือก

### 9.3 Custom Base URL และ SSRF

การรับ custom endpoint บน VPS มีความเสี่ยง SSRF จึงต้อง:

- อนุญาตเฉพาะ `https` ใน production
- resolve DNS และปฏิเสธ loopback, link-local, private network และ cloud metadata addresses
- ตรวจ redirect ทุก hop ด้วยกฎเดียวกัน
- ใช้ allowlist เมื่อ deploy แบบ public/multi-user
- จำกัด port, timeout และ response size
- เปิดการเชื่อม endpoint ภายในเฉพาะ deployment ที่ผู้ดูแลตั้งค่าไว้อย่างชัดเจน

### 9.4 Financial safety

- AI prompt ต้องบอกให้แยกข้อเท็จจริง การคำนวณ และข้อสันนิษฐาน
- แสดง data timestamp และ provider ในผลวิเคราะห์
- ห้ามสร้างคำสั่งซื้อขายหรือรับประกันผลตอบแทน
- แสดง disclaimer ใน UI และผล export

## 10. Performance และ reliability

- หน้าแรกตอบสนองโดยไม่เรียก AI
- Market data timeout เป้าหมาย 15 วินาที
- AI first-token timeout เป้าหมาย 30 วินาที
- จำกัด output token ผ่าน config
- cache market data ตาม `(symbol, period, provider)` อายุ 1–5 นาที
- ไม่ cache API key หรือคำตอบ AI ใน MVP
- จำกัด concurrent AI requests ต่อ client
- รองรับ cancellation เมื่อผู้ใช้ปิด modal หรือกด Stop
- circuit-breaker แบบง่ายต่อ provider ที่ error ต่อเนื่อง

## 11. โครงสร้างไฟล์ที่เสนอ

สร้างแอปใหม่แยกจาก `desktop` และไม่แก้ behavior ของ OpenBB เดิม:

```text
apps/lean_web/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── web/
│   │   ├── routes.py
│   │   ├── templates/
│   │   └── static/
│   ├── market/
│   │   ├── models.py
│   │   └── module.py
│   ├── analysis/
│   │   ├── models.py
│   │   ├── context.py
│   │   ├── module.py
│   │   └── adapters/
│   │       ├── openai_compatible.py
│   │       ├── anthropic.py
│   │       └── gemini.py
│   └── security/
│       ├── secrets.py
│       └── outbound_url.py
├── tests/
│   ├── fakes/
│   ├── test_market_module.py
│   ├── test_analysis_module.py
│   ├── test_security.py
│   └── test_web.py
├── Dockerfile
├── compose.yaml
├── Caddyfile
├── pyproject.toml
├── .env.example
└── README.md
```

## 12. Configuration

Environment variables ฝั่ง server:

```text
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
APP_PUBLIC_URL=https://stocks.example.com
APP_ALLOWED_HOSTS=stocks.example.com
APP_MARKET_PROVIDER=yfinance
APP_MARKET_CACHE_TTL_SECONDS=120
APP_AI_MAX_OUTPUT_TOKENS=2000
APP_AI_TIMEOUT_SECONDS=90
APP_AI_ALLOWED_BASE_URLS=
APP_AUTH_MODE=proxy
LOG_LEVEL=INFO
```

ห้ามกำหนด API key ของผู้ใช้ใน server `.env` สำหรับ flow BYOK หากภายหลังต้องการ server-managed key ให้เพิ่มเป็นโหมดแยกที่ผู้ดูแลเปิดเอง

## 13. Deployment บน VPS

### รูปแบบแนะนำ

```text
Internet → Caddy (HTTPS/Auth/Rate Limit) → MindMesh App → OpenBB/AI Providers
```

### Compose services

- `web`: FastAPI app, internal port 8000
- `caddy`: TLS termination และ access protection

### ขั้นตอน deploy

1. ติดตั้ง Docker และ Docker Compose plugin บน VPS
2. Clone repository
3. Copy `.env.example` เป็น `.env` และกำหนด domain
4. ตั้ง DNS ให้ชี้มาที่ VPS
5. รัน `docker compose up -d --build`
6. ตรวจ `/health/ready`
7. เปิด HTTPS URL และทดสอบ market data
8. ทดสอบ AI ด้วย key ชั่วคราวและตรวจ log ว่าไม่มี secret

Container ต้องรันด้วย non-root user, filesystem แบบ read-only เท่าที่ทำได้, drop Linux capabilities และกำหนด CPU/memory limits

## 14. Testing strategy

ทดสอบผ่าน interface ของ module ไม่ผูกกับ implementation ภายใน

### Unit/module tests

- Market query normalization และ summary metrics
- ข้อมูลว่าง, ticker ผิด, timeout และ rate limit
- Analysis context มีเฉพาะข้อมูลที่อนุญาตและขนาดไม่เกิน limit
- AI adapters แปลง streaming event เป็นรูปแบบกลาง
- cancellation และ timeout
- secret redaction ใน exception และ log
- outbound URL validation ป้องกัน SSRF และ redirect bypass

### Integration tests

- FastAPI routes กับ fake market adapter และ fake AI adapter
- POST analysis stream สำเร็จโดยไม่เก็บ key
- CSV export
- security headers และ body-size limits
- Docker health checks

### End-to-end tests

- ค้นหา ticker แล้วเห็นกราฟและตัวเลข
- เปิด AI modal, กรอก provider/model/key แล้วรับ streamed response
- invalid key แสดงข้อความที่เข้าใจได้และไม่เปิดเผย key
- mobile viewport ใช้งาน flow หลักได้

External provider live tests ให้เป็น optional/manual หรือ scheduled tests แยกจาก CI ปกติ

## 15. Implementation phases

### Phase 0 — Scaffold และ deployment skeleton

- สร้าง `apps/lean_web`
- FastAPI, templates, static assets และ health endpoints
- Dockerfile, Compose, Caddy และ `.env.example`
- CI สำหรับ lint/test/build image

เกณฑ์ผ่าน: deploy หน้า placeholder บน local Docker และ VPS staging ผ่าน HTTPS ได้

### Phase 1 — Market dashboard

- Market Data module
- OpenBB/yfinance integration
- Summary cards, chart, table และ CSV
- Loading/error/empty states
- TTL cache

เกณฑ์ผ่าน: ผู้ใช้เปิดเว็บ ค้นหา `AAPL` และดูข้อมูลได้โดยไม่กรอก key

### Phase 2 — AI analysis core

- Analysis Context module
- AI Analysis module และ streaming
- OpenAI-compatible adapter
- BYOK modal, cancellation และ disclaimer
- secret redaction tests

เกณฑ์ผ่าน: ผู้ใช้กรอก provider/model/key แล้วรับบทวิเคราะห์แบบ stream โดย key ไม่อยู่ใน log หรือ storage

### Phase 3 — Provider expansion

- Anthropic adapter
- Gemini adapter
- provider-specific validation และข้อความ error
- editable model field และ configurable suggestions

เกณฑ์ผ่าน: adapters ทุกตัวผ่าน contract tests ชุดเดียวกัน

### Phase 4 — Security และ production hardening

- SSRF protection
- reverse-proxy auth
- rate limits, secure headers และ request limits
- non-root/read-only container
- backup/restore documentation สำหรับ config ที่ไม่มี secret
- deployment smoke test

เกณฑ์ผ่าน: security checklist ผ่านและ image สามารถ redeploy โดยไม่สูญเสีย config สำคัญ

### Phase 5 — UX polish

- responsive/mobile layout
- accessibility และ keyboard navigation
- chart interactions
- copy/export experience
- ภาษาไทย/อังกฤษผ่าน locale files

## 16. Acceptance criteria ของ MVP

- รัน local ได้ด้วยคำสั่งเดียว: `docker compose up --build`
- deploy บน VPS Linux ได้โดยไม่ต้องติดตั้ง Python หรือ OpenBB บน host
- market dashboard ใช้ได้โดยไม่มี API key
- AI ทำงานเฉพาะเมื่อผู้ใช้ส่ง provider, model และ API key
- API key ไม่ถูกเก็บใน database, file, cookie, localStorage หรือ log
- รองรับ OpenAI-compatible อย่างน้อยหนึ่ง adapter และมี fake adapter สำหรับ test
- กรณี provider ล่มหรือ key ผิด UI ไม่ล่มและไม่เปิดเผย secret
- มี HTTPS/auth deployment path ที่อธิบายและทดสอบแล้ว
- source เดิมใน `desktop` และ OpenBB packages ไม่ถูกเปลี่ยน behavior

## 17. งานหลัง MVP

- Watchlist ที่เก็บใน browser หรือ database แบบ opt-in
- ข่าวและงบการเงิน
- เปรียบเทียบหลาย ticker
- Technical indicators ที่ผู้ใช้เลือกเอง
- Export บทวิเคราะห์เป็น Markdown/PDF
- Server-managed AI key สำหรับ deployment แบบทีม โดยใช้ secret manager
- ระบบผู้ใช้และ quota เมื่อจำเป็นจริง
- Redis cache และหลาย web workers เมื่อ traffic สูงขึ้น
- data provider BYOK แยกจาก AI provider BYOK

## 18. Decisions ที่ล็อกไว้สำหรับเริ่มงาน

- แอปเป็นโปรเจกต์ใหม่ใต้ `apps/lean_web`
- ใช้ FastAPI + Jinja2 + JavaScript เท่าที่จำเป็น
- ใช้ OpenBB/yfinance เป็นข้อมูลพื้นฐาน
- ใช้ request-scoped BYOK และไม่ทำ secret persistence ใน MVP
- เริ่มจาก private/single-owner VPS ที่ป้องกันด้วย reverse proxy auth
- AI analysis เป็น optional enhancement ไม่บล็อก market dashboard
- ไม่มี database จนกว่าจะมี use case persistence ที่ชัดเจน

## 19. ประเด็นที่ตัดสินภายหลังได้โดยไม่บล็อก MVP

- ชื่อผลิตภัณฑ์และ visual identity
- ใช้ Caddy Basic Auth หรือ Cloudflare Access
- provider/model suggestions เริ่มต้น
- ค่า TTL และ token limit ที่เหมาะกับ VPS จริง
- เพิ่ม data provider แบบมี key รายใดเป็นลำดับแรก

