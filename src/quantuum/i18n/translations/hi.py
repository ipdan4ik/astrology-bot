"""Hindi (hi) UI translations. Keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": "🔮 Blueprint",
    "btn.profile": "👤 प्रोफ़ाइल",
    "btn.history": "📜 इतिहास",
    "btn.help": "ℹ️ सहायता",
    "btn.ask": "❓ ज्योतिषी से पूछें",
    "btn.transits": "🌌 गोचर",
    "btn.daily": "🔔 दैनिक राशिफल",
    "btn.buy": "💳 खरीदें",
    "btn.language": "🌐 भाषा",
    # -------------------------------------------------------------------------
    # Blueprint status words
    # -------------------------------------------------------------------------
    "status.pending": "प्रतीक्षारत",
    "status.calculating": "गणना हो रही है",
    "status.generating": "तैयार हो रहा है",
    "status.done": "तैयार",
    "status.failed": "त्रुटि",
    "status.refunded": "वापसी",
    # -------------------------------------------------------------------------
    # Help text
    # -------------------------------------------------------------------------
    "help.text": (
        "मैं आपके जन्म डेटा से व्यक्तिगत ज्योतिषीय विश्लेषण बनाता हूँ।\n\n"
        "मेनू:\n"
        "❓ ज्योतिषी से पूछें — अपनी जन्म कुंडली के संदर्भ में प्रश्न पूछें\n"
        "📖 विश्लेषण — Blueprint, ट्रांज़िट, BaZi, Human Design, टैरो आदि\n"
        "🔔 दैनिक राशिफल — हर दिन राशिफल की डिलीवरी\n"
        "👤 प्रोफ़ाइल — जन्म तिथि, समय और स्थान\n"
        "📜 इतिहास — सभी पिछले विश्लेषण\n"
        "💳 खरीदें — पैकेज और सदस्यता\n"
        "🌐 भाषा — इंटरफ़ेस भाषा बदलें\n"
        "🎁 मित्र को आमंत्रित करें — रेफरल लिंक\n"
        "🎁 उपहार — मित्र को क्रेडिट उपहार में दें\n\n"
        "सहायता: @quantuum_support"
    ),
    # -------------------------------------------------------------------------
    # Profile display
    # -------------------------------------------------------------------------
    "profile.title": "👤 आपकी प्रोफ़ाइल:",
    "profile.name": "नाम: {name}",
    "profile.birth_date": "जन्म तिथि: {birth_date}",
    "profile.birth_time": "समय: {birth_time}",
    "profile.place": "स्थान: {place}",
    # -------------------------------------------------------------------------
    # Profile screen messages
    # -------------------------------------------------------------------------
    "profile.empty": "प्रोफ़ाइल नहीं भरी गई।",
    "profile.not_found": "प्रोफ़ाइल नहीं मिली।",
    "profile.place.confirm": "मिला: {place}\n\nसही है?",
    "profile.place.not_found": "यह स्थान नहीं मिला। शहर / पता सुधारें या लोकेशन भेजें:",
    # -------------------------------------------------------------------------
    # Profile keyboard labels
    # -------------------------------------------------------------------------
    "profile.kb.fill": "📝 प्रोफ़ाइल भरें",
    "profile.kb.edit_name": "✏️ नाम",
    "profile.kb.edit_birth_date": "✏️ तिथि",
    "profile.kb.edit_birth_time": "✏️ समय",
    "profile.kb.edit_birth_place": "✏️ स्थान",
    "profile.kb.place_confirm": "✅ हाँ",
    "profile.kb.place_retry": "✏️ दूसरा पता",
    # -------------------------------------------------------------------------
    # Profile field prompts (edit flow)
    # -------------------------------------------------------------------------
    "profile.prompt.name": "अपना नाम दर्ज करें:",
    "profile.prompt.birth_date": "जन्म तिथि YYYY-MM-DD (उदा. 1980-06-24):",
    "profile.prompt.birth_time": "जन्म समय HH:MM (उदा. 10:00):",
    "profile.prompt.birth_place": "लोकेशन भेजें (📎 → Location) या शहर / पता लिखें:",
    # -------------------------------------------------------------------------
    # Profile field validation errors
    # -------------------------------------------------------------------------
    "profile.error.name_empty": "नाम खाली नहीं हो सकता।",
    "profile.error.birth_date_invalid": "तिथि समझ नहीं आई। प्रारूप YYYY-MM-DD।",
    "profile.error.birth_time_invalid": "समय समझ नहीं आया। प्रारूप HH:MM।",
    "profile.error.unknown_field": "अज्ञात फ़ील्ड।",
    "profile.field_edit_error": "{err}\nकृपया फिर प्रयास करें:",
    # -------------------------------------------------------------------------
    # Start / welcome
    # -------------------------------------------------------------------------
    "start.welcome": "नमस्ते! मैं आपका ज्योतिषीय विश्लेषण तैयार करूँगा ✨",
    # -------------------------------------------------------------------------
    # Main menu
    # -------------------------------------------------------------------------
    "menu.title": "मुख्य मेनू:",
    "menu.cancelled": "रद्द किया गया।",
    # -------------------------------------------------------------------------
    # Generate (blueprint request)
    # -------------------------------------------------------------------------
    "generate.no_profile": "पहले अपनी प्रोफ़ाइल भरें:",
    "generate.no_quota": "मुफ़्त विश्लेषण का उपयोग हो चुका है। पैकेज या सदस्यता खरीदें:",
    "generate.queued": "आपका विश्लेषण तैयार हो रहा है, इसमें लगभग एक मिनट लगेगा…",
    # -------------------------------------------------------------------------
    # Q&A astrologer
    # -------------------------------------------------------------------------
    "qa.ask_prompt": "ज्योतिषी को अपना प्रश्न भेजें:",
    "qa.thinking": "उत्तर सोच रहा हूँ… ⏳",
    "qa.no_profile": "पहले जन्म कुंडली प्रोफ़ाइल भरें (/profile)।",
    "qa.no_quota": "क्रेडिट समाप्त हो गए। ज्योतिषी से पूछने के लिए पैकेज या सदस्यता खरीदें:",
    "qa.too_long": "प्रश्न बहुत लंबा है (अधिकतम 1000 अक्षर)।",
    "qa.empty": "प्रश्न खाली है। कृपया प्रश्न लिखें:",
    # -------------------------------------------------------------------------
    # Transits
    # -------------------------------------------------------------------------
    "transit.thinking": "गोचर की गणना हो रही है… ⏳",
    "transit.no_profile": "पहले जन्म कुंडली प्रोफ़ाइल भरें (/profile)।",
    "transit.no_quota": "क्रेडिट समाप्त हो गए। गोचर देखने के लिए पैकेज या सदस्यता खरीदें:",
    "transit.failed": "गोचर की गणना नहीं हो सकी। बाद में फिर प्रयास करें।",
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": "🌟 आज का राशिफल",
    "daily.status_on": "दैनिक राशिफल चालू है। प्रेषण समय: {hour}:00 (आपका टाइमज़ोन)।",
    "daily.status_off": "दैनिक राशिफल बंद है।",
    "daily.not_subscriber": "दैनिक राशिफल सदस्यता सुविधा है। हर सुबह पाने के लिए सदस्यता लें:",
    "daily.no_profile": "पहले जन्म कुंडली प्रोफ़ाइल भरें (/profile)।",
    "daily.enabled": "दैनिक राशिफल चालू किया ✅",
    "daily.disabled": "दैनिक राशिफल बंद किया।",
    "daily.hour_set": "प्रेषण समय: {hour}:00 ✅",
    "daily.kb.turn_on": "🔔 चालू करें",
    "daily.kb.close": "✅ हो गया",
    "daily.kb.turn_off": "🔕 बंद करें",
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": "अभी कोई विश्लेषण नहीं है। पहला बनाने के लिए «🔮 Blueprint» दबाएँ।",
    "history.title": "📜 विश्लेषण इतिहास:",
    "history.label": "🔮 {date} · {status}",
    "history.detail_header": "🔮 Blueprint #{id}",
    "history.detail_status": "स्थिति: {status}",
    "history.detail_created": "बनाया: {created_at}",
    "history.detail_ready": "तैयार: {completed_at}",
    "history.not_found": "नहीं मिला",
    # -------------------------------------------------------------------------
    # History / blueprint detail keyboard labels
    # -------------------------------------------------------------------------
    "history.kb.download": "📥 .md डाउनलोड करें",
    "history.kb.preview": "👁 प्रीव्यू",
    "history.kb.back": "← वापस",
    "history.kb.prev_page": "← पिछला",
    "history.kb.next_page": "अगला →",
    "history.unavailable": "अनुपलब्ध",
    # -------------------------------------------------------------------------
    # Buy / payments
    # -------------------------------------------------------------------------
    "buy.menu_title": "क्या खरीदना है चुनें (भुगतान Telegram Stars ★ से):",
    "buy.no_plans": "अभी कोई प्लान उपलब्ध नहीं है। बाद में देखें।",
    "buy.plan_subscription": "⭐ {name} — {price}★",
    "buy.plan_package": "⭐ {name} · {count} विश्लेषण — {price}★",
    "buy.invoice_subscription": "{period_days} दिनों की सदस्यता",
    "buy.invoice_package": "पैकेज: {count} विश्लेषण",
    "buy.plan_unavailable": "यह प्लान अब उपलब्ध नहीं है।",
    "buy.payment_success": "भुगतान प्राप्त हुआ! एक्सेस सक्रिय हो गई। ✨",
    "buy.payment_already_credited": "यह भुगतान पहले ही जमा किया जा चुका है।",
    "buy.kb.open": "💳 विश्लेषण खरीदें",
    # -------------------------------------------------------------------------
    # Shared / generic
    # -------------------------------------------------------------------------
    "kb.cancel": "✖️ रद्द करें",
    "errors.queue_failed": "आपका अनुरोध कतार में नहीं डाला जा सका। आपका क्रेडिट लौटा दिया गया — कृपया थोड़ी देर में फिर से प्रयास करें।",
    # -------------------------------------------------------------------------
    # Master bot — owner onboarding
    # -------------------------------------------------------------------------
    "master.onboard.invite_invalid": "निमंत्रण अमान्य है या समाप्त हो गया है।",
    "master.onboard.slug_prompt": "स्वागत है! बॉट बनाते हैं। टेनेंट slug दर्ज करें (लैटिन अक्षर, बिना स्पेस){prefill}:",
    "master.onboard.slug_prefill": " (सुझाव: {slug})",
    "master.onboard.plain_start": "यह प्लेटफ़ॉर्म ऑनबोर्डिंग बॉट है। अपना बॉट बनाने के लिए निमंत्रण लिंक खोलें।",
    "master.onboard.slug_invalid": "Slug खाली नहीं होना चाहिए और उसमें स्पेस नहीं होनी चाहिए। फिर प्रयास करें:",
    "master.onboard.slug_taken": "यह slug पहले से लिया जा चुका है। दूसरा दर्ज करें:",
    "master.onboard.display_name_prompt": "उत्पाद का प्रदर्शन नाम (उदा. «Acme Astro»):",
    "master.onboard.display_name_empty": "नाम खाली नहीं होना चाहिए। फिर दर्ज करें:",
    "master.onboard.lang_prompt": "डिफ़ॉल्ट भाषा (दो-अक्षर कोड, उदा. ru या en):",
    "master.onboard.lang_invalid": "दो-अक्षर भाषा कोड आवश्यक है, उदा. ru। फिर दर्ज करें:",
    "master.onboard.confirm": (
        "विवरण जाँचें:\nslug: {slug}\nनाम: {display_name}\nभाषा: {language}\n\n"
        "बॉट बनाएँ?"
    ),
    "master.onboard.invite_gone": "निमंत्रण अब मान्य नहीं है।",
    "master.onboard.creating": "टेनेंट बना रहे हैं… बॉट का स्वचालित निर्माण जाँच रहे हैं।",
    "master.onboard.cancelled": "ऑनबोर्डिंग रद्द की गई।",
    "master.onboard.token_invalid": "यह वैध बॉट टोकन नहीं लगता। @BotFather से टोकन फिर भेजें:",
    "master.onboard.token_in_use": "यह बॉट पहले से किसी अन्य प्रोजेक्ट से जुड़ा है। कोई दूसरा बॉट इस्तेमाल करें।",
    "master.onboard.done": "हो गया! बॉट @{username} सक्रिय हो गया। वर्कर रिस्टार्ट होने के बाद उपलब्ध होगा।",
    "master.kb.cancel": "रद्द करें",
    "master.kb.create_bot": "बॉट बनाएँ",
    # -------------------------------------------------------------------------
    # Master bot — owner console
    # -------------------------------------------------------------------------
    "owner.tenants.empty": "आपके पास अभी कोई टेनेंट नहीं है। निमंत्रण लिंक से बॉट बनाएँ।",
    "owner.tenants.header": "आपके टेनेंट:",
    "owner.tenants.line": "• {display_name} (/{slug}) — {status}",
    "owner.tenants.hint": "\nप्रबंधन: /manage <slug>",
    "owner.manage.usage": "उपयोग: /manage <slug>",
    "owner.manage.not_found": "टेनेंट नहीं मिला या आपके पास अनुमति नहीं है।",
    "owner.manage.title": "प्रबंधन: {display_name} (/{slug}) — {status}",
    "owner.manage.kb.stats": "📊 आँकड़े",
    "owner.manage.kb.pause": "⏸ रोकें",
    "owner.manage.kb.resume": "▶️ फिर शुरू करें",
    "owner.manage.kb.transfer": "🔁 स्वामित्व स्थानांतरित करें",
    "owner.stats.text": (
        "📊 आँकड़े (पिछले {period_days} दिन)\n"
        "सक्रिय: {active_customers}, भुगतानकर्ता: {paid_customers}\n"
        "DAU/WAU/MAU: {dau}/{wau}/{mau}\n"
        "राजस्व: {revenue_cents}, MRR: {mrr_cents}\n"
        "अनुरोध: {requests_by_kind}"
    ),
    "owner.no_rights": "अनुमति नहीं है",
    "owner.pause.platform_blocked": "प्लेटफ़ॉर्म टेनेंट को रोका नहीं जा सकता",
    "owner.pause.done": "⏸ रोक दिया गया।",
    "owner.resume.done": "▶️ फिर शुरू किया गया।",
    "owner.manage.kb.delete": "🗑 हटाएँ",
    "owner.delete.prompt": (
        "⚠️ इससे बॉट स्थायी रूप से हट जाएगा और टेनेंट छिप जाएगा। "
        "पुष्टि के लिए slug भेजें: {slug}\n(या /cancel)"
    ),
    "owner.delete.mismatch": "Slug मेल नहीं खाता। {slug} फिर भेजें या /cancel।",
    "owner.delete.done": "🗑 बॉट हटा दिया गया।",
    "owner.delete.cancelled": "रद्द किया गया।",
    "owner.delete.platform_blocked": "प्लेटफ़ॉर्म टेनेंट को हटाया नहीं जा सकता",
    # -------------------------------------------------------------------------
    # Superadmin cabinet
    # -------------------------------------------------------------------------
    "admin.denied": "अधिकृत नहीं।",
    "admin.menu.title": "🛠 सुपरएडमिन पैनल",
    "admin.menu.kb.tenants": "🏢 बॉट्स",
    "admin.menu.kb.invites": "🎟 निमंत्रण",
    "admin.tenants.title": "सभी बॉट्स:",
    "admin.tenants.empty": "अभी कोई बॉट नहीं है।",
    "admin.tenant.title": "बॉट: {display_name} (/{slug}) — {status}",
    "admin.tenant.kb.stats": "📊 आँकड़े",
    "admin.tenant.kb.suspend": "⏸ निलंबित करें",
    "admin.tenant.kb.resume": "▶️ फिर शुरू करें",
    "admin.tenant.kb.delete": "🗑 हटाएँ",
    "admin.kb.back": "⬅️ वापस",
    "admin.tenant.suspended": "⏸ बॉट निलंबित किया गया।",
    "admin.tenant.resumed": "▶️ बॉट फिर शुरू किया गया।",
    "admin.invites.title": "सक्रिय निमंत्रण:",
    "admin.invites.empty": "कोई सक्रिय निमंत्रण नहीं।",
    "admin.invites.kb.new": "➕ नया निमंत्रण",
    "admin.invite.kb.revoke": "🗑 रद्द करें",
    "admin.invite.created": "निमंत्रण बनाया गया:\n{link}",
    "admin.invite.revoked": "निमंत्रण रद्द किया गया।",
    "admin.stale": "नहीं मिला — सूची ताज़ा की गई।",
    # -------------------------------------------------------------------------
    # Transfer
    # -------------------------------------------------------------------------
    "owner.transfer.usage": "उपयोग: /transfer <slug>",
    "owner.transfer.not_owner": "टेनेंट नहीं मिला या आप स्वामी नहीं हैं।",
    "owner.transfer.prompt": (
        "नए स्वामी का Telegram ID (एक संख्या) भेजें। "
        "उनका इस टेनेंट में खाता होना चाहिए (आपका बॉट शुरू किया हो)।"
    ),
    "owner.transfer.cancelled": "रद्द किया गया।",
    "owner.transfer.target_invalid": "संख्यात्मक Telegram ID आवश्यक है। फिर प्रयास करें या /cancel।",
    "owner.transfer.no_rights_anymore": "आपके पास अब स्थानांतरण की अनुमति नहीं है।",
    "owner.transfer.no_account": (
        "इस उपयोगकर्ता का टेनेंट में खाता नहीं है। "
        "उन्हें पहले आपका बॉट शुरू करना होगा।"
    ),
    "owner.transfer.done": "✅ हो गया। स्वामित्व स्थानांतरित किया गया।",
    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    "lang.prompt": "अपनी भाषा चुनें:",
    "lang.changed": "भाषा अपडेट की गई।",
    # -------------------------------------------------------------------------
    # Onboarding flow
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": "अपना पूरा नाम दर्ज करें (जैसा जन्म प्रमाण पत्र पर है):",
    "onb.error.full_name": "नाम समझ नहीं आया। अपना पूरा नाम टेक्स्ट में दर्ज करें:",
    "onb.prompt.birth_date": "जन्म तिथि YYYY-MM-DD प्रारूप में (उदा. 1980-06-24):",
    "onb.error.birth_date": "तिथि समझ नहीं आई। प्रारूप YYYY-MM-DD:",
    "onb.prompt.birth_time": "जन्म समय HH:MM (उदा. 10:00):",
    "onb.error.birth_time": "समय समझ नहीं आया। प्रारूप HH:MM:",
    "onb.prompt.birth_place": (
        "जन्म स्थान: लोकेशन भेजें (📎 → Location, मानचित्र पर पिन लगा सकते हैं) "
        "या शहर / पते का हिस्सा लिखें:"
    ),
    "onb.done": "हो गया! आपका प्रोफ़ाइल सहेजा गया। नीचे मेनू में «🔮 Blueprint» दबाएं।",
    # Owner console — user management
    "owner.manage.kb.users": "👥 उपयोगकर्ता",
    "owner.users.header": "{display_name} के उपयोगकर्ता:",
    "owner.users.empty": "अभी कोई उपयोगकर्ता नहीं है।",
    "owner.users.row": "{name} · {credits}💎",
    "owner.users.unnamed": "उपयोगकर्ता #{id}",
    "owner.users.nav.prev": "◀️",
    "owner.users.nav.next": "▶️",
    "owner.user.card": (
        "👤 {name}\nTelegram ID: {tg_id}\nक्रेडिट: {credits}💎\n"
        "सदस्यता: {subscription}\nस्थिति: {status}"
    ),
    "owner.user.card.banned": "🚫 प्रतिबंधित। कारण: {reason}",
    "owner.user.status.active": "सक्रिय",
    "owner.user.status.banned": "प्रतिबंधित",
    "owner.user.not_found": "उपयोगकर्ता नहीं मिला।",
    "owner.user.kb.grant": "💎 क्रेडिट समायोजित करें",
    "owner.user.kb.ban": "🚫 प्रतिबंधित करें",
    "owner.user.kb.unban": "✅ प्रतिबंध हटाएँ",
    "owner.user.kb.back": "⬅️ सूची पर जाएँ",
    "owner.user.grant.prompt": "क्रेडिट की संख्या दर्ज करें (ऋणात्मक भी हो सकती है, उदा. -3):",
    "owner.user.grant.invalid": "समझ नहीं आया। एक पूर्ण संख्या दर्ज करें, उदा. 5 या -2।",
    "owner.user.grant.done": "हो गया। नई शेष राशि: {credits}💎।",
    "owner.user.ban.prompt": "प्रतिबंध का कारण दर्ज करें:",
    "owner.user.ban.invalid": "कारण खाली नहीं हो सकता। कृपया कारण दर्ज करें:",
    "owner.user.ban.done": "उपयोगकर्ता को प्रतिबंधित कर दिया गया।",
    "owner.user.ban.staff_blocked": "आप किसी स्वामी या व्यवस्थापक को प्रतिबंधित नहीं कर सकते।",
    "owner.user.unban.done": "उपयोगकर्ता का प्रतिबंध हटा दिया गया।",
    "owner.user.cancelled": "रद्द किया गया।",
    "account.banned.notice": "🚫 बॉट तक आपकी पहुँच प्रतिबंधित है। कारण: {reason}",
    # -------------------------------------------------------------------------
    # Readings submenu
    # -------------------------------------------------------------------------
    "btn.readings": "📖 पाठ",
    "readings.menu.title": "कौन सा पाठ चाहिए?",
    "readings.queued": "आपका पाठ तैयार हो रहा है। एक मिनट लगेगा।",
    "readings.no_profile": "पहले अपना जन्म विवरण भरें।",
    "readings.no_quota": "क्रेडिट उपलब्ध नहीं हैं। जारी रखने के लिए पैकेज खरीदें।",
    "readings.kind.bazi": "🐉 BaZi",
    "readings.kind.numerology": "🔢 Numerology",
    "readings.kind.human_design": "🧬 Human Design",
    "readings.kind.astrology": "☉ Astrology",
    "readings.kind.vedic": "🕉 Vedic",
    "readings.kind.gene_keys": "🗝 Gene Keys",
    "readings.kind.mayan": "🌀 Mayan",
    "readings.kind.aspects": "✦ Aspects",
    # -------------------------------------------------------------------------
    # History — recent readings section
    # -------------------------------------------------------------------------
    "history.readings_title": "📖 हाल के पाठ",
    "history.reading_row": "{kind} · {status} · {date}",
    "history.download": "⬇️ डाउनलोड",
    # -------------------------------------------------------------------------
    # Content moderation
    # -------------------------------------------------------------------------
    "moderation.self_harm": "अगर आप अभी कठिन समय में हैं, तो कृपया सहायता लें: {helpline_url}. मैं किसी विशेषज्ञ की जगह नहीं ले सकता, पर मैं यहाँ हूँ.",
    "moderation.violence": "यह सवाल मेरी मदद की सीमा के बाहर है.",
    "moderation.hate": "मैं इसके लिए नहीं हूँ.",
    "moderation.medical": "यह डॉक्टर के लिए सवाल है, ज्योतिष के लिए नहीं. मैं चिकित्सकीय सलाह नहीं देता.",
    "moderation.legal": "यह वकील के लिए है. मैं ऊर्जा और चक्रों की बात करता हूँ, कानूनी जोखिमों की नहीं.",
    "moderation.blocked_generic": "यह अनुरोध संसाधित नहीं किया जा सकता.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
    "feature.disabled_generic": "यह सुविधा इस बॉट पर उपलब्ध नहीं है.",
    "owner.features.title": "⚙️ सुविधाएं",
    "owner.features.btn": "⚙️ सुविधाएं",
    "owner.features.section.readings": "— रीडिंग्स —",
    "owner.features.label.qa": "प्रश्न-उत्तर",
    "owner.features.label.blueprint": "रीडिंग",
    "owner.features.label.transits": "ट्रांज़िट",
    "owner.features.label.daily": "दैनिक",
    # White-label branding (SP3)
    "brand.signature": "",
    "owner.branding.btn": "🎨 ब्रांडिंग",
    "owner.branding.title": "🎨 ब्रांडिंग (भाषा: {language})",
    "owner.branding.label.name": "नाम",
    "owner.branding.label.welcome": "स्वागत",
    "owner.branding.label.help": "मदद",
    "owner.branding.label.signature": "हस्ताक्षर",
    "owner.branding.prompt": (
        "**{label}** ({language}) के लिए नया पाठ भेजें, "
        "या रखने के लिए /cancel, डिफ़ॉल्ट पर पुनर्स्थापित करने के लिए /reset।"
    ),
    "owner.branding.saved": "✅ अपडेट किया गया।",
    "owner.branding.reset_done": "↩️ डिफ़ॉल्ट पर पुनर्स्थापित।",
    "owner.branding.cancelled": "रद्द किया गया।",
    "owner.branding.too_long": "बहुत लंबा: {actual} अक्षर (अधिकतम {limit})।",
    "owner.branding.bad_format": "नाम 1-64 अक्षर का होना चाहिए, बिना लाइन ब्रेक के।",
    "owner.branding.empty_value": "खाली मान की अनुमति नहीं है। साफ़ करने के लिए /reset का उपयोग करें।",
    "owner.branding.preview_empty": "(खाली)",
    # -------------------------------------------------------------------------
    # Referral links (SP4)
    # -------------------------------------------------------------------------
    "btn.invite": "🎁 दोस्त को आमंत्रित करें",
    "invite.title": "इस बॉट में दोस्तों को आमंत्रित करें।",
    "invite.link_label": "आपका लिंक",
    "invite.earned": "अर्जित: {friends} दोस्तों से {credits} क्रेडिट।",
    "invite.share_text": "इस बॉट को आज़माएं",
    "invite.disabled": "इस बॉट में रेफरल प्रोग्राम अक्षम है।",
    "invite.unknown_code": "रेफरल लिंक पहचाना नहीं गया। बिना बोनस के जारी है।",
    "owner.referrals.title": "रेफरल प्रोग्राम",
    "owner.referrals.current_value": "वर्तमान पुरस्कार: {value} क्रेडिट।",
    "owner.referrals.prompt": "पुरस्कार बदलने के लिए 0 से {max} के बीच पूर्णांक भेजें।",
    "owner.referrals.saved": "सहेजा गया: {value} क्रेडिट।",
    "owner.referrals.reset": "डिफ़ॉल्ट पर रीसेट ({value})।",
    "owner.referrals.too_large": "मान 0 से {max} की सीमा में होना चाहिए।",
    "owner.referrals.not_a_number": "एक पूर्णांक भेजें।",
    "owner.referrals.cancel_hint": "रद्द करने के लिए /cancel भेजें।",
    "owner.referrals.menu_button": "रेफरल",
    # -------------------------------------------------------------------------
    # Gift-a-friend (SP5)
    # -------------------------------------------------------------------------
    "btn.gift": "🎁 उपहार",
    "gift.title": "मित्र को उपहार दें",
    "gift.balance_line": "उपलब्ध: {balance}",
    "gift.amount_prompt": "उपहार राशि दर्ज करें (1–{max}):",
    "gift.cancelled": "रद्द किया गया।",
    "gift.cancel_hint": "रद्द करने के लिए /cancel भेजें।",
    "gift.too_small": "न्यूनतम 1 क्रेडिट।",
    "gift.too_large": "अधिकतम {max} क्रेडिट।",
    "gift.not_a_number": "यह संख्या नहीं है। पूर्णांक दर्ज करें।",
    "gift.no_balance": "उपहार देने के लिए आपके पास क्रेडिट नहीं हैं।",
    "gift.created": "{amount} क्रेडिट का उपहार तैयार है!\n\nलिंक: {link}",
    "gift.share_text": "तुम्हारे लिए उपहार! क्रेडिट प्राप्त करने के लिए बॉट खोलो।",
    "gift.disabled": "उपहार अभी उपलब्ध नहीं हैं।",
    "gift.received": "आपको उपहार मिला: {amount} क्रेडिट!",
    "gift.self_blocked": "आप अपना उपहार स्वयं प्राप्त नहीं कर सकते।",
    "gift.history_title": "आपके उपहार",
    "gift.history_empty": "अभी खाली।",
    "gift.history_row": "{date} — {amount} क्र. — {status}",
    "gift.status.active": "लंबित",
    "gift.status.claimed": "प्राप्त",
    "gift.status.refunded": "वापस",
    "gift.btn.create_new": "नया बनाएं",
    "owner.gifts.menu_button": "उपहार",
    "owner.gifts.title": "उपहार",
    "owner.gifts.current_value": "उपहार अवधि: {value} दिन।",
    "owner.gifts.prompt": "उपहार अवधि दिनों में दर्ज करें ({min}–{max}):",
    "owner.gifts.saved": "सहेजा गया।",
    "owner.gifts.reset": "डिफ़ॉल्ट पर रीसेट।",
    "owner.gifts.too_small": "न्यूनतम {min} दिन।",
    "owner.gifts.too_large": "अधिकतम {max} दिन।",
    "owner.gifts.not_a_number": "पूर्णांक दर्ज करें।",
    "owner.gifts.cancel_hint": "रद्द करने के लिए /cancel भेजें।",
    # SP6 — Divination (Tarot + I-Ching)
    "readings.kind.tarot": "🔮 टैरो",
    "readings.kind.iching": "☯ आई चिंग",
    "divination.question_prompt": "अपना प्रश्न पूछें या /skip भेजें:",
    "divination.skip_btn": "छोड़ें",
    "divination.no_question": "(कोई प्रश्न नहीं)",
    "tarot.position.past": "अतीत",
    "tarot.position.present": "वर्तमान",
    "tarot.position.future": "भविष्य",
    "tarot.orientation.upright": "सीधी",
    "tarot.orientation.reversed": "उल्टी",
    "iching.judgment_label": "निर्णय",
    "iching.image_label": "छवि",
    "iching.changing_line_label": "बदलती रेखा {n}",
    "iching.transformed_label": "बदलता है",
    # Console UX nav + provisioning
    "owner.manage.kb.back": "⬅️ मेनू पर वापस",
    "owner.features.label.referrals": "रेफ़रल",
    "owner.features.label.gifts": "उपहार",
    "master.provision.manual_prompt": (
        "स्वचालित बॉट निर्माण उपलब्ध नहीं है। @BotFather के ज़रिए एक नया बॉट बनाएँ "
        "और उसका टोकन यहाँ एक ही संदेश में भेजें।"
    ),
    "master.provision.managed_prompt": (
        "नीचे दिए बटन पर टैप करें — Telegram बॉट बना देगा और मैं उसे अपने आप उठा लूँगा। "
        "उपयोगकर्ता नाम को निर्माण स्क्रीन पर समायोजित किया जा सकता है।"
    ),
    "master.provision.managed_button": "🤖 बॉट बनाएँ",
}
