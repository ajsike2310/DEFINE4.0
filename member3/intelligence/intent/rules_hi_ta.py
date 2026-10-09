"""Hindi and Tamil phrase lists for the rule matcher (native script plus a few common romanised forms).

NOT reviewed by a native speaker. They are small hand-written examples, not evidence of real-world accuracy, and
Hindi/Tamil speakers should check and extend them (same caveat as the Malayalam lists in rules.py).

Matching notes (see rules._contains):
  * Hindi (Devanagari) and romanised phrases match as whole words; spelling variants are normalised first, so
    "हाँ"/"हां" and "ज़रूर"/"जरूर" are the same word.
  * Tamil is agglutinative, so Tamil phrases match as substrings. They are kept long enough to avoid false hits
    (for example "எங்க" is NOT used alone because it is the start of "எங்கள்", "our"; "எப்ப" is the start of "எப்படி").
  * A hedge ("पता नहीं", "பார்க்கலாம்") always forces UNCLEAR, and conflicting categories also give UNCLEAR, so a
    wrong phrase here costs a clarification question rather than a wrong attendance record.
"""
from .taxonomy import Intent

PHRASES_HI_TA: dict[Intent, list[str]] = {
    Intent.CONFIRM: [
        # Hindi
        "हाँ", "हां", "जी हाँ", "जी हां", "ठीक है", "बिल्कुल", "ज़रूर", "पक्का", "मैं आऊँगा", "मैं आऊँगी", "आऊँगा",
        "आऊँगी", "आ जाऊँगा", "आ जाऊँगी", "आ रहा हूँ", "आ रही हूँ", "आ सकता हूँ", "आ सकती हूँ", "हम आएँगे",
        "मैं शामिल होऊँगा", "मैं शामिल होऊँगी",
        "haan", "haa", "ji haan", "theek hai", "thik hai", "zaroor", "bilkul", "pakka", "aaunga", "aaungi", "aunga",
        "aungi", "aa jaunga", "aa jaungi", "aa raha hoon", "aa rahi hoon", "aa sakta hoon", "aa sakti hoon",
        # Tamil
        "ஆமாம்", "ஆமா", "ஆம்", "சரி", "வருவேன்", "வருகிறேன்", "வருகிறோம்", "வருவோம்", "வந்துவிடுவேன்", "வந்திடுவேன்",
        "வந்துடுவேன்", "வரேன்", "வர்றேன்", "கண்டிப்பாக", "கண்டிப்பா", "நிச்சயமாக", "கலந்துகொள்வேன்",
        "கலந்து கொள்வேன்", "கலந்துக்குவேன்",
        "aamam", "aama", "sari", "varuven", "varen", "kandippa", "nichayama",
    ],
    Intent.DECLINE: [
        # Hindi
        "नहीं", "नही", "जी नहीं", "नहीं आऊँगा", "नहीं आऊँगी", "नहीं आ सकता", "नहीं आ सकती", "नहीं आ पाऊँगा",
        "नहीं आ पाऊँगी", "नहीं आना", "आ नहीं सकता", "आ नहीं सकती", "आ नहीं पाऊँगा", "आ नहीं पाऊँगी", "आऊँगा नहीं",
        "आऊँगी नहीं", "नहीं आ रहा", "नहीं आ रही", "रुचि नहीं", "दिलचस्पी नहीं", "इच्छा नहीं", "नहीं चाहिए",
        "नहीं धन्यवाद", "नहीं शुक्रिया",
        "nahi", "nahin", "nahi aaunga", "nahin aaunga", "nahi aaungi", "nahi aa sakta", "nahi aa sakti",
        "nahi aa paunga", "nahi aa paungi", "aa nahi sakta", "aa nahi sakti", "nahi aa raha", "nahi aa rahi",
        "interest nahi", "dilchaspi nahi",
        # Tamil
        "இல்லை", "இல்ல", "வேண்டாம்", "வரமாட்டேன்", "வர மாட்டேன்", "வரமுடியாது", "வர முடியாது", "வர இயலாது",
        "வர முடியலை", "வரமுடியலை", "வரவில்லை", "வர மாட்டோம்", "வரமாட்டோம்", "கலந்துகொள்ள மாட்டேன்",
        "கலந்துக்க மாட்டேன்", "கலந்துக்க முடியாது", "ஆர்வம் இல்லை", "விருப்பம் இல்லை",
        "illai", "illa", "vendam", "varamatten", "vara matten", "varamaatten", "vara maatten", "varamudiyathu",
        "vara mudiyathu", "vara mudiyadhu",
    ],
    Intent.CALLBACK: [
        # Hindi
        "बाद में फोन करना", "बाद में फोन करें", "बाद में फोन करो", "बाद में कॉल करना", "बाद में कॉल करें",
        "बाद में कॉल करो", "फिर से फोन करना", "फिर फोन करना", "दोबारा फोन करना", "कल फोन करना", "कल कॉल करना",
        "कल फोन करें", "कल कॉल करें", "थोड़ी देर बाद फोन", "थोड़ी देर में फोन", "अभी व्यस्त हूँ", "अभी बिजी हूँ",
        "मैं व्यस्त हूँ", "मैं बिजी हूँ", "अभी बात नहीं कर सकता", "अभी बात नहीं कर सकती", "अभी समय नहीं",
        "मीटिंग में हूँ", "गाड़ी चला रहा हूँ", "गाड़ी चला रही हूँ", "अभी नहीं",
        "baad mein phone", "baad me phone", "baad mein call", "baad me call", "baad mein baat", "kal phone karna",
        "kal call karna", "abhi busy hoon", "abhi vyast hoon", "abhi baat nahi kar sakta", "abhi baat nahi kar sakti",
        "abhi nahi", "meeting mein hoon", "gaadi chala raha hoon",
        # Tamil
        "பிறகு அழைக்கவும்", "பின்னர் அழைக்கவும்", "பிறகு கூப்பிடுங்க", "பின்னர் கூப்பிடுங்க", "அப்புறம் கூப்பிடுங்க",
        "அப்புறம் அழைங்க", "நாளை அழைக்கவும்", "நாளைக்கு கூப்பிடுங்க", "பிறகு கால் பண்ணுங்க",
        "அப்புறம் கால் பண்ணுங்க", "இப்போ பிஸி", "இப்போது பிஸி", "பிஸியா இருக்கேன்", "பிஸியாக இருக்கிறேன்",
        "வேலையா இருக்கேன்", "மீட்டிங்ல இருக்கேன்", "மீட்டிங்கில் இருக்கிறேன்", "இப்போ பேச முடியாது",
        "இப்போது பேச முடியாது", "இப்போ முடியாது",
        "piragu kooptunga", "appuram kooptunga", "appuram call pannunga", "piragu call pannunga",
        "naalaikku kooptunga", "ippo busy", "meeting la irukken", "ippo pesa mudiyathu",
    ],
    Intent.INFO: [
        # Hindi
        "कहाँ", "कहाँ है", "कहाँ होगा", "कब", "कब है", "कब होगा", "कितने बजे", "क्या समय है", "कौन सा दिन", "किस दिन",
        "कौन सी तारीख", "किस तारीख", "जगह कहाँ", "पता क्या है", "और जानकारी", "अधिक जानकारी", "ज़्यादा जानकारी",
        "जानकारी चाहिए", "आप कौन हैं", "कौन बोल रहा है", "यह किस बारे में है", "किस बारे में",
        "kahan", "kahan hai", "kab", "kab hai", "kitne baje", "kya time", "kaun si date", "address kya hai",
        "jagah kahan", "aur jaankari", "zyada jaankari", "aap kaun", "kis baare mein",
        # Tamil
        "எங்கே", "எங்க இருக்கு", "எங்க நடக்கு", "எப்போது", "எத்தனை மணிக்கு", "என்ன நேரம்", "எந்த தேதி", "என்ன தேதி",
        "எந்த நாள்", "மேலும் தகவல்", "கூடுதல் தகவல்", "விவரம் வேணும்", "யார் பேசுறீங்க", "யார் பேசுகிறீர்கள்",
        "இது எதைப் பற்றி", "முகவரி என்ன",
        "enge", "enga irukku", "eppodhu", "enna neram", "ethanai mani", "address enna", "yaar pesuringa",
    ],
    Intent.OPT_OUT: [
        # Hindi
        "फोन मत करो", "फोन मत करना", "फोन मत करें", "कॉल मत करो", "कॉल मत करना", "कॉल मत करें", "दोबारा फोन मत",
        "दोबारा कॉल मत", "फोन नहीं करना", "कॉल नहीं करना", "फोन न करें", "कॉल न करें", "फोन करना बंद", "कॉल करना बंद",
        "नंबर हटा दो", "नंबर हटाओ", "नंबर हटा दीजिए", "मेरा नंबर हटा", "लिस्ट से हटा", "मुझे फोन मत",
        "phone mat karo", "phone mat karna", "call mat karo", "call mat karna", "phone karna band", "call karna band",
        "number hata do", "number hatao", "number hata dijiye", "list se hata",
        # Tamil
        "அழைக்க வேண்டாம்", "கூப்பிட வேண்டாம்", "அழைக்காதீர்கள்", "அழைக்காதீங்க", "கூப்பிடாதீர்கள்", "கூப்பிடாதீங்க",
        "தொந்தரவு செய்யாதீர்கள்", "தொந்தரவு பண்ணாதீங்க", "என் எண்ணை நீக்கு", "எண்ணை நீக்கவும்", "எண்ணை நீக்கிடுங்க",
        "கால் பண்ணாதீங்க", "கால் பண்ண வேண்டாம்",
        "இனி+வேண்டாம்",       # "from now on ... don't": survives when the verb in the middle is misheard
        "kooptadheenga", "kooppidadheenga", "azhaikkadheenga", "call pannadheenga", "call panna vendam",
        "number remove pannunga", "thondaravu pannadheenga",
    ],
    Intent.ACK: [
        "धन्यवाद", "शुक्रिया", "समझ गया", "समझ गई", "नोट कर लिया", "dhanyavad", "shukriya", "samajh gaya", "samajh gayi",
        "நன்றி", "தேங்க்ஸ்", "புரிந்தது", "புரிஞ்சது", "nandri", "purinjathu",
    ],
}

HEDGES_HI_TA = [
    # Hindi
    "शायद", "पता नहीं", "मालूम नहीं", "पक्का नहीं", "देखता हूँ", "देखती हूँ", "देखूँगा", "देखूँगी", "देखेंगे",
    "सोचूँगा", "सोचूँगी", "सोचते हैं", "कोशिश करूँगा", "कोशिश करूँगी", "कोशिश करेंगे", "बताऊँगा", "बताऊँगी",
    "बता दूँगा", "बता दूँगी", "निर्भर करता है", "हो सकता है",
    "shayad", "pata nahi", "pata nahin", "maloom nahi", "pakka nahi", "dekhta hoon", "dekhti hoon", "dekhunga",
    "dekhungi", "dekhenge", "sochunga", "sochungi", "koshish karunga", "koshish karungi", "batata hoon", "bataunga",
    "bataungi", "ho sakta hai",
    # Tamil
    "ஒருவேளை", "பார்க்கலாம்", "பார்ப்போம்", "தெரியாது", "தெரியவில்லை", "யோசிக்கிறேன்", "யோசிச்சு சொல்றேன்",
    "முயற்சி செய்கிறேன்", "முயற்சிக்கிறேன்", "முயற்சி பண்றேன்", "சொல்றேன்", "சொல்கிறேன்", "உறுதியா தெரியாது",
    "இருக்கலாம்", "வரலாம்",
    "oruvelai", "paakalam", "parkalam", "theriyathu", "yosikkiren", "muyarchi", "solren", "solkiren",
]
