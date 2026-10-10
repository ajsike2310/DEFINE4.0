# Cadence app (React Native / Expo)

Expo SDK 57, React Native 0.86, `react-native-web`, expo-router (file routes in `src/app`, screens in `src/screens`).
Same backend API as the web UI; all calls go through `src/services/api.ts`.

## Run
```powershell
cd member1\app
npm install
npx expo start --web --port 8081     # browser: http://localhost:8081
npx expo start                       # QR code for Expo Go (Android / iOS)
```
The backend must be running (`scripts\dev.ps1` starts both).

### API address
`EXPO_PUBLIC_API_URL` (default `http://localhost:8000`). In a browser on the same machine the default works.
**On a phone or emulator `localhost` is the phone itself** — set it to your computer's LAN address
(e.g. `$env:EXPO_PUBLIC_API_URL="http://192.168.1.20:8000"`) and start the backend with `--host 0.0.0.0`.
The backend allows browser origins listed in `CORS_ORIGINS` (default includes `localhost:5173`, `:8081`, `:19006`);
native apps are not subject to CORS. **Restart the backend after pulling this change.**

## Check
```powershell
npm run typecheck
npm test                 # jest-expo + React Native Testing Library (26 tests)
npm run build:web        # static web export to dist/
```

## Layout
- `src/theme.ts` — design tokens (palette, type scale, shadows). `src/components/ui.tsx` — primitives.
- `src/components/Shell.tsx` — sidebar (≥ 900 px) or menu button (narrower), event picker, bell.
- `src/components/Notifications.tsx` — toasts, notification centre, confirm dialog.
- `src/hooks`, `src/services`, `src/types` — logic carried over unchanged from the web UI.
