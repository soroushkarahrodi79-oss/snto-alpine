# Scaphoid Recovery — بهبود اسکافویید

A lightweight, mobile-first Personal Recovery Dashboard / Progressive Web App (PWA) for a patient undergoing conservative treatment for a right scaphoid fracture.

**This app is NOT a medical diagnostic tool.** It is a personal recovery companion for treatment adherence, cast care, nutrition, safe movement, clinical follow-up, and red-flag awareness.

---

## What the app does

It answers exactly five questions:

1. Where am I in my recovery timeline?
2. What should I do today?
3. What should I avoid today?
4. When is my next clinical checkpoint?
5. Is anything happening that means I should contact my medical team?

---

## What was intentionally NOT built

- Bone healing percentage or healing prediction
- AI diagnosis or chatbot
- Pain analytics or ML
- Social features, accounts, or cloud backend
- Apple Health / wearable integration
- Gamification or streaks
- Supplement marketplace
- Any claim of field validation

---

## How to run

```bash
cd scaphoid-pwa
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

## How to build for production

```bash
npm run build
npm run preview
```

## How to run tests

```bash
npm test
```

---

## How to install on iPhone (Add to Home Screen)

1. Build and serve the app (or use `npm run preview`).
2. Open Safari on iPhone and navigate to the app URL.
3. Tap the Share button (box with arrow).
4. Tap **Add to Home Screen**.
5. Confirm the name **بهبودی** and tap **Add**.

The app will now behave like a native app — no browser chrome, offline support, and a home screen icon.

For production use, deploy the `dist/` folder to any static hosting service (Vercel, Netlify, GitHub Pages, etc.) and access via HTTPS from Safari on iPhone.

---

## Where personal clinical configuration lives

All personal clinical constants are in two places:

### `src/data/clinicalProfile.ts`
Contains the **frozen clinical facts** derived from the CT report and treating physician's review:
- CT date
- CT findings (in Persian)
- Physician review notes
- Cast care do/don't lists
- Movement guidance
- Nutrition reference foods

**These should not be modified without a confirmed clinical update.**

### Settings (in-app)
The user-editable configuration (injury date, next appointments, dark mode, etc.) lives in the app's Settings screen (gear icon in the top right). It is stored in `localStorage` and survives page refresh.

Default injury date: `2026-07-30`

---

## How data is stored

- **Storage**: `localStorage` only — no backend, no account, no cloud sync.
- **Keys used**: `scaphoid_settings`, `scaphoid_daily_logs`, `scaphoid_weekly_checkins`, `scaphoid_medical_docs`
- **Survives**: page refresh, app close/reopen, browser restart
- **Does NOT survive**: clearing browser data, uninstalling the PWA

---

## Export / Import backup

In **Settings → Daده‌ها**:
- **صادرات (Export)**: Downloads a `scaphoid-recovery-backup-YYYY-MM-DD.json` file
- **وارد کردن (Import)**: Restores from a previously exported JSON file
- **بازنشانی (Reset)**: Deletes all data (requires confirmation)

---

## Clinical safety notes

- **Timeline shows time elapsed, NOT bone healing.** The progress bar displays "X% of 12-week immobilisation horizon elapsed" — this is emphatically not a healing percentage.
- Cast removal depends on clinical and imaging evidence of consolidation, decided by the treating physician — not on the countdown alone.
- The elbow is immobilised at ~90° in a long cast: no elbow exercises without medical authorisation.
- The app never infers surgical need, never recommends cast removal, and never interprets decreasing pain as proof of union.

---

## Tech stack

- **Vite + React + TypeScript**
- **CSS custom properties** (no Tailwind — keeps bundle small)
- **vite-plugin-pwa + Workbox** for PWA/offline support
- **localStorage** for persistence
- **Vitest** for testing
- Persian (Farsi) RTL UI with Vazirmatn font via Google Fonts (cached offline by service worker)
