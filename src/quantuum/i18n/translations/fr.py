"""French (fr) UI translations. Keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": "🔮 Blueprint",
    "btn.profile": "👤 Profil",
    "btn.history": "📜 Historique",
    "btn.help": "ℹ️ Aide",
    "btn.ask": "❓ Demander à l'astrologue",
    "btn.transits": "🌌 Transits",
    "btn.daily": "🔔 Horoscope quotidien",
    "btn.buy": "💳 Acheter",
    "btn.language": "🌐 Langue",
    # -------------------------------------------------------------------------
    # Blueprint status words
    # -------------------------------------------------------------------------
    "status.pending": "en attente",
    "status.calculating": "calcul en cours",
    "status.generating": "génération en cours",
    "status.done": "prêt",
    "status.failed": "erreur",
    "status.refunded": "remboursé",
    # -------------------------------------------------------------------------
    # Help text
    # -------------------------------------------------------------------------
    "help.text": (
        "Je crée des lectures astrologiques personnelles à partir de tes données natales.\n\n"
        "Menu :\n"
        "❓ Demander à l'astrologue — question avec ton contexte natal\n"
        "📖 Lectures — Blueprint, Transits, BaZi, Human Design, Tarot et plus\n"
        "🔔 Horoscope quotidien — livraison quotidienne de ton horoscope\n"
        "👤 Profil — date, heure et lieu de naissance\n"
        "📜 Historique — toutes les lectures passées\n"
        "💳 Acheter — packs et abonnements\n"
        "🌐 Langue — changer la langue de l'interface\n"
        "🎁 Inviter un ami — lien de parrainage\n"
        "🎁 Cadeau — offrir des crédits à un ami\n\n"
        "Support : @quantuum_support"
    ),
    # -------------------------------------------------------------------------
    # Profile display
    # -------------------------------------------------------------------------
    "profile.title": "👤 Ton profil :",
    "profile.name": "Nom : {name}",
    "profile.birth_date": "Date de naissance : {birth_date}",
    "profile.birth_time": "Heure : {birth_time}",
    "profile.place": "Lieu : {place}",
    # -------------------------------------------------------------------------
    # Profile screen messages
    # -------------------------------------------------------------------------
    "profile.empty": "Profil non renseigné.",
    "profile.not_found": "Profil introuvable.",
    "profile.place.confirm": "Trouvé : {place}\n\nCorrect ?",
    "profile.place.not_found": "Impossible de trouver ce lieu. Précise la ville / l'adresse ou envoie ta position :",
    # -------------------------------------------------------------------------
    # Profile keyboard labels
    # -------------------------------------------------------------------------
    "profile.kb.fill": "📝 Remplir le profil",
    "profile.kb.edit_name": "✏️ Nom",
    "profile.kb.edit_birth_date": "✏️ Date",
    "profile.kb.edit_birth_time": "✏️ Heure",
    "profile.kb.edit_birth_place": "✏️ Lieu",
    "profile.kb.place_confirm": "✅ Oui",
    "profile.kb.place_retry": "✏️ Autre adresse",
    # -------------------------------------------------------------------------
    # Profile field prompts (edit flow)
    # -------------------------------------------------------------------------
    "profile.prompt.name": "Entre ton nom :",
    "profile.prompt.birth_date": "Date de naissance AAAA-MM-JJ (ex. 1980-06-24) :",
    "profile.prompt.birth_time": "Heure de naissance HH:MM (ex. 10:00) :",
    "profile.prompt.birth_place": "Envoie ta position (📎 → Localisation) ou tape une ville / adresse :",
    # -------------------------------------------------------------------------
    # Profile field validation errors
    # -------------------------------------------------------------------------
    "profile.error.name_empty": "Le nom ne peut pas être vide.",
    "profile.error.birth_date_invalid": "Date non reconnue. Format AAAA-MM-JJ.",
    "profile.error.birth_time_invalid": "Heure non reconnue. Format HH:MM.",
    "profile.error.unknown_field": "Champ inconnu.",
    "profile.field_edit_error": "{err}\nRéessaie :",
    # -------------------------------------------------------------------------
    # Start / welcome
    # -------------------------------------------------------------------------
    "start.welcome": "Bonjour ! Je vais générer ta lecture astrologique ✨",
    # -------------------------------------------------------------------------
    # Main menu
    # -------------------------------------------------------------------------
    "menu.title": "Menu principal :",
    "menu.cancelled": "Annulé.",
    # -------------------------------------------------------------------------
    # Generate (blueprint request)
    # -------------------------------------------------------------------------
    "generate.no_profile": "Remplis d'abord ton profil :",
    "generate.no_quota": "Ta lecture gratuite a déjà été utilisée. Achète un forfait ou un abonnement :",
    "generate.queued": "Génération de ta lecture en cours, cela prendra environ une minute…",
    # -------------------------------------------------------------------------
    # Q&A astrologer
    # -------------------------------------------------------------------------
    "qa.ask_prompt": "Envoie ta question à l'astrologue :",
    "qa.thinking": "Je réfléchis à ta réponse… ⏳",
    "qa.no_profile": "Remplis d'abord ton profil natal (/profile).",
    "qa.no_quota": "Tu n'as plus de crédits. Achète un forfait ou un abonnement pour consulter l'astrologue :",
    "qa.too_long": "La question est trop longue (max 1000 caractères).",
    "qa.empty": "Question vide. Écris ta question :",
    # -------------------------------------------------------------------------
    # Transits
    # -------------------------------------------------------------------------
    "transit.thinking": "Calcul de tes transits… ⏳",
    "transit.no_profile": "Remplis d'abord ton profil natal (/profile).",
    "transit.no_quota": "Tu n'as plus de crédits. Achète un forfait ou un abonnement pour voir tes transits :",
    "transit.failed": "Impossible de calculer tes transits. Réessaie plus tard.",
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": "🌟 Horoscope du jour",
    "daily.status_on": "Horoscope quotidien activé. Heure de livraison : {hour}:00 (ton fuseau horaire).",
    "daily.status_off": "Horoscope quotidien désactivé.",
    "daily.not_subscriber": "L'horoscope quotidien est réservé aux abonnés. Abonne-toi pour le recevoir chaque matin :",
    "daily.no_profile": "Remplis d'abord ton profil natal (/profile).",
    "daily.enabled": "Horoscope quotidien activé ✅",
    "daily.disabled": "Horoscope quotidien désactivé.",
    "daily.hour_set": "Heure de livraison : {hour}:00 ✅",
    "daily.kb.turn_on": "🔔 Activer",
    "daily.kb.close": "✅ Terminer",
    "daily.kb.turn_off": "🔕 Désactiver",
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": "Aucune lecture pour l'instant. Appuie sur «🔮 Blueprint» pour en créer une.",
    "history.title": "📜 Historique des lectures :",
    "history.label": "🔮 {date} · {status}",
    "history.detail_header": "🔮 Blueprint #{id}",
    "history.detail_status": "Statut : {status}",
    "history.detail_created": "Créée : {created_at}",
    "history.detail_ready": "Prête : {completed_at}",
    "history.not_found": "Introuvable",
    # -------------------------------------------------------------------------
    # History / blueprint detail keyboard labels
    # -------------------------------------------------------------------------
    "history.kb.download": "📥 Télécharger .md",
    "history.kb.preview": "👁 Aperçu",
    "history.kb.back": "← Retour",
    "history.kb.prev_page": "← Préc",
    "history.kb.next_page": "Suiv →",
    "history.unavailable": "Indisponible",
    # -------------------------------------------------------------------------
    # Buy / payments
    # -------------------------------------------------------------------------
    "buy.menu_title": "Choisir ce que tu veux acheter (paiement via Telegram Stars ★) :",
    "buy.no_plans": "Aucun forfait disponible pour l'instant. Reviens plus tard.",
    "buy.plan_subscription": "⭐ {name} — {price}★",
    "buy.plan_package": "⭐ {name} · {count} lectures — {price}★",
    "buy.invoice_subscription": "Abonnement de {period_days} jours",
    "buy.invoice_package": "Forfait : {count} lectures",
    "buy.plan_unavailable": "Ce forfait n'est plus disponible.",
    "buy.payment_success": "Paiement reçu ! Accès activé. ✨",
    "buy.payment_already_credited": "Ce paiement a déjà été pris en compte.",
    "buy.kb.open": "💳 Acheter des lectures",
    # -------------------------------------------------------------------------
    # Shared / generic
    # -------------------------------------------------------------------------
    "kb.cancel": "✖️ Annuler",
    "errors.queue_failed": "Impossible de mettre votre demande en file d'attente. Votre crédit a été remboursé — réessayez dans un instant.",
    # -------------------------------------------------------------------------
    # Master bot — owner onboarding
    # -------------------------------------------------------------------------
    "master.onboard.invite_invalid": "L'invitation est invalide ou a expiré.",
    "master.onboard.slug_prompt": "Bienvenue ! Créons un bot. Entre le slug du tenant (lettres latines, sans espaces){prefill} :",
    "master.onboard.slug_prefill": " (suggéré : {slug})",
    "master.onboard.plain_start": "Ceci est le bot d'accueil de la plateforme. Ouvre un lien d'invitation pour créer ton propre bot.",
    "master.onboard.slug_invalid": "Le slug ne doit pas être vide ni contenir d'espaces. Réessaie :",
    "master.onboard.slug_taken": "Ce slug est déjà pris. Entre un autre :",
    "master.onboard.display_name_prompt": "Nom d'affichage du produit (ex. «Acme Astro») :",
    "master.onboard.display_name_empty": "Le nom ne doit pas être vide. Entre-le à nouveau :",
    "master.onboard.lang_prompt": "Langue par défaut (code à deux lettres, ex. ru ou en) :",
    "master.onboard.lang_invalid": "Un code de langue à deux lettres est requis, ex. fr. Entre-le à nouveau :",
    "master.onboard.confirm": (
        "Vérifie les informations :\nslug : {slug}\nnom : {display_name}\nlangue : {language}\n\n"
        "Créer le bot ?"
    ),
    "master.onboard.invite_gone": "L'invitation n'est plus valide.",
    "master.onboard.creating": "Création du tenant… Vérification de la création automatique du bot.",
    "master.onboard.cancelled": "Inscription annulée.",
    "master.onboard.token_invalid": "Ce token ne semble pas valide. Renvoie le token de @BotFather :",
    "master.onboard.token_in_use": "Ce bot est déjà lié à un autre projet. Utilise un autre bot.",
    "master.onboard.done": "Terminé ! Le bot @{username} est activé. Il sera disponible après le redémarrage du worker.",
    "master.kb.cancel": "Annuler",
    "master.kb.create_bot": "Créer le bot",
    # -------------------------------------------------------------------------
    # Master bot — owner console
    # -------------------------------------------------------------------------
    "owner.tenants.empty": "Tu n'as pas encore de tenants. Crée un bot via un lien d'invitation.",
    "owner.tenants.header": "Tes tenants :",
    "owner.tenants.line": "• {display_name} (/{slug}) — {status}",
    "owner.tenants.hint": "\nGestion : /manage <slug>",
    "owner.manage.usage": "Utilisation : /manage <slug>",
    "owner.manage.not_found": "Tenant introuvable ou tu n'as pas les droits.",
    "owner.manage.title": "Gestion : {display_name} (/{slug}) — {status}",
    "owner.manage.kb.stats": "📊 Statistiques",
    "owner.manage.kb.pause": "⏸ Pause",
    "owner.manage.kb.resume": "▶️ Reprendre",
    "owner.manage.kb.transfer": "🔁 Transférer la propriété",
    "owner.stats.text": (
        "📊 Statistiques (derniers {period_days} jours)\n"
        "Actifs : {active_customers}, payants : {paid_customers}\n"
        "DAU/WAU/MAU : {dau}/{wau}/{mau}\n"
        "Revenus : {revenue_cents}, MRR : {mrr_cents}\n"
        "Requêtes : {requests_by_kind}"
    ),
    "owner.no_rights": "Non autorisé",
    "owner.pause.platform_blocked": "Le tenant de la plateforme ne peut pas être mis en pause",
    "owner.pause.done": "⏸ Mis en pause.",
    "owner.resume.done": "▶️ Repris.",
    "owner.manage.kb.delete": "🗑 Supprimer",
    "owner.delete.prompt": (
        "⚠️ Ceci supprimera définitivement le bot et masquera le tenant. "
        "Pour confirmer, envoie le slug : {slug}\n(ou /cancel)"
    ),
    "owner.delete.mismatch": "Le slug ne correspond pas. Envoie {slug} à nouveau ou /cancel.",
    "owner.delete.done": "🗑 Bot supprimé.",
    "owner.delete.cancelled": "Annulé.",
    "owner.delete.platform_blocked": "Le tenant de la plateforme ne peut pas être supprimé",
    # -------------------------------------------------------------------------
    # Superadmin cabinet
    # -------------------------------------------------------------------------
    "admin.denied": "Non autorisé.",
    "admin.menu.title": "🛠 Panneau superadmin",
    "admin.menu.kb.tenants": "🏢 Bots",
    "admin.menu.kb.invites": "🎟 Invitations",
    "admin.tenants.title": "Tous les bots :",
    "admin.tenants.empty": "Aucun bot pour l'instant.",
    "admin.tenant.title": "Bot : {display_name} (/{slug}) — {status}",
    "admin.tenant.kb.stats": "📊 Statistiques",
    "admin.tenant.kb.suspend": "⏸ Suspendre",
    "admin.tenant.kb.resume": "▶️ Reprendre",
    "admin.tenant.kb.delete": "🗑 Supprimer",
    "admin.kb.back": "⬅️ Retour",
    "admin.tenant.suspended": "⏸ Bot suspendu.",
    "admin.tenant.resumed": "▶️ Bot repris.",
    "admin.invites.title": "Invitations actives :",
    "admin.invites.empty": "Aucune invitation active.",
    "admin.invites.kb.new": "➕ Nouvelle invitation",
    "admin.invite.kb.revoke": "🗑 Révoquer",
    "admin.invite.created": "Invitation créée :\n{link}",
    "admin.invite.revoked": "Invitation révoquée.",
    "admin.stale": "Introuvable — liste actualisée.",
    # -------------------------------------------------------------------------
    # Transfer
    # -------------------------------------------------------------------------
    "owner.transfer.usage": "Utilisation : /transfer <slug>",
    "owner.transfer.not_owner": "Tenant introuvable ou tu n'en es pas le propriétaire.",
    "owner.transfer.prompt": (
        "Envoie l'ID Telegram du nouveau propriétaire (un nombre). "
        "Il doit déjà avoir un compte dans ce tenant (avoir démarré ton bot)."
    ),
    "owner.transfer.cancelled": "Annulé.",
    "owner.transfer.target_invalid": "Un ID Telegram numérique est requis. Réessaie ou /cancel.",
    "owner.transfer.no_rights_anymore": "Tu n'as plus les droits pour effectuer ce transfert.",
    "owner.transfer.no_account": (
        "Cet utilisateur n'a pas de compte dans le tenant. "
        "Il doit d'abord démarrer ton bot."
    ),
    "owner.transfer.done": "✅ Terminé. Propriété transférée.",
    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    "lang.prompt": "Choisis ta langue :",
    "lang.changed": "Langue mise à jour.",
    # -------------------------------------------------------------------------
    # Onboarding flow
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": "Entre ton nom complet (tel qu'il figure sur ton acte de naissance) :",
    "onb.error.full_name": "Nom non reconnu. Entre ton nom complet en texte :",
    "onb.prompt.birth_date": "Date de naissance au format AAAA-MM-JJ (ex. 1980-06-24) :",
    "onb.error.birth_date": "Date non reconnue. Format AAAA-MM-JJ :",
    "onb.prompt.birth_time": "Heure de naissance HH:MM (ex. 10:00) :",
    "onb.error.birth_time": "Heure non reconnue. Format HH:MM :",
    "onb.prompt.birth_place": (
        "Lieu de naissance : envoie ta position (📎 → Localisation, tu peux placer un repère sur "
        "la carte) ou tape une ville / partie d'adresse :"
    ),
    "onb.done": "Terminé ! Ton profil est enregistré. Appuie sur «🔮 Blueprint» dans le menu ci-dessous.",
    # Owner console — user management
    "owner.manage.kb.users": "👥 Utilisateurs",
    "owner.users.header": "Utilisateurs de {display_name} :",
    "owner.users.empty": "Aucun utilisateur pour l'instant.",
    "owner.users.row": "{name} · {credits}💎",
    "owner.users.unnamed": "utilisateur #{id}",
    "owner.users.nav.prev": "◀️",
    "owner.users.nav.next": "▶️",
    "owner.user.card": (
        "👤 {name}\nTelegram ID: {tg_id}\nCrédits : {credits}💎\n"
        "Abonnement : {subscription}\nStatut : {status}"
    ),
    "owner.user.card.banned": "🚫 Banni. Motif : {reason}",
    "owner.user.status.active": "actif",
    "owner.user.status.banned": "banni",
    "owner.user.not_found": "Utilisateur introuvable.",
    "owner.user.kb.grant": "💎 Ajuster les crédits",
    "owner.user.kb.ban": "🚫 Bannir",
    "owner.user.kb.unban": "✅ Débannir",
    "owner.user.kb.back": "⬅️ Retour à la liste",
    "owner.user.grant.prompt": "Saisis le nombre de crédits (peut être négatif, ex. -3) :",
    "owner.user.grant.invalid": "Je n'ai pas compris. Saisis un nombre entier, ex. 5 ou -2.",
    "owner.user.grant.done": "Fait. Nouveau solde : {credits}💎.",
    "owner.user.ban.prompt": "Saisis le motif du bannissement :",
    "owner.user.ban.invalid": "Le motif ne peut pas être vide. Saisis un motif :",
    "owner.user.ban.done": "Utilisateur banni.",
    "owner.user.ban.staff_blocked": "Vous ne pouvez pas bannir un propriétaire ou un administrateur.",
    "owner.user.unban.done": "Utilisateur débanni.",
    "owner.user.cancelled": "Annulé.",
    "account.banned.notice": "🚫 Votre accès au bot est restreint. Motif : {reason}",
    # -------------------------------------------------------------------------
    # Readings submenu
    # -------------------------------------------------------------------------
    "btn.readings": "📖 Lectures",
    "readings.menu.title": "Quelle lecture souhaites-tu ?",
    "readings.queued": "Je prépare ta lecture. Cela prendra une minute.",
    "readings.no_profile": "Remplis d'abord ton profil de naissance.",
    "readings.no_quota": "Aucun crédit disponible. Achète un pack pour continuer.",
    "readings.kind.bazi": "🐉 BaZi",
    "readings.kind.numerology": "🔢 Numérologie",
    "readings.kind.human_design": "🧬 Human Design",
    "readings.kind.astrology": "☉ Astrologie",
    "readings.kind.vedic": "🕉 Védique",
    "readings.kind.gene_keys": "🗝 Gene Keys",
    "readings.kind.mayan": "🌀 Maya",
    "readings.kind.aspects": "✦ Aspects",
    # -------------------------------------------------------------------------
    # History — recent readings section
    # -------------------------------------------------------------------------
    "history.readings_title": "📖 Lectures récentes",
    "history.reading_row": "{kind} · {status} · {date}",
    "history.download": "⬇️ Télécharger",
    # -------------------------------------------------------------------------
    # Content moderation
    # -------------------------------------------------------------------------
    "moderation.self_harm": "Si tu traverses un moment difficile, demande du soutien : {helpline_url}. Je ne remplace pas un professionnel, mais je suis là.",
    "moderation.violence": "Cette question dépasse ce que je peux faire.",
    "moderation.hate": "Je ne suis pas là pour ça.",
    "moderation.medical": "C'est une question pour un médecin, pas pour l'astrologie. Je ne donne pas de conseils cliniques.",
    "moderation.legal": "C'est pour un avocat. Je parle d'énergies et de cycles, pas de risques juridiques.",
    "moderation.blocked_generic": "Cette demande ne peut pas être traitée.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
    "feature.disabled_generic": "Cette fonctionnalité n'est pas disponible sur ce bot.",
    "owner.features.title": "⚙️ Fonctions",
    "owner.features.btn": "⚙️ Fonctions",
    "owner.features.section.readings": "— Lectures —",
    "owner.features.label.qa": "Question-Réponse",
    "owner.features.label.blueprint": "Lecture",
    "owner.features.label.transits": "Transits",
    "owner.features.label.daily": "Quotidien",
    # White-label branding (SP3)
    "brand.signature": "",
    "owner.branding.btn": "🎨 Branding",
    "owner.branding.title": "🎨 Branding (langue : {language})",
    "owner.branding.label.name": "Nom",
    "owner.branding.label.welcome": "Bienvenue",
    "owner.branding.label.help": "Aide",
    "owner.branding.label.signature": "Signature",
    "owner.branding.prompt": (
        "Envoyez le nouveau texte pour **{label}** ({language}), "
        "ou /cancel pour garder l'actuel, /reset pour restaurer le défaut."
    ),
    "owner.branding.saved": "✅ Mis à jour.",
    "owner.branding.reset_done": "↩️ Réinitialisé au défaut.",
    "owner.branding.cancelled": "Annulé.",
    "owner.branding.too_long": "Trop long : {actual} caractères (max {limit}).",
    "owner.branding.bad_format": "Le nom doit faire 1-64 caractères sans saut de ligne.",
    "owner.branding.empty_value": "Valeur vide interdite. Utilisez /reset pour effacer.",
    "owner.branding.preview_empty": "(vide)",
    # -------------------------------------------------------------------------
    # Referral links (SP4)
    # -------------------------------------------------------------------------
    "btn.invite": "🎁 Inviter un ami",
    "invite.title": "Invitez vos amis dans ce bot.",
    "invite.link_label": "Votre lien",
    "invite.earned": "Gagné : {credits} crédits de {friends} amis.",
    "invite.share_text": "Essayez ce bot",
    "invite.disabled": "Les parrainages sont désactivés dans ce bot.",
    "invite.unknown_code": "Lien de parrainage non reconnu. Continuation sans bonus.",
    "owner.referrals.title": "Programme de parrainage",
    "owner.referrals.current_value": "Récompense actuelle : {value} crédits.",
    "owner.referrals.prompt": "Envoyez un entier entre 0 et {max} pour modifier la récompense.",
    "owner.referrals.saved": "Enregistré : {value} crédits.",
    "owner.referrals.reset": "Réinitialisé à la valeur par défaut ({value}).",
    "owner.referrals.too_large": "La valeur doit être comprise entre 0 et {max}.",
    "owner.referrals.not_a_number": "Envoyez un entier.",
    "owner.referrals.cancel_hint": "Envoyez /cancel pour annuler.",
    "owner.referrals.menu_button": "Parrainages",
    # -------------------------------------------------------------------------
    # Gift-a-friend (SP5)
    # -------------------------------------------------------------------------
    "btn.gift": "🎁 Cadeau",
    "gift.title": "Offrir à un ami",
    "gift.balance_line": "Disponible : {balance}",
    "gift.amount_prompt": "Entrez le montant du cadeau (1–{max}) :",
    "gift.cancelled": "Annulé.",
    "gift.cancel_hint": "Envoyez /cancel pour annuler.",
    "gift.too_small": "Minimum 1 crédit.",
    "gift.too_large": "Maximum {max} crédits.",
    "gift.not_a_number": "Ce n'est pas un nombre. Entrez un nombre entier.",
    "gift.no_balance": "Vous n'avez pas de crédits à offrir.",
    "gift.created": "Cadeau de {amount} crédits prêt !\n\nLien : {link}",
    "gift.share_text": "Un cadeau pour toi ! Ouvre le bot pour réclamer tes crédits.",
    "gift.disabled": "Les cadeaux ne sont pas disponibles actuellement.",
    "gift.received": "Vous avez reçu un cadeau : {amount} crédits !",
    "gift.self_blocked": "Vous ne pouvez pas réclamer votre propre cadeau.",
    "gift.history_title": "Vos cadeaux",
    "gift.history_empty": "Encore vide.",
    "gift.history_row": "{date} — {amount} cr. — {status}",
    "gift.status.active": "en attente",
    "gift.status.claimed": "réclamé",
    "gift.status.refunded": "remboursé",
    "gift.btn.create_new": "Créer nouveau",
    "owner.gifts.menu_button": "Cadeaux",
    "owner.gifts.title": "Cadeaux",
    "owner.gifts.current_value": "Durée de vie du cadeau : {value} jours.",
    "owner.gifts.prompt": "Entrez la durée de vie du cadeau en jours ({min}–{max}) :",
    "owner.gifts.saved": "Sauvegardé.",
    "owner.gifts.reset": "Réinitialisé à la valeur par défaut.",
    "owner.gifts.too_small": "Minimum {min} jour.",
    "owner.gifts.too_large": "Maximum {max} jours.",
    "owner.gifts.not_a_number": "Entrez un nombre entier.",
    "owner.gifts.cancel_hint": "Envoyez /cancel pour annuler.",
    # SP6 — Divination (Tarot + I-Ching)
    "readings.kind.tarot": "🔮 Tarot",
    "readings.kind.iching": "☯ Yi King",
    "divination.question_prompt": "Formule ta question ou envoie /skip :",
    "divination.skip_btn": "Passer",
    "divination.no_question": "(sans question)",
    "tarot.position.past": "Passé",
    "tarot.position.present": "Présent",
    "tarot.position.future": "Futur",
    "tarot.orientation.upright": "droite",
    "tarot.orientation.reversed": "renversée",
    "iching.judgment_label": "Jugement",
    "iching.image_label": "Image",
    "iching.changing_line_label": "Ligne mutante {n}",
    "iching.transformed_label": "Devient",
}
