// Design tokens, same palette as the web UI: white surfaces, black ink, hairlines; yellow = the one highlight, pink = needs a person.
export const colors = {
  canvas: "#f6f6f5", surface: "#ffffff", ink: "#111113", ink2: "#3d3d42", muted: "#77777e",
  line: "#e5e5e7", lineSoft: "#efeff1", brand: "#111113", brandSoft: "#f1f1f2",
  marigold: "#ffe53b", marigoldInk: "#111113", marigoldSoft: "#fff7c2",
  signal: "#e03a6b", signalSoft: "#fde4ec", thumbi: "#6a4fe0",
  good: "#1f9d55", bad: "#d2453a", warn: "#a0650a", info: "#6a4fe0", neutral: "#7a7a82", sage: "#b9b9c0",
} as const;

export const fonts = {
  display: "HankenGrotesk_700Bold", displayBold: "HankenGrotesk_600SemiBold",
  body: "HankenGrotesk_400Regular", medium: "HankenGrotesk_500Medium", semi: "HankenGrotesk_600SemiBold", bold: "HankenGrotesk_700Bold",
  ml: "NotoSansMalayalam_400Regular",
} as const;

export const radius = { sm: 6, md: 8, lg: 10, xl: 12, pill: 999 } as const;
export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const toneColor = { good: colors.good, bad: colors.bad, warn: colors.warn, info: colors.info, neutral: colors.neutral } as const;
