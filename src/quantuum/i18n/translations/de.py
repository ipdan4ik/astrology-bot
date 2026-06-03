"""German (de) UI translations. Keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": "🔮 Blueprint",
    "btn.profile": "👤 Profil",
    "btn.history": "📜 Verlauf",
    "btn.help": "ℹ️ Hilfe",
    "btn.ask": "❓ Astrologen fragen",
    "btn.transits": "🌌 Transite",
    "btn.daily": "🔔 Tageshoroskop",
    "btn.buy": "💳 Kaufen",
    "btn.language": "🌐 Sprache",
    # -------------------------------------------------------------------------
    # Blueprint status words
    # -------------------------------------------------------------------------
    "status.pending": "in der Warteschlange",
    "status.calculating": "berechne",
    "status.generating": "generiere",
    "status.done": "fertig",
    "status.failed": "Fehler",
    "status.refunded": "erstattet",
    # -------------------------------------------------------------------------
    # Help text
    # -------------------------------------------------------------------------
    "help.text": (
        "Ich erstelle persönliche astrologische Analysen aus deinen Geburtsdaten.\n\n"
        "Menü:\n"
        "❓ Astrologen fragen — Frage mit deinem Geburtskontext\n"
        "📖 Analysen — Blueprint, Transite, BaZi, Human Design, Tarot u.v.m.\n"
        "🔔 Tageshoroskop — tägliche Horoskop-Lieferung\n"
        "👤 Profil — Geburtsdatum, -zeit und -ort\n"
        "📜 Verlauf — alle vergangenen Analysen\n"
        "💳 Kaufen — Pakete und Abonnements\n"
        "🌐 Sprache — Sprache der Benutzeroberfläche ändern\n"
        "🎁 Freund einladen — Empfehlungslink\n"
        "🎁 Geschenk — einem Freund Credits schenken\n\n"
        "Support: @quantuum_support"
    ),
    # -------------------------------------------------------------------------
    # Profile display
    # -------------------------------------------------------------------------
    "profile.title": "👤 Dein Profil:",
    "profile.name": "Name: {name}",
    "profile.birth_date": "Geburtsdatum: {birth_date}",
    "profile.birth_time": "Uhrzeit: {birth_time}",
    "profile.place": "Ort: {place}",
    # -------------------------------------------------------------------------
    # Profile screen messages
    # -------------------------------------------------------------------------
    "profile.empty": "Profil nicht ausgefüllt.",
    "profile.not_found": "Profil nicht gefunden.",
    "profile.place.confirm": "Gefunden: {place}\n\nKorrekt?",
    "profile.place.not_found": "Diesen Ort konnte ich nicht finden. Bitte präzisiere Stadt / Adresse oder sende deinen Standort:",
    # -------------------------------------------------------------------------
    # Profile keyboard labels
    # -------------------------------------------------------------------------
    "profile.kb.fill": "📝 Profil ausfüllen",
    "profile.kb.edit_name": "✏️ Name",
    "profile.kb.edit_birth_date": "✏️ Datum",
    "profile.kb.edit_birth_time": "✏️ Uhrzeit",
    "profile.kb.edit_birth_place": "✏️ Ort",
    "profile.kb.place_confirm": "✅ Ja",
    "profile.kb.place_retry": "✏️ Andere Adresse",
    # -------------------------------------------------------------------------
    # Profile field prompts (edit flow)
    # -------------------------------------------------------------------------
    "profile.prompt.name": "Gib deinen Namen ein:",
    "profile.prompt.birth_date": "Geburtsdatum JJJJ-MM-TT (z. B. 1980-06-24):",
    "profile.prompt.birth_time": "Geburtszeit HH:MM (z. B. 10:00):",
    "profile.prompt.birth_place": "Sende deinen Standort (📎 → Standort) oder gib eine Stadt / Adresse ein:",
    # -------------------------------------------------------------------------
    # Profile field validation errors
    # -------------------------------------------------------------------------
    "profile.error.name_empty": "Der Name darf nicht leer sein.",
    "profile.error.birth_date_invalid": "Datum nicht erkannt. Format JJJJ-MM-TT.",
    "profile.error.birth_time_invalid": "Uhrzeit nicht erkannt. Format HH:MM.",
    "profile.error.unknown_field": "Unbekanntes Feld.",
    "profile.field_edit_error": "{err}\nBitte erneut versuchen:",
    # -------------------------------------------------------------------------
    # Start / welcome
    # -------------------------------------------------------------------------
    "start.welcome": "Hallo! Ich erstelle deine astrologische Analyse ✨",
    # -------------------------------------------------------------------------
    # Main menu
    # -------------------------------------------------------------------------
    "menu.title": "Hauptmenü:",
    "menu.cancelled": "Abgebrochen.",
    # -------------------------------------------------------------------------
    # Generate (blueprint request)
    # -------------------------------------------------------------------------
    "generate.no_profile": "Bitte fülle zuerst dein Profil aus:",
    "generate.no_quota": "Deine kostenlose Analyse wurde bereits verwendet. Kaufe ein Paket oder ein Abonnement:",
    "generate.queued": "Ich erstelle deine Analyse, das dauert etwa eine Minute…",
    # -------------------------------------------------------------------------
    # Q&A astrologer
    # -------------------------------------------------------------------------
    "qa.ask_prompt": "Sende deine Frage an den Astrologen:",
    "qa.thinking": "Ich denke über die Antwort nach… ⏳",
    "qa.no_profile": "Fülle zuerst dein Geburtshoroskop-Profil aus (/profile).",
    "qa.no_quota": "Dein Guthaben ist aufgebraucht. Kaufe ein Paket oder Abonnement, um den Astrologen zu fragen:",
    "qa.too_long": "Die Frage ist zu lang (max. 1000 Zeichen).",
    "qa.empty": "Leere Frage. Bitte gib deine Frage ein:",
    # -------------------------------------------------------------------------
    # Transits
    # -------------------------------------------------------------------------
    "transit.thinking": "Ich berechne deine Transite… ⏳",
    "transit.no_profile": "Fülle zuerst dein Geburtshoroskop-Profil aus (/profile).",
    "transit.no_quota": "Dein Guthaben ist aufgebraucht. Kaufe ein Paket oder Abonnement, um deine Transite zu sehen:",
    "transit.failed": "Transite konnten nicht berechnet werden. Versuche es später erneut.",
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": "🌟 Heutiges Horoskop",
    "daily.status_on": "Tageshoroskop ist eingeschaltet. Lieferzeit: {hour}:00 (deine Zeitzone).",
    "daily.status_off": "Tageshoroskop ist ausgeschaltet.",
    "daily.not_subscriber": "Das Tageshoroskop ist ein Abonnement-Feature. Abonniere, um es jeden Morgen zu erhalten:",
    "daily.no_profile": "Fülle zuerst dein Geburtshoroskop-Profil aus (/profile).",
    "daily.enabled": "Tageshoroskop aktiviert ✅",
    "daily.disabled": "Tageshoroskop deaktiviert.",
    "daily.hour_set": "Lieferzeit: {hour}:00 ✅",
    "daily.kb.turn_on": "🔔 Aktivieren",
    "daily.kb.close": "✅ Fertig",
    "daily.kb.turn_off": "🔕 Deaktivieren",
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": "Noch keine Analysen. Tippe auf «🔮 Blueprint», um deine erste zu erstellen.",
    "history.title": "📜 Analyseverlauf:",
    "history.label": "🔮 {date} · {status}",
    "history.detail_header": "🔮 Blueprint #{id}",
    "history.detail_status": "Status: {status}",
    "history.detail_created": "Erstellt: {created_at}",
    "history.detail_ready": "Fertig: {completed_at}",
    "history.not_found": "Nicht gefunden",
    # -------------------------------------------------------------------------
    # History / blueprint detail keyboard labels
    # -------------------------------------------------------------------------
    "history.kb.download": "📥 .md herunterladen",
    "history.kb.preview": "👁 Vorschau",
    "history.kb.back": "← Zurück",
    "history.kb.prev_page": "← Vorherige",
    "history.kb.next_page": "Weiter →",
    "history.unavailable": "Nicht verfügbar",
    # -------------------------------------------------------------------------
    # Buy / payments
    # -------------------------------------------------------------------------
    "buy.menu_title": "Was möchtest du kaufen? (Zahlung per Telegram Stars ★):",
    "buy.no_plans": "Noch keine Pläne verfügbar. Schau später vorbei.",
    "buy.plan_subscription": "⭐ {name} — {price}★",
    "buy.plan_package": "⭐ {name} · {count} Analysen — {price}★",
    "buy.invoice_subscription": "Abonnement für {period_days} Tage",
    "buy.invoice_package": "Paket: {count} Analysen",
    "buy.plan_unavailable": "Dieser Plan ist nicht mehr verfügbar.",
    "buy.payment_success": "Zahlung eingegangen! Zugang aktiviert. ✨",
    "buy.payment_already_credited": "Diese Zahlung wurde bereits gutgeschrieben.",
    "buy.kb.open": "💳 Analysen kaufen",
    # -------------------------------------------------------------------------
    # Shared / generic
    # -------------------------------------------------------------------------
    "kb.cancel": "✖️ Abbrechen",
    "errors.queue_failed": "Anfrage konnte nicht eingereiht werden. Dein Guthaben wurde erstattet — bitte versuche es gleich noch einmal.",
    # -------------------------------------------------------------------------
    # Master bot — owner onboarding
    # -------------------------------------------------------------------------
    "master.onboard.invite_invalid": "Die Einladung ist ungültig oder abgelaufen.",
    "master.onboard.slug_prompt": "Willkommen! Lass uns einen Bot erstellen. Gib den Tenant-Slug ein (lateinische Buchstaben, keine Leerzeichen){prefill}:",
    "master.onboard.slug_prefill": " (Vorschlag: {slug})",
    "master.onboard.plain_start": "Dies ist der Plattform-Onboarding-Bot. Öffne einen Einladungslink, um deinen eigenen Bot zu erstellen.",
    "master.onboard.slug_invalid": "Der Slug darf nicht leer sein oder Leerzeichen enthalten. Bitte erneut versuchen:",
    "master.onboard.slug_taken": "Dieser Slug ist bereits vergeben. Gib einen anderen ein:",
    "master.onboard.display_name_prompt": "Anzeigename des Produkts (z. B. «Acme Astro»):",
    "master.onboard.display_name_empty": "Der Name darf nicht leer sein. Bitte erneut eingeben:",
    "master.onboard.lang_prompt": "Standardsprache (zweistelliger Code, z. B. ru oder en):",
    "master.onboard.lang_invalid": "Ein zweistelliger Sprachcode ist erforderlich, z. B. ru. Bitte erneut eingeben:",
    "master.onboard.confirm": (
        "Daten prüfen:\nslug: {slug}\nName: {display_name}\nSprache: {language}\n\n"
        "Bot erstellen?"
    ),
    "master.onboard.invite_gone": "Die Einladung ist nicht mehr gültig.",
    "master.onboard.creating": "Tenant wird erstellt… Prüfe, ob der Bot automatisch angelegt werden kann.",
    "master.onboard.cancelled": "Onboarding abgebrochen.",
    "master.onboard.token_invalid": "Das sieht nicht wie ein gültiger Bot-Token aus. Sende den Token von @BotFather erneut:",
    "master.onboard.token_in_use": "Dieser Bot ist bereits mit einem anderen Projekt verknüpft. Verwende einen anderen Bot.",
    "master.onboard.done": "Fertig! Bot @{username} ist aktiviert. Er wird nach dem Neustart des Workers verfügbar.",
    "master.kb.cancel": "Abbrechen",
    "master.kb.create_bot": "Bot erstellen",
    # -------------------------------------------------------------------------
    # Master bot — owner console
    # -------------------------------------------------------------------------
    "owner.tenants.empty": "Du hast noch keine Tenants. Erstelle einen Bot über einen Einladungslink.",
    "owner.tenants.header": "Deine Tenants:",
    "owner.tenants.line": "• {display_name} (/{slug}) — {status}",
    "owner.tenants.hint": "\nVerwaltung: /manage <slug>",
    "owner.manage.usage": "Verwendung: /manage <slug>",
    "owner.manage.not_found": "Tenant nicht gefunden oder keine Berechtigung.",
    "owner.manage.title": "Verwaltung: {display_name} (/{slug}) — {status}",
    "owner.manage.kb.stats": "📊 Statistik",
    "owner.manage.kb.pause": "⏸ Pausieren",
    "owner.manage.kb.resume": "▶️ Fortsetzen",
    "owner.manage.kb.transfer": "🔁 Eigentümer übertragen",
    "owner.stats.text": (
        "📊 Statistik (letzte {period_days} Tage)\n"
        "Aktiv: {active_customers}, zahlend: {paid_customers}\n"
        "DAU/WAU/MAU: {dau}/{wau}/{mau}\n"
        "Umsatz: {revenue_cents}, MRR: {mrr_cents}\n"
        "Anfragen: {requests_by_kind}"
    ),
    "owner.no_rights": "Keine Berechtigung",
    "owner.pause.platform_blocked": "Der Plattform-Tenant kann nicht pausiert werden",
    "owner.pause.done": "⏸ Pausiert.",
    "owner.resume.done": "▶️ Fortgesetzt.",
    "owner.manage.kb.delete": "🗑 Löschen",
    "owner.delete.prompt": (
        "⚠️ Dadurch wird der Bot dauerhaft gelöscht und der Tenant ausgeblendet. "
        "Zur Bestätigung sende den Slug: {slug}\n(oder /cancel)"
    ),
    "owner.delete.mismatch": "Slug stimmt nicht überein. Sende {slug} erneut oder /cancel.",
    "owner.delete.done": "🗑 Bot gelöscht.",
    "owner.delete.cancelled": "Abgebrochen.",
    "owner.delete.platform_blocked": "Der Plattform-Tenant kann nicht gelöscht werden",
    # -------------------------------------------------------------------------
    # Superadmin cabinet
    # -------------------------------------------------------------------------
    "admin.denied": "Keine Berechtigung.",
    "admin.menu.title": "🛠 Superadmin-Panel",
    "admin.menu.kb.tenants": "🏢 Bots",
    "admin.menu.kb.invites": "🎟 Einladungen",
    "admin.tenants.title": "Alle Bots:",
    "admin.tenants.empty": "Noch keine Bots.",
    "admin.tenant.title": "Bot: {display_name} (/{slug}) — {status}",
    "admin.tenant.kb.stats": "📊 Statistik",
    "admin.tenant.kb.suspend": "⏸ Aussetzen",
    "admin.tenant.kb.resume": "▶️ Fortsetzen",
    "admin.tenant.kb.delete": "🗑 Löschen",
    "admin.kb.back": "⬅️ Zurück",
    "admin.tenant.suspended": "⏸ Bot ausgesetzt.",
    "admin.tenant.resumed": "▶️ Bot fortgesetzt.",
    "admin.invites.title": "Aktive Einladungen:",
    "admin.invites.empty": "Keine aktiven Einladungen.",
    "admin.invites.kb.new": "➕ Neue Einladung",
    "admin.invite.kb.revoke": "🗑 Widerrufen",
    "admin.invite.created": "Einladung erstellt:\n{link}",
    "admin.invite.revoked": "Einladung widerrufen.",
    "admin.stale": "Nicht gefunden — Liste aktualisiert.",
    # -------------------------------------------------------------------------
    # Transfer ownership
    # -------------------------------------------------------------------------
    "owner.transfer.usage": "Verwendung: /transfer <slug>",
    "owner.transfer.not_owner": "Tenant nicht gefunden oder du bist nicht der Eigentümer.",
    "owner.transfer.prompt": (
        "Sende die Telegram-ID des neuen Eigentümers (eine Zahl). "
        "Er muss bereits ein Konto in diesem Tenant haben (deinen Bot gestartet haben)."
    ),
    "owner.transfer.cancelled": "Abgebrochen.",
    "owner.transfer.target_invalid": "Eine numerische Telegram-ID ist erforderlich. Erneut versuchen oder /cancel.",
    "owner.transfer.no_rights_anymore": "Du hast keine Berechtigung mehr zur Übertragung.",
    "owner.transfer.no_account": (
        "Dieser Nutzer hat kein Konto im Tenant. "
        "Er muss zuerst deinen Bot starten."
    ),
    "owner.transfer.done": "✅ Fertig. Eigentümerschaft übertragen.",
    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    "lang.prompt": "Wähle deine Sprache:",
    "lang.changed": "Sprache aktualisiert.",
    # -------------------------------------------------------------------------
    # Onboarding flow
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": "Gib deinen vollständigen Namen ein (wie in der Geburtsurkunde):",
    "onb.error.full_name": "Name nicht erkannt. Gib deinen vollständigen Namen als Text ein:",
    "onb.prompt.birth_date": "Geburtsdatum im Format JJJJ-MM-TT (z. B. 1980-06-24):",
    "onb.error.birth_date": "Datum nicht erkannt. Format JJJJ-MM-TT:",
    "onb.prompt.birth_time": "Geburtszeit HH:MM (z. B. 10:00):",
    "onb.error.birth_time": "Uhrzeit nicht erkannt. Format HH:MM:",
    "onb.prompt.birth_place": (
        "Geburtsort: Sende deinen Standort (📎 → Standort, du kannst eine Markierung auf der "
        "Karte setzen) oder gib eine Stadt / Teil einer Adresse ein:"
    ),
    "onb.done": "Fertig! Dein Profil ist gespeichert. Tippe auf «🔮 Blueprint» im Menü unten.",
    # Owner console — user management
    "owner.manage.kb.users": "👥 Nutzer",
    "owner.users.header": "Nutzer von {display_name}:",
    "owner.users.empty": "Noch keine Nutzer.",
    "owner.users.row": "{name} · {credits}💎",
    "owner.users.unnamed": "Nutzer #{id}",
    "owner.users.nav.prev": "◀️",
    "owner.users.nav.next": "▶️",
    "owner.user.card": (
        "👤 {name}\nTelegram ID: {tg_id}\nGuthaben: {credits}💎\n"
        "Abonnement: {subscription}\nStatus: {status}"
    ),
    "owner.user.card.banned": "🚫 Gesperrt. Grund: {reason}",
    "owner.user.status.active": "aktiv",
    "owner.user.status.banned": "gesperrt",
    "owner.user.not_found": "Nutzer nicht gefunden.",
    "owner.user.kb.grant": "💎 Guthaben anpassen",
    "owner.user.kb.ban": "🚫 Sperren",
    "owner.user.kb.unban": "✅ Entsperren",
    "owner.user.kb.back": "⬅️ Zur Liste",
    "owner.user.grant.prompt": "Gib die Anzahl der Guthabenpunkte ein (kann negativ sein, z. B. -3):",
    "owner.user.grant.invalid": "Das habe ich nicht verstanden. Gib eine ganze Zahl ein, z. B. 5 oder -2.",
    "owner.user.grant.done": "Erledigt. Neues Guthaben: {credits}💎.",
    "owner.user.ban.prompt": "Gib den Sperrgrund ein:",
    "owner.user.ban.invalid": "Der Grund darf nicht leer sein. Gib einen Grund ein:",
    "owner.user.ban.done": "Nutzer gesperrt.",
    "owner.user.ban.staff_blocked": "Du kannst keinen Inhaber oder Administrator sperren.",
    "owner.user.unban.done": "Nutzer entsperrt.",
    "owner.user.cancelled": "Abgebrochen.",
    "account.banned.notice": "🚫 Dein Zugang zum Bot ist eingeschränkt. Grund: {reason}",
    # -------------------------------------------------------------------------
    # Readings submenu
    # -------------------------------------------------------------------------
    "btn.readings": "📖 Lesungen",
    "readings.menu.title": "Welche Lesung möchtest du?",
    "readings.queued": "Ich erstelle deine Lesung. Das dauert eine Minute.",
    "readings.no_profile": "Bitte fülle zuerst dein Geburtsprofil aus.",
    "readings.no_quota": "Keine Credits verfügbar. Kaufe ein Paket, um fortzufahren.",
    "readings.kind.bazi": "🐉 BaZi",
    "readings.kind.numerology": "🔢 Numerologie",
    "readings.kind.human_design": "🧬 Human Design",
    "readings.kind.astrology": "☉ Astrologie",
    "readings.kind.vedic": "🕉 Vedisch",
    "readings.kind.gene_keys": "🗝 Gene Keys",
    "readings.kind.mayan": "🌀 Maya",
    "readings.kind.aspects": "✦ Aspekte",
    # -------------------------------------------------------------------------
    # History — recent readings section
    # -------------------------------------------------------------------------
    "history.readings_title": "📖 Letzte Lesungen",
    "history.reading_row": "{kind} · {status} · {date}",
    "history.download": "⬇️ Herunterladen",
    # -------------------------------------------------------------------------
    # Content moderation
    # -------------------------------------------------------------------------
    "moderation.self_harm": "Wenn du gerade an einem schweren Punkt bist, hol dir bitte Unterstützung: {helpline_url}. Ich ersetze keine Fachperson, aber ich bin da.",
    "moderation.violence": "Diese Frage liegt außerhalb dessen, womit ich helfen kann.",
    "moderation.hate": "Dafür bin ich nicht da.",
    "moderation.medical": "Das ist eine Frage für Ärztinnen oder Ärzte, nicht für Astrologie. Klinische Ratschläge gebe ich nicht.",
    "moderation.legal": "Das ist eine Frage für einen Anwalt. Ich rede über Energien und Zyklen, nicht über rechtliche Risiken.",
    "moderation.blocked_generic": "Diese Anfrage kann nicht bearbeitet werden.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
    "feature.disabled_generic": "Diese Funktion ist in diesem Bot nicht verfügbar.",
    "owner.features.title": "⚙️ Funktionen",
    "owner.features.btn": "⚙️ Funktionen",
    "owner.features.section.readings": "— Auswertungen —",
    "owner.features.label.qa": "Frage-Antwort",
    "owner.features.label.blueprint": "Auswertung",
    "owner.features.label.transits": "Transite",
    "owner.features.label.daily": "Tägliches",
    # White-label branding (SP3)
    "brand.signature": "",
    "owner.branding.btn": "🎨 Branding",
    "owner.branding.title": "🎨 Branding (Sprache: {language})",
    "owner.branding.label.name": "Name",
    "owner.branding.label.welcome": "Begrüßung",
    "owner.branding.label.help": "Hilfe",
    "owner.branding.label.signature": "Signatur",
    "owner.branding.prompt": (
        "Sende neuen Text für **{label}** ({language}), "
        "oder /cancel um abzubrechen, /reset um Standard wiederherzustellen."
    ),
    "owner.branding.saved": "✅ Aktualisiert.",
    "owner.branding.reset_done": "↩️ Auf Standard zurückgesetzt.",
    "owner.branding.cancelled": "Abgebrochen.",
    "owner.branding.too_long": "Zu lang: {actual} Zeichen (max {limit}).",
    "owner.branding.bad_format": "Name muss 1-64 Zeichen lang sein und keine Zeilenumbrüche enthalten.",
    "owner.branding.empty_value": "Leerer Wert nicht erlaubt. /reset zum Löschen.",
    "owner.branding.preview_empty": "(leer)",
    # -------------------------------------------------------------------------
    # Referral links (SP4)
    # -------------------------------------------------------------------------
    "btn.invite": "🎁 Freund einladen",
    "invite.title": "Lade Freunde zu diesem Bot ein.",
    "invite.link_label": "Dein Link",
    "invite.earned": "Verdient: {credits} Credits von {friends} Freunden.",
    "invite.share_text": "Probier diesen Bot",
    "invite.disabled": "Empfehlungen sind in diesem Bot deaktiviert.",
    "invite.unknown_code": "Empfehlungslink nicht erkannt. Fortsetzung ohne Bonus.",
    "owner.referrals.title": "Empfehlungsprogramm",
    "owner.referrals.current_value": "Aktuelle Belohnung: {value} Credits.",
    "owner.referrals.prompt": "Sende eine ganze Zahl zwischen 0 und {max}.",
    "owner.referrals.saved": "Gespeichert: {value} Credits.",
    "owner.referrals.reset": "Auf Standard zurückgesetzt ({value}).",
    "owner.referrals.too_large": "Wert muss zwischen 0 und {max} sein.",
    "owner.referrals.not_a_number": "Sende eine ganze Zahl.",
    "owner.referrals.cancel_hint": "Sende /cancel zum Abbrechen.",
    "owner.referrals.menu_button": "Empfehlungen",
    # -------------------------------------------------------------------------
    # Gift-a-friend (SP5)
    # -------------------------------------------------------------------------
    "btn.gift": "🎁 Geschenk",
    "gift.title": "Verschenke an einen Freund",
    "gift.balance_line": "Verfügbar: {balance}",
    "gift.amount_prompt": "Geschenkbetrag eingeben (1–{max}):",
    "gift.cancelled": "Abgebrochen.",
    "gift.cancel_hint": "Sende /cancel zum Abbrechen.",
    "gift.too_small": "Mindestens 1 Kredit.",
    "gift.too_large": "Maximal {max} Kredits.",
    "gift.not_a_number": "Das ist keine Zahl. Bitte ganze Zahl eingeben.",
    "gift.no_balance": "Du hast keine Kredits zum Verschenken.",
    "gift.created": "Geschenk über {amount} Kredits ist bereit!\n\nLink: {link}",
    "gift.share_text": "Ein Geschenk für dich! Öffne den Bot, um deine Kredits einzulösen.",
    "gift.disabled": "Geschenke sind derzeit nicht verfügbar.",
    "gift.received": "Du hast ein Geschenk erhalten: {amount} Kredits!",
    "gift.self_blocked": "Du kannst dein eigenes Geschenk nicht einlösen.",
    "gift.history_title": "Deine Geschenke",
    "gift.history_empty": "Noch leer.",
    "gift.history_row": "{date} — {amount} Kr. — {status}",
    "gift.status.active": "ausstehend",
    "gift.status.claimed": "eingelöst",
    "gift.status.refunded": "erstattet",
    "gift.btn.create_new": "Neu erstellen",
    "owner.gifts.menu_button": "Geschenke",
    "owner.gifts.title": "Geschenke",
    "owner.gifts.current_value": "Geschenkdauer: {value} Tage.",
    "owner.gifts.prompt": "Geschenkdauer in Tagen eingeben ({min}–{max}):",
    "owner.gifts.saved": "Gespeichert.",
    "owner.gifts.reset": "Auf Standard zurückgesetzt.",
    "owner.gifts.too_small": "Mindestens {min} Tag.",
    "owner.gifts.too_large": "Maximal {max} Tage.",
    "owner.gifts.not_a_number": "Bitte ganze Zahl eingeben.",
    "owner.gifts.cancel_hint": "Sende /cancel zum Abbrechen.",
    # SP6 — Divination (Tarot + I-Ching)
    "readings.kind.tarot": "🔮 Tarot",
    "readings.kind.iching": "☯ I Ging",
    "divination.question_prompt": "Stelle deine Frage oder sende /skip:",
    "divination.skip_btn": "Überspringen",
    "divination.no_question": "(keine Frage)",
    "tarot.position.past": "Vergangenheit",
    "tarot.position.present": "Gegenwart",
    "tarot.position.future": "Zukunft",
    "tarot.orientation.upright": "aufrecht",
    "tarot.orientation.reversed": "umgekehrt",
    "iching.judgment_label": "Urteil",
    "iching.image_label": "Bild",
    "iching.changing_line_label": "Wandelnde Linie {n}",
    "iching.transformed_label": "Wird zu",
    # Console UX nav + provisioning
    "owner.manage.kb.back": "⬅️ Zurück zum Menü",
    "owner.features.label.referrals": "Empfehlungen",
    "owner.features.label.gifts": "Geschenke",
    "master.provision.manual_prompt": (
        "Automatische Bot-Erstellung ist nicht verfügbar. Erstelle einen neuen Bot "
        "über @BotFather und sende seinen Token hier in einer Nachricht."
    ),
    "master.provision.managed_prompt": (
        "Tippe auf die Schaltfläche unten — Telegram erstellt den Bot und ich übernehme "
        "ihn automatisch. Den Benutzernamen kannst du im Erstellungsbildschirm anpassen."
    ),
    "master.provision.managed_button": "🤖 Bot erstellen",
}
