# Raissa Good Bots — TikTok Automation Suite

Sistem de automatizare TikTok care rulează pe un **VM Linux** controlând un **telefon Android** prin ADB / uiautomator2.

Contul TikTok operat: **@i.live.in.hotels** (Raissa)

---

## Boți

### Charlie (`charlie.py`)
**TikTok Search-based bot** — caută utilizatori și videouri pe TikTok, apoi interacționează.

Are două faze pe ciclu:

| Fază | Ce face |
|------|---------|
| **ALFA** | Caută useri pe baza unor query-uri travel/lifestyle → deschide profilul → follow + like primul video |
| **BRAVO** | Caută videouri pe aceleași query-uri → lasă comentarii generate de AI (OpenAI GPT-4o-mini) |

**Reguli de filtrare profil:**
- Skip dacă `followers > 5.000`
- Skip dacă `following × 3 ≤ followers` (cont prea popular, nu va da follow-back)
- Doar profilurile cu `following × 3 > followers` sunt eligibile

**Comentarii AI (faza BRAVO):**
- 1-2 propoziții scurte, specifice conținutului video-ului
- Fără hashtag-uri, fără text generic
- Anti-duplicate: hash pe (creator + username + caption)
- Cooldown per creator: 12 ore între comentarii la același creator
- Istoricul comentariilor se salvează în `tt_comment_history.json`

**Query-uri:** Grupuri tematice rotite ciclic (travel, backpacking, digital nomad, Europe, etc.), cu state persistent în `charlie_query_state.json`.

---

### India (`india.py`)
**TikTok For You-based bot** — scrollează feed-ul For You și interacționează cu conținutul organic.

| Acțiune | Detalii |
|---------|---------|
| **Scroll** | Swipe pe For You, evaluează fiecare video |
| **First-glance filter** | Skip automat: conținut sponsorizat, branded, promovat, reclame |
| **Follow + Like** | Deschide profilul creatorului → follow confirmat → like video-ul curent |

**Reguli de filtrare profil:** Identice cu Charlie:
- Skip dacă `followers > 5.000`
- Skip dacă `following × 3 ≤ followers`

**Target per ciclu:** Random între **22 și 31** acțiuni confirmate (follow + like).

**Fără comentarii** — India doar follow + like.

---

### Nuke (`nuke.py`)
**Cleanup utility** — oprește totul și resetează telefonul la Home screen.

Pași:
1. Oprește toate procesele Python ale boților (charlie, india, delta, echo, foxtrot)
2. Oprește serviciile uiautomator (`com.github.uiautomator`, `atx-agent`)
3. Force-stop TikTok (`com.zhiliaoapp.musically`) și Instagram (`com.instagram.android`)
4. Trimite telefonul la Home screen

Se apelează automat la începutul fiecărui ciclu (prin launcher-e) și poate fi rulat manual oricând.

---

## Launcher-e

### `run_charlie.sh`
Script shell care:
1. Verifică/reconectează ADB la telefon (`192.168.68.50`)
2. Scanează porturile 30000-49999 dacă telefonul nu e conectat
3. Rulează `nuke.py` (cleanup)
4. Lansează `charlie.py --cycles 1`
5. Loguri per-run în `charlie_YYYYMMDD_HHMMSS.log`

### `run_india.sh`
Identic ca structură cu `run_charlie.sh`, dar lansează `india.py --cycles 1`.
Loguri per-run în `india_YYYYMMDD_HHMMSS.log`.

---

## Programare zilnică (`crontab.txt`)

| Ora România (UTC+3) | UTC | Bot |
|----------------------|-----|-----|
| 10:03 | 07:03 | Charlie |
| 11:30 | 08:30 | India |
| 13:42 | 10:42 | Charlie |
| 15:41 | 12:41 | India |
| 17:33 | 14:33 | Charlie |
| 20:02 | 17:02 | India |
| 22:43 | 19:43 | Charlie |

**Total: 4× Charlie + 3× India pe zi.**

---

## Infrastructură

```
VM Linux (Ubuntu)
  └── ADB over TCP → Telefon Android (192.168.68.50)
       └── uiautomator2 → controlează UI-ul TikTok
```

- **Python venv:** `/home/corban/good bots/venv/bin/python3`
- **Director boți:** `/home/corban/charlie/`
- **Dependențe Python:** `uiautomator2`, `openai` (doar Charlie)
- **API key OpenAI:** Se citește din variabila de mediu `OPENAI_API_KEY`

---

## Note

- Fiecare rulare este **one-shot** (1 ciclu), lansată de cron sau manual
- Boții verifică ADB la fiecare pornire și reconectează automat dacă e nevoie
- `nuke.py` se rulează înainte de fiecare ciclu pentru a garanta un start curat
- Charlie și India sunt complet independenți — nu interferează între ei
