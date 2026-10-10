// Starting messages per purpose. Placeholders must be replaced with organiser-verified details before launch.
export const OPT = "If you would like us to stop calling you, just tell us.";
export const PLACEHOLDER = "[ORGANISER: add verified details]";
export const TEMPLATES: Record<string, { en: (e: string) => string; ml?: (e: string) => string }> = {
  attendance_confirmation: {
    en: (e) => `Hello, this is Cadence calling on behalf of ${e} to confirm your attendance. Will you be able to attend? You can also ask us to call you back, or ask a question. ${OPT}`,
    ml: (e) => `നമസ്കാരം, ${e}-ന് വേണ്ടി Cadence വിളിക്കുന്നു. നിങ്ങളുടെ പങ്കാളിത്തം സ്ഥിരീകരിക്കാൻ വിളിക്കുകയാണ്. നിങ്ങൾക്ക് പങ്കെടുക്കാൻ കഴിയുമോ? തിരികെ വിളിക്കണമെങ്കിലോ എന്തെങ്കിലും ചോദിക്കാനുണ്ടെങ്കിലോ അതും പറയാം. ഇനി ഞങ്ങൾ വിളിക്കേണ്ടെങ്കിൽ അത് പറഞ്ഞാൽ മതി.`,
  },
  event_announcement: { en: (e) => `Hello, this is Cadence calling on behalf of ${e} with an announcement: ${PLACEHOLDER}. Please let us know you have heard this, or tell us if you have a question or would like a call back. ${OPT}` },
  schedule_venue_update: { en: (e) => `Hello, this is Cadence calling on behalf of ${e} with a schedule or venue update: ${PLACEHOLDER}. Please let us know you have heard this, or tell us if you have a question. ${OPT}` },
  submission_deadline_reminder: { en: (e) => `Hello, this is Cadence calling on behalf of ${e} with a reminder about the submission deadline: ${PLACEHOLDER}. Please let us know you have heard this, or tell us if you have a question. ${OPT}` },
  participant_followup: { en: (e) => `Hello, this is Cadence calling on behalf of ${e}. ${PLACEHOLDER}. Please let us know you have heard this, or tell us if you have a question or would like a call back. ${OPT}` },
};
