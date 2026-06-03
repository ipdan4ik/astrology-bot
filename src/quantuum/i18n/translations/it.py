"""Italian (it) UI translations. Keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": "🔮 Blueprint",
    "btn.profile": "👤 Profilo",
    "btn.history": "📜 Cronologia",
    "btn.help": "ℹ️ Aiuto",
    "btn.ask": "❓ Chiedi all'astrologo",
    "btn.transits": "🌌 Transiti",
    "btn.daily": "🔔 Oroscopo quotidiano",
    "btn.buy": "💳 Acquista",
    "btn.language": "🌐 Lingua",
    # -------------------------------------------------------------------------
    # Blueprint status words
    # -------------------------------------------------------------------------
    "status.pending": "in coda",
    "status.calculating": "in calcolo",
    "status.generating": "in generazione",
    "status.done": "pronto",
    "status.failed": "errore",
    "status.refunded": "rimborso",
    # -------------------------------------------------------------------------
    # Help text
    # -------------------------------------------------------------------------
    "help.text": (
        "Creo letture astrologiche personali dai tuoi dati natali.\n\n"
        "Menu:\n"
        "❓ Chiedi all'astrologo — domanda con il tuo contesto natale\n"
        "📖 Letture — Blueprint, Transiti, BaZi, Human Design, Tarocchi e altro\n"
        "🔔 Oroscopo quotidiano — consegna giornaliera dell'oroscopo\n"
        "👤 Profilo — data, ora e luogo di nascita\n"
        "📜 Cronologia — tutte le letture passate\n"
        "💳 Acquista — pacchetti e abbonamenti\n"
        "🌐 Lingua — cambia la lingua dell'interfaccia\n"
        "🎁 Invita un amico — link referral\n"
        "🎁 Regalo — regala crediti a un amico\n\n"
        "Supporto: @quantuum_support"
    ),
    # -------------------------------------------------------------------------
    # Profile display
    # -------------------------------------------------------------------------
    "profile.title": "👤 Il tuo profilo:",
    "profile.name": "Nome: {name}",
    "profile.birth_date": "Data di nascita: {birth_date}",
    "profile.birth_time": "Ora: {birth_time}",
    "profile.place": "Luogo: {place}",
    # -------------------------------------------------------------------------
    # Profile screen messages
    # -------------------------------------------------------------------------
    "profile.empty": "Profilo non compilato.",
    "profile.not_found": "Profilo non trovato.",
    "profile.place.confirm": "Trovato: {place}\n\nCorretto?",
    "profile.place.not_found": "Non ho trovato questo luogo. Specifica la città / indirizzo o invia la posizione:",
    # -------------------------------------------------------------------------
    # Profile keyboard labels
    # -------------------------------------------------------------------------
    "profile.kb.fill": "📝 Compila il profilo",
    "profile.kb.edit_name": "✏️ Nome",
    "profile.kb.edit_birth_date": "✏️ Data",
    "profile.kb.edit_birth_time": "✏️ Ora",
    "profile.kb.edit_birth_place": "✏️ Luogo",
    "profile.kb.place_confirm": "✅ Sì",
    "profile.kb.place_retry": "✏️ Altro indirizzo",
    # -------------------------------------------------------------------------
    # Profile field prompts (edit flow)
    # -------------------------------------------------------------------------
    "profile.prompt.name": "Inserisci il tuo nome:",
    "profile.prompt.birth_date": "Data di nascita AAAA-MM-GG (es. 1980-06-24):",
    "profile.prompt.birth_time": "Ora di nascita HH:MM (es. 10:00):",
    "profile.prompt.birth_place": "Invia la tua posizione (📎 → Posizione) oppure scrivi una città / indirizzo:",
    # -------------------------------------------------------------------------
    # Profile field validation errors
    # -------------------------------------------------------------------------
    "profile.error.name_empty": "Il nome non può essere vuoto.",
    "profile.error.birth_date_invalid": "Impossibile leggere la data. Formato AAAA-MM-GG.",
    "profile.error.birth_time_invalid": "Impossibile leggere l'ora. Formato HH:MM.",
    "profile.error.unknown_field": "Campo sconosciuto.",
    "profile.field_edit_error": "{err}\nRiprova:",
    # -------------------------------------------------------------------------
    # Start / welcome
    # -------------------------------------------------------------------------
    "start.welcome": "Ciao! Creerò la tua lettura astrologica ✨",
    # -------------------------------------------------------------------------
    # Main menu
    # -------------------------------------------------------------------------
    "menu.title": "Menu principale:",
    "menu.cancelled": "Annullato.",
    # -------------------------------------------------------------------------
    # Generate (blueprint request)
    # -------------------------------------------------------------------------
    "generate.no_profile": "Compila prima il tuo profilo:",
    "generate.no_quota": "La generazione gratuita è già stata utilizzata. Acquista un pacchetto o un abbonamento:",
    "generate.queued": "Sto generando la tua lettura, ci vorrà circa un minuto…",
    # -------------------------------------------------------------------------
    # Q&A astrologer
    # -------------------------------------------------------------------------
    "qa.ask_prompt": "Invia la tua domanda all'astrologo:",
    "qa.thinking": "Sto elaborando la risposta… ⏳",
    "qa.no_profile": "Compila prima il tuo profilo natale (/profile).",
    "qa.no_quota": "Crediti esauriti. Acquista un pacchetto o un abbonamento per interrogare l'astrologo:",
    "qa.too_long": "La domanda è troppo lunga (max 1000 caratteri).",
    "qa.empty": "Domanda vuota. Scrivi la tua domanda:",
    # -------------------------------------------------------------------------
    # Transits
    # -------------------------------------------------------------------------
    "transit.thinking": "Calcolo i tuoi transiti… ⏳",
    "transit.no_profile": "Compila prima il tuo profilo natale (/profile).",
    "transit.no_quota": "Crediti esauriti. Acquista un pacchetto o un abbonamento per vedere i tuoi transiti:",
    "transit.failed": "Impossibile calcolare i transiti. Riprova più tardi.",
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": "🌟 Oroscopo di oggi",
    "daily.status_on": "Oroscopo quotidiano attivato. Orario di consegna: {hour}:00 (fuso orario locale).",
    "daily.status_off": "Oroscopo quotidiano disattivato.",
    "daily.not_subscriber": "L'oroscopo quotidiano è una funzione riservata agli abbonati. Abbonati per riceverlo ogni mattina:",
    "daily.no_profile": "Compila prima il tuo profilo natale (/profile).",
    "daily.enabled": "Oroscopo quotidiano attivato ✅",
    "daily.disabled": "Oroscopo quotidiano disattivato.",
    "daily.hour_set": "Orario di consegna: {hour}:00 ✅",
    "daily.kb.turn_on": "🔔 Attiva",
    "daily.kb.close": "✅ Fatto",
    "daily.kb.turn_off": "🔕 Disattiva",
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": "Nessuna lettura ancora. Premi «🔮 Blueprint» per crearne una.",
    "history.title": "📜 Cronologia letture:",
    "history.label": "🔮 {date} · {status}",
    "history.detail_header": "🔮 Blueprint #{id}",
    "history.detail_status": "Stato: {status}",
    "history.detail_created": "Creata: {created_at}",
    "history.detail_ready": "Pronta: {completed_at}",
    "history.not_found": "Non trovato",
    # -------------------------------------------------------------------------
    # History / blueprint detail keyboard labels
    # -------------------------------------------------------------------------
    "history.kb.download": "📥 Scarica .md",
    "history.kb.preview": "👁 Anteprima",
    "history.kb.back": "← Indietro",
    "history.kb.prev_page": "← Prec",
    "history.kb.next_page": "Succ →",
    "history.unavailable": "Non disponibile",
    # -------------------------------------------------------------------------
    # Buy / payments
    # -------------------------------------------------------------------------
    "buy.menu_title": "Scegli cosa acquistare (pagamento tramite Telegram Stars ★):",
    "buy.no_plans": "Nessun piano disponibile al momento. Riprova più tardi.",
    "buy.plan_subscription": "⭐ {name} — {price}★",
    "buy.plan_package": "⭐ {name} · {count} letture — {price}★",
    "buy.invoice_subscription": "Abbonamento per {period_days} giorni",
    "buy.invoice_package": "Pacchetto: {count} letture",
    "buy.plan_unavailable": "Questo piano non è più disponibile.",
    "buy.payment_success": "Pagamento ricevuto! Accesso attivato. ✨",
    "buy.payment_already_credited": "Questo pagamento è già stato accreditato.",
    "buy.kb.open": "💳 Acquista letture",
    # -------------------------------------------------------------------------
    # Shared / generic
    # -------------------------------------------------------------------------
    "kb.cancel": "✖️ Annulla",
    "errors.queue_failed": "Impossibile mettere in coda la richiesta. Il credito è stato rimborsato — riprova tra poco.",
    # -------------------------------------------------------------------------
    # Master bot — owner onboarding
    # -------------------------------------------------------------------------
    "master.onboard.invite_invalid": "L'invito non è valido o è scaduto.",
    "master.onboard.slug_prompt": "Benvenuto! Creiamo un bot. Inserisci lo slug del tenant (lettere latine, senza spazi){prefill}:",
    "master.onboard.slug_prefill": " (suggerito: {slug})",
    "master.onboard.plain_start": "Questo è il bot di onboarding della piattaforma. Apri un link di invito per creare il tuo bot.",
    "master.onboard.slug_invalid": "Lo slug non deve essere vuoto né contenere spazi. Riprova:",
    "master.onboard.slug_taken": "Questo slug è già in uso. Inserisci un altro:",
    "master.onboard.display_name_prompt": "Nome visualizzato del prodotto (es. «Acme Astro»):",
    "master.onboard.display_name_empty": "Il nome non deve essere vuoto. Inseriscilo di nuovo:",
    "master.onboard.lang_prompt": "Lingua predefinita (codice a due lettere, es. ru o en):",
    "master.onboard.lang_invalid": "È richiesto un codice lingua a due lettere, es. it. Inseriscilo di nuovo:",
    "master.onboard.confirm": (
        "Controlla i dati:\nslug: {slug}\nnome: {display_name}\nlingua: {language}\n\n"
        "Creare il bot?"
    ),
    "master.onboard.invite_gone": "L'invito non è più valido.",
    "master.onboard.creating": "Creo il tenant… Verifico se il bot può essere creato automaticamente.",
    "master.onboard.cancelled": "Onboarding annullato.",
    "master.onboard.token_invalid": "Questo non sembra un token bot valido. Invia di nuovo il token da @BotFather:",
    "master.onboard.token_in_use": "Questo bot è già collegato a un altro progetto. Usa un bot diverso.",
    "master.onboard.done": "Fatto! Il bot @{username} è attivato. Sarà disponibile dopo il riavvio del worker.",
    "master.kb.cancel": "Annulla",
    "master.kb.create_bot": "Crea bot",
    # -------------------------------------------------------------------------
    # Master bot — owner console
    # -------------------------------------------------------------------------
    "owner.tenants.empty": "Non hai ancora tenant. Crea un bot tramite un link di invito.",
    "owner.tenants.header": "I tuoi tenant:",
    "owner.tenants.line": "• {display_name} (/{slug}) — {status}",
    "owner.tenants.hint": "\nGestisci: /manage <slug>",
    "owner.manage.usage": "Utilizzo: /manage <slug>",
    "owner.manage.not_found": "Tenant non trovato o permesso insufficiente.",
    "owner.manage.title": "Gestione: {display_name} (/{slug}) — {status}",
    "owner.manage.kb.stats": "📊 Statistiche",
    "owner.manage.kb.pause": "⏸ Pausa",
    "owner.manage.kb.resume": "▶️ Riprendi",
    "owner.manage.kb.transfer": "🔁 Trasferisci proprietà",
    "owner.stats.text": (
        "📊 Statistiche (ultimi {period_days} giorni)\n"
        "Attivi: {active_customers}, paganti: {paid_customers}\n"
        "DAU/WAU/MAU: {dau}/{wau}/{mau}\n"
        "Ricavi: {revenue_cents}, MRR: {mrr_cents}\n"
        "Richieste: {requests_by_kind}"
    ),
    "owner.no_rights": "Permesso negato",
    "owner.pause.platform_blocked": "Il tenant della piattaforma non può essere messo in pausa",
    "owner.pause.done": "⏸ Messo in pausa.",
    "owner.resume.done": "▶️ Ripreso.",
    "owner.manage.kb.delete": "🗑 Elimina",
    "owner.delete.prompt": (
        "⚠️ Questo eliminerà definitivamente il bot e nasconderà il tenant. "
        "Per confermare, invia lo slug: {slug}\n(oppure /cancel)"
    ),
    "owner.delete.mismatch": "Lo slug non corrisponde. Invia {slug} di nuovo oppure /cancel.",
    "owner.delete.done": "🗑 Bot eliminato.",
    "owner.delete.cancelled": "Annullato.",
    "owner.delete.platform_blocked": "Il tenant della piattaforma non può essere eliminato",
    # -------------------------------------------------------------------------
    # Superadmin cabinet
    # -------------------------------------------------------------------------
    "admin.denied": "Non autorizzato.",
    "admin.menu.title": "🛠 Pannello superadmin",
    "admin.menu.kb.tenants": "🏢 Bot",
    "admin.menu.kb.invites": "🎟 Inviti",
    "admin.tenants.title": "Tutti i bot:",
    "admin.tenants.empty": "Nessun bot ancora.",
    "admin.tenant.title": "Bot: {display_name} (/{slug}) — {status}",
    "admin.tenant.kb.stats": "📊 Statistiche",
    "admin.tenant.kb.suspend": "⏸ Sospendi",
    "admin.tenant.kb.resume": "▶️ Riprendi",
    "admin.tenant.kb.delete": "🗑 Elimina",
    "admin.kb.back": "⬅️ Indietro",
    "admin.tenant.suspended": "⏸ Bot sospeso.",
    "admin.tenant.resumed": "▶️ Bot ripreso.",
    "admin.invites.title": "Inviti attivi:",
    "admin.invites.empty": "Nessun invito attivo.",
    "admin.invites.kb.new": "➕ Nuovo invito",
    "admin.invite.kb.revoke": "🗑 Revoca",
    "admin.invite.created": "Invito creato:\n{link}",
    "admin.invite.revoked": "Invito revocato.",
    "admin.stale": "Non trovato — elenco aggiornato.",
    # -------------------------------------------------------------------------
    # Transfer
    # -------------------------------------------------------------------------
    "owner.transfer.usage": "Utilizzo: /transfer <slug>",
    "owner.transfer.not_owner": "Tenant non trovato o non sei il proprietario.",
    "owner.transfer.prompt": (
        "Invia il Telegram ID del nuovo proprietario (un numero). "
        "Deve già avere un account in questo tenant (aver avviato il tuo bot)."
    ),
    "owner.transfer.cancelled": "Annullato.",
    "owner.transfer.target_invalid": "È richiesto un Telegram ID numerico. Riprova oppure /cancel.",
    "owner.transfer.no_rights_anymore": "Non hai più il permesso di trasferire.",
    "owner.transfer.no_account": (
        "Questo utente non ha un account nel tenant. "
        "Deve prima avviare il tuo bot."
    ),
    "owner.transfer.done": "✅ Fatto. Proprietà trasferita.",
    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    "lang.prompt": "Scegli la tua lingua:",
    "lang.changed": "Lingua aggiornata.",
    # -------------------------------------------------------------------------
    # Onboarding flow
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": "Inserisci il tuo nome completo (come sul certificato di nascita):",
    "onb.error.full_name": "Non ho capito il nome. Inserisci il tuo nome completo come testo:",
    "onb.prompt.birth_date": "Data di nascita nel formato AAAA-MM-GG (es. 1980-06-24):",
    "onb.error.birth_date": "Non ho capito la data. Formato AAAA-MM-GG:",
    "onb.prompt.birth_time": "Ora di nascita HH:MM (es. 10:00):",
    "onb.error.birth_time": "Non ho capito l'ora. Formato HH:MM:",
    "onb.prompt.birth_place": (
        "Luogo di nascita: invia la tua posizione (📎 → Posizione, puoi segnare un punto "
        "sulla mappa) oppure scrivi una città / parte dell'indirizzo:"
    ),
    "onb.done": "Fatto! Il tuo profilo è salvato. Premi «🔮 Blueprint» nel menu in basso.",
    # Owner console — user management
    "owner.manage.kb.users": "👥 Utenti",
    "owner.users.header": "Utenti di {display_name}:",
    "owner.users.empty": "Ancora nessun utente.",
    "owner.users.row": "{name} · {credits}💎",
    "owner.users.unnamed": "utente #{id}",
    "owner.users.nav.prev": "◀️",
    "owner.users.nav.next": "▶️",
    "owner.user.card": (
        "👤 {name}\nTelegram ID: {tg_id}\nCrediti: {credits}💎\n"
        "Abbonamento: {subscription}\nStato: {status}"
    ),
    "owner.user.card.banned": "🚫 Bannato. Motivo: {reason}",
    "owner.user.status.active": "attivo",
    "owner.user.status.banned": "bannato",
    "owner.user.not_found": "Utente non trovato.",
    "owner.user.kb.grant": "💎 Gestisci crediti",
    "owner.user.kb.ban": "🚫 Banna",
    "owner.user.kb.unban": "✅ Rimuovi ban",
    "owner.user.kb.back": "⬅️ Alla lista",
    "owner.user.grant.prompt": "Inserisci il numero di crediti (può essere negativo, es. -3):",
    "owner.user.grant.invalid": "Non ho capito. Inserisci un numero intero, es. 5 o -2.",
    "owner.user.grant.done": "Fatto. Nuovo saldo: {credits}💎.",
    "owner.user.ban.prompt": "Inserisci il motivo del ban:",
    "owner.user.ban.invalid": "Il motivo non può essere vuoto. Inserisci un motivo:",
    "owner.user.ban.done": "Utente bannato.",
    "owner.user.ban.staff_blocked": "Non puoi bannare un proprietario o un amministratore.",
    "owner.user.unban.done": "Ban rimosso.",
    "owner.user.cancelled": "Annullato.",
    "account.banned.notice": "🚫 Il tuo accesso al bot è limitato. Motivo: {reason}",
    # -------------------------------------------------------------------------
    # Readings submenu
    # -------------------------------------------------------------------------
    "btn.readings": "📖 Letture",
    "readings.menu.title": "Quale lettura ti interessa?",
    "readings.queued": "Sto preparando la tua lettura. Ci vorrà un minuto.",
    "readings.no_profile": "Prima completa il tuo profilo di nascita.",
    "readings.no_quota": "Crediti esauriti. Acquista un pacchetto per continuare.",
    "readings.kind.bazi": "🐉 BaZi",
    "readings.kind.numerology": "🔢 Numerologia",
    "readings.kind.human_design": "🧬 Human Design",
    "readings.kind.astrology": "☉ Astrologia",
    "readings.kind.vedic": "🕉 Vedica",
    "readings.kind.gene_keys": "🗝 Gene Keys",
    "readings.kind.mayan": "🌀 Maya",
    "readings.kind.aspects": "✦ Aspetti",
    # -------------------------------------------------------------------------
    # History — recent readings section
    # -------------------------------------------------------------------------
    "history.readings_title": "📖 Letture recenti",
    "history.reading_row": "{kind} · {status} · {date}",
    "history.download": "⬇️ Scarica",
    # -------------------------------------------------------------------------
    # Content moderation
    # -------------------------------------------------------------------------
    "moderation.self_harm": "Se ora stai attraversando un momento difficile, chiedi supporto: {helpline_url}. Non sostituisco un professionista, ma ci sono.",
    "moderation.violence": "Questa domanda è oltre ciò con cui posso aiutarti.",
    "moderation.hate": "Non sono qui per questo.",
    "moderation.medical": "È una domanda per un medico, non per l'astrologia. Non do consigli clinici.",
    "moderation.legal": "Quello è per un avvocato. Parlo di energie e cicli, non di rischi legali.",
    "moderation.blocked_generic": "Questa richiesta non può essere elaborata.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
    "feature.disabled_generic": "Questa funzionalità non è disponibile su questo bot.",
    "owner.features.title": "⚙️ Funzioni",
    "owner.features.btn": "⚙️ Funzioni",
    "owner.features.section.readings": "— Letture —",
    "owner.features.label.qa": "Domanda-Risposta",
    "owner.features.label.blueprint": "Lettura",
    "owner.features.label.transits": "Transiti",
    "owner.features.label.daily": "Quotidiano",
    # White-label branding (SP3)
    "brand.signature": "",
    "owner.branding.btn": "🎨 Branding",
    "owner.branding.title": "🎨 Branding (lingua: {language})",
    "owner.branding.label.name": "Nome",
    "owner.branding.label.welcome": "Benvenuto",
    "owner.branding.label.help": "Aiuto",
    "owner.branding.label.signature": "Firma",
    "owner.branding.prompt": (
        "Invia il nuovo testo per **{label}** ({language}), "
        "o /cancel per mantenere, /reset per ripristinare il predefinito."
    ),
    "owner.branding.saved": "✅ Aggiornato.",
    "owner.branding.reset_done": "↩️ Ripristinato al predefinito.",
    "owner.branding.cancelled": "Annullato.",
    "owner.branding.too_long": "Troppo lungo: {actual} caratteri (max {limit}).",
    "owner.branding.bad_format": "Il nome deve essere 1-64 caratteri senza ritorni a capo.",
    "owner.branding.empty_value": "Valore vuoto non permesso. Usa /reset per cancellare.",
    "owner.branding.preview_empty": "(vuoto)",
    # -------------------------------------------------------------------------
    # Referral links (SP4)
    # -------------------------------------------------------------------------
    "btn.invite": "🎁 Invita un amico",
    "invite.title": "Invita gli amici in questo bot.",
    "invite.link_label": "Il tuo link",
    "invite.earned": "Guadagnato: {credits} crediti da {friends} amici.",
    "invite.share_text": "Prova questo bot",
    "invite.disabled": "I referral sono disabilitati in questo bot.",
    "invite.unknown_code": "Link di referral non riconosciuto. Continuo senza bonus.",
    "owner.referrals.title": "Programma referral",
    "owner.referrals.current_value": "Ricompensa attuale: {value} crediti.",
    "owner.referrals.prompt": "Invia un intero tra 0 e {max} per modificare la ricompensa.",
    "owner.referrals.saved": "Salvato: {value} crediti.",
    "owner.referrals.reset": "Ripristinato al valore predefinito ({value}).",
    "owner.referrals.too_large": "Il valore deve essere nell'intervallo 0-{max}.",
    "owner.referrals.not_a_number": "Invia un numero intero.",
    "owner.referrals.cancel_hint": "Invia /cancel per annullare.",
    "owner.referrals.menu_button": "Referral",
    # -------------------------------------------------------------------------
    # Gift-a-friend (SP5)
    # -------------------------------------------------------------------------
    "btn.gift": "🎁 Regalo",
    "gift.title": "Regala a un amico",
    "gift.balance_line": "Disponibile: {balance}",
    "gift.amount_prompt": "Inserisci l'importo del regalo (1–{max}):",
    "gift.cancelled": "Annullato.",
    "gift.cancel_hint": "Invia /cancel per annullare.",
    "gift.too_small": "Minimo 1 credito.",
    "gift.too_large": "Massimo {max} crediti.",
    "gift.not_a_number": "Non è un numero. Inserisci un numero intero.",
    "gift.no_balance": "Non hai crediti da regalare.",
    "gift.created": "Regalo di {amount} crediti pronto!\n\nLink: {link}",
    "gift.share_text": "Un regalo per te! Apri il bot per riscattare i tuoi crediti.",
    "gift.disabled": "I regali non sono disponibili al momento.",
    "gift.received": "Hai ricevuto un regalo: {amount} crediti!",
    "gift.self_blocked": "Non puoi riscattare il tuo regalo.",
    "gift.history_title": "I tuoi regali",
    "gift.history_empty": "Ancora vuoto.",
    "gift.history_row": "{date} — {amount} cr. — {status}",
    "gift.status.active": "in attesa",
    "gift.status.claimed": "riscattato",
    "gift.status.refunded": "rimborsato",
    "gift.btn.create_new": "Crea nuovo",
    "owner.gifts.menu_button": "Regali",
    "owner.gifts.title": "Regali",
    "owner.gifts.current_value": "Durata del regalo: {value} giorni.",
    "owner.gifts.prompt": "Inserisci la durata del regalo in giorni ({min}–{max}):",
    "owner.gifts.saved": "Salvato.",
    "owner.gifts.reset": "Reimpostato al valore predefinito.",
    "owner.gifts.too_small": "Minimo {min} giorno.",
    "owner.gifts.too_large": "Massimo {max} giorni.",
    "owner.gifts.not_a_number": "Inserisci un numero intero.",
    "owner.gifts.cancel_hint": "Invia /cancel per annullare.",
    # SP6 — Divination (Tarot + I-Ching)
    "readings.kind.tarot": "🔮 Tarocchi",
    "readings.kind.iching": "☯ I Ching",
    "divination.question_prompt": "Formula la tua domanda o invia /skip:",
    "divination.skip_btn": "Salta",
    "divination.no_question": "(nessuna domanda)",
    "tarot.position.past": "Passato",
    "tarot.position.present": "Presente",
    "tarot.position.future": "Futuro",
    "tarot.orientation.upright": "dritta",
    "tarot.orientation.reversed": "rovesciata",
    "iching.judgment_label": "Giudizio",
    "iching.image_label": "Immagine",
    "iching.changing_line_label": "Linea mutevole {n}",
    "iching.transformed_label": "Diventa",
}
