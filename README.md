<div align="center">

# 🧠 MindMesh

### Market intelligence ที่รวมข้อมูลราคา สัญญาณเทคนิค และ AI analysis ไว้ในที่เดียว

<p>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/BYOK-Private_by_Design-7C3AED?style=for-the-badge" alt="BYOK private by design">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker ready">
</p>

<p>
  <strong>🟦 Market Data</strong> ・
  <strong>🟪 Quick AI</strong> ・
  <strong>🟧 Deep Debate</strong> ・
  <strong>🟩 Local App</strong>
</p>

</div>

---

MindMesh คือเว็บแอปสำหรับสำรวจตลาด วิเคราะห์หุ้น และพูดคุยกับ AI ผ่าน dashboard เดียว พัฒนาโดยใช้ FastAPI พร้อมแนวคิด **Bring Your Own Key (BYOK)** — API key ถูกใช้เฉพาะ request นั้นและไม่ถูกบันทึกไว้ในระบบ

## ✨ จุดเด่น

| | ความสามารถ | รายละเอียด |
|---|---|---|
| 📈 | **Market dashboard** | ดูข้อมูลราคา กราฟย้อนหลัง ภาพรวมดัชนี และดาวน์โหลด CSV |
| 📊 | **Technical signal** | วิเคราะห์สัญญาณเทคนิคผ่าน TradingView TA |
| ⚡ | **Quick analysis** | ใช้โมเดลเดียวเพื่อสรุปแนวโน้ม ความเสี่ยง และ volatility แบบ streaming |
| 🧩 | **Deep analysis** | ให้หลาย agent ถกมุม Bull, Bear และ Risk ผ่าน TradingAgents |
| 💬 | **AI chat** | สนทนาต่อจากข้อมูลสินทรัพย์ที่กำลังดูอยู่ |
| 🔐 | **Private by design** | Key อยู่ในหน่วยความจำเฉพาะ request และไม่ถูกเก็บ log หรือส่งกลับไปยังหน้าเว็บ |
| 🚀 | **One-command launcher** | สร้าง virtual environment, ติดตั้ง dependency, เลือกพอร์ต และเปิด browser ให้อัตโนมัติ |

## 🚀 เริ่มใช้งาน

### Clone และติดตั้งคำสั่ง

```bash
git clone https://github.com/codex074/mindmesh.git
cd mindmesh
./install.sh
```

`install.sh` ใช้เพียงครั้งแรก โดยจะ:

1. ติดตั้งคำสั่ง `mindmesh` ระดับผู้ใช้ที่ `~/.local/bin` โดยไม่ใช้ `sudo`
2. เพิ่มตำแหน่งคำสั่งลง `PATH` สำหรับ terminal ใหม่ หากจำเป็น
3. เปิด MindMesh ให้ทันที

ครั้งต่อไป เรียกแอปจาก terminal ที่ไหนก็ได้:

```bash
mindmesh
```

> [!TIP]
> หากไม่ต้องการติดตั้งคำสั่งลง `PATH` สามารถเข้าโฟลเดอร์โปรเจกต์แล้วรัน `./mindmesh` ได้ตลอดเวลา

### สิ่งที่ launcher จัดการให้

```text
ค้นหา Python 3.11+
        ↓
สร้าง .venv และติดตั้ง dependencies
        ↓
สร้าง .env สำหรับ local development
        ↓
เลือก port 8000 หรือ port ว่างอัตโนมัติ
        ↓
เปิด Dashboard ใน browser
```

เมื่อแอปพร้อมใช้งาน terminal จะแสดง URL เช่น:

```text
[mindmesh] starting MindMesh…
[mindmesh]   → http://127.0.0.1:8000
[mindmesh] server ready — opening browser
```

หยุดแอปด้วย `Ctrl+C`

## 🔌 การเลือกพอร์ต

MindMesh จะใช้ `8000` เป็นค่าเริ่มต้น หากพอร์ตนี้ถูกใช้งานอยู่ ระบบจะเลือกพอร์ตว่างและเปิด URL ที่ถูกต้องให้โดยอัตโนมัติ

กำหนดพอร์ตเองได้ด้วย:

```bash
MINDMESH_PORT=9000 mindmesh
```

ถ้าพอร์ตที่กำหนดไม่ว่าง launcher จะ fallback ไปยังพอร์ตที่ใช้งานได้แทน โดยพอร์ตล่าสุดจะถูกจำไว้ใน `.mindmesh-port`

## 🤖 โหมด AI

| โหมด | เหมาะสำหรับ | วิธีทำงาน |
|---|---|---|
| ⚡ **Quick** | ต้องการคำตอบรวดเร็วและประหยัด token | โมเดลเดียววิเคราะห์และ stream คำตอบกลับทันที |
| 🧩 **Deep** | ต้องการมุมมองหลายด้านและรายงานเชิงโครงสร้าง | TradingAgents แยกทีม Bull, Bear และ Risk ให้ถกกันใน subprocess แยกต่างหาก |

Quick mode รองรับ:

- OpenAI และ OpenAI-compatible endpoints
- DeepSeek
- Anthropic
- Google Gemini

Market data ใช้งานได้โดยไม่ต้องมี API key ส่วนฟีเจอร์ AI จะให้กรอก key ของ provider ในหน้าเว็บทุกครั้งที่ใช้งาน

### เปิดใช้ Deep mode

```bash
mindmesh --deep
```

การรันครั้งแรกจะติดตั้ง TradingAgents จาก commit ที่ pin ไว้ อาจใช้เวลานานกว่า Quick mode เล็กน้อย

## 🛠️ Local development

ต้องใช้ Python 3.11 ขึ้นไป:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e . ".[dev]"
uvicorn app.main:app --reload
```

เปิด [http://localhost:8000](http://localhost:8000) และ API documentation ที่ [http://localhost:8000/docs](http://localhost:8000/docs)

สำหรับ Deep mode แบบ editable จาก repository ที่อยู่ข้างกัน:

```bash
pip install -e ./TradingAgents
```

### รันชุดทดสอบ

```bash
source .venv/bin/activate
pytest
```

## 🐳 Docker

```bash
cp .env.example .env
docker compose up --build
```

เปิด [http://localhost:8080](http://localhost:8080)

Container bind พอร์ตไว้ที่ `127.0.0.1:8080` เท่านั้น จึงไม่เปิด FastAPI ออกสู่ public interface โดยตรง ใน production ควรให้ Caddy ติดต่อ container ผ่าน `mindmesh_app:8000`

TradingAgents ภายใน image ถูกติดตั้งจาก Git commit ที่ pin ไว้ใน `pyproject.toml` และไม่ได้ copy source หรือ key จากเครื่อง local เข้า build context

## ⚙️ Configuration

ค่าตั้งต้นอยู่ใน [.env.example](.env.example) โดย launcher จะสร้าง `.env` สำหรับ local development ให้ในครั้งแรก

| ตัวแปร | ค่าเริ่มต้น | หน้าที่ |
|---|---:|---|
| `APP_HOST` | `127.0.0.1` เมื่อรันผ่าน launcher | Interface ที่เว็บเซิร์ฟเวอร์ bind |
| `APP_PORT` | `8000` | พอร์ตภายในของแอป |
| `MINDMESH_PORT` | `8000` | ขอพอร์ตเฉพาะสำหรับ local launcher |
| `APP_MARKET_PROVIDER` | `yfinance` | แหล่งข้อมูลตลาดหลัก |
| `APP_MARKET_CACHE_TTL_SECONDS` | `120` | อายุ cache ของข้อมูลตลาด |
| `APP_AI_MAX_OUTPUT_TOKENS` | `2000` | จำนวน output token สูงสุดต่อคำขอ |
| `APP_AI_MAX_CONCURRENT_PER_CLIENT` | `3` | จำนวนงาน AI พร้อมกันต่อ client |
| `APP_DATA_DIR` | `./data` | ตำแหน่ง cache, result และ Deep memory |

> [!CAUTION]
> อย่าใส่ API key ของ AI provider ลงใน `.env` — MindMesh ออกแบบให้รับ key จากผู้ใช้แบบ request-scoped เท่านั้น

## 🔒 Security

- BYOK key ไม่ถูกบันทึกลง disk, log หรือ response
- Deep mode ส่ง key เข้า subprocess ผ่าน environment ที่จำกัดเฉพาะค่าจำเป็น
- Custom OpenAI-compatible base URL ผ่านการตรวจ SSRF ก่อนเชื่อมต่อ
- Docker publish เฉพาะ loopback interface
- Container ทำงานด้วย non-root user พร้อม drop Linux capabilities

## 🗂️ โครงสร้างโปรเจกต์

```text
MindMesh/
├── app/
│   ├── analysis/       # Quick/Deep adapters และ streaming contracts
│   ├── deep/           # TradingAgents runner และ concurrency pool
│   ├── market/         # Market data และ technical indicators
│   ├── security/       # Secret handling และ outbound URL policy
│   └── web/            # FastAPI routes, templates และ static assets
├── docs/               # Product, execution และ integration plans
├── tests/              # Automated test suite
├── compose.yaml        # Docker Compose stack
├── install.sh          # ติดตั้งคำสั่ง mindmesh
└── mindmesh            # Local bootstrap launcher
```

## 📚 เอกสารเพิ่มเติม

- [Product Plan](docs/PRODUCT_PLAN.md) — ขอบเขตผลิตภัณฑ์ UX และ security model
- [Execution Plan](docs/EXECUTION_PLAN.md) — การรวม TradingAgents และแนวทาง deploy
- [TradingView Integration Plan](docs/TRADINGVIEW_INTEGRATION_PLAN.md) — public scanner และ Desktop bridge

<details>
<summary><strong>⚠️ หมายเหตุสำหรับ VPS ที่มี pharmshift อยู่แล้ว</strong></summary>

ติดตั้ง MindMesh แยก directory และแยก Compose project จาก pharmshift เสมอ:

- `compose.yaml` กำหนดชื่อ project เป็น `mindmesh` ไว้แล้ว
- ตรวจพอร์ตด้วย `ss -tlnp` และ `docker ps` ก่อน deploy
- เพิ่ม site block ของ MindMesh ต่อท้าย Caddyfile เดิม ห้ามเขียนทับ
- ใช้ domain แยกจาก pharmshift
- ห้าม stop, remove หรือ rebuild container/volume ของ pharmshift

</details>

---

<div align="center">

สร้างมาเพื่อให้การสำรวจตลาดและการใช้ AI วิเคราะห์ข้อมูลเป็นเรื่องง่าย — โดยยังรักษา key ไว้กับผู้ใช้ 🔐

</div>
