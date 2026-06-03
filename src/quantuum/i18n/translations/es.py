"""Spanish (es) UI translations. Keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": "🔮 Blueprint",
    "btn.profile": "👤 Perfil",
    "btn.history": "📜 Historial",
    "btn.help": "ℹ️ Ayuda",
    "btn.ask": "❓ Preguntar al astrólogo",
    "btn.transits": "🌌 Tránsitos",
    "btn.daily": "🔔 Horóscopo diario",
    "btn.buy": "💳 Comprar",
    "btn.language": "🌐 Idioma",
    # -------------------------------------------------------------------------
    # Blueprint status words
    # -------------------------------------------------------------------------
    "status.pending": "en cola",
    "status.calculating": "calculando",
    "status.generating": "generando",
    "status.done": "lista",
    "status.failed": "error",
    "status.refunded": "reembolsado",
    # -------------------------------------------------------------------------
    # Help text
    # -------------------------------------------------------------------------
    "help.text": (
        "Creo lecturas astrológicas personales a partir de tus datos natales.\n\n"
        "Menú:\n"
        "❓ Preguntar al astrólogo — pregunta con tu contexto natal\n"
        "📖 Lecturas — Blueprint, Tránsitos, BaZi, Human Design, Tarot y más\n"
        "🔔 Horóscopo diario — entrega diaria de tu horóscopo\n"
        "👤 Perfil — fecha, hora y lugar de nacimiento\n"
        "📜 Historial — todas las lecturas pasadas\n"
        "💳 Comprar — paquetes y suscripciones\n"
        "🌐 Idioma — cambiar idioma de la interfaz\n"
        "🎁 Invitar a un amigo — enlace de referido\n"
        "🎁 Regalo — regalar créditos a un amigo\n\n"
        "Soporte: @quantuum_support"
    ),
    # -------------------------------------------------------------------------
    # Profile display
    # -------------------------------------------------------------------------
    "profile.title": "👤 Tu perfil:",
    "profile.name": "Nombre: {name}",
    "profile.birth_date": "Fecha de nacimiento: {birth_date}",
    "profile.birth_time": "Hora: {birth_time}",
    "profile.place": "Lugar: {place}",
    # -------------------------------------------------------------------------
    # Profile screen messages
    # -------------------------------------------------------------------------
    "profile.empty": "El perfil no está completado.",
    "profile.not_found": "Perfil no encontrado.",
    "profile.place.confirm": "Encontrado: {place}\n\n¿Es correcto?",
    "profile.place.not_found": "No encontré ese lugar. Refina la ciudad / dirección o envía tu ubicación:",
    # -------------------------------------------------------------------------
    # Profile keyboard labels
    # -------------------------------------------------------------------------
    "profile.kb.fill": "📝 Completar perfil",
    "profile.kb.edit_name": "✏️ Nombre",
    "profile.kb.edit_birth_date": "✏️ Fecha",
    "profile.kb.edit_birth_time": "✏️ Hora",
    "profile.kb.edit_birth_place": "✏️ Lugar",
    "profile.kb.place_confirm": "✅ Sí",
    "profile.kb.place_retry": "✏️ Otra dirección",
    # -------------------------------------------------------------------------
    # Profile field prompts (edit flow)
    # -------------------------------------------------------------------------
    "profile.prompt.name": "Introduce tu nombre:",
    "profile.prompt.birth_date": "Fecha de nacimiento AAAA-MM-DD (p. ej. 1980-06-24):",
    "profile.prompt.birth_time": "Hora de nacimiento HH:MM (p. ej. 10:00):",
    "profile.prompt.birth_place": "Envía tu ubicación (📎 → Ubicación) o escribe una ciudad / dirección:",
    # -------------------------------------------------------------------------
    # Profile field validation errors
    # -------------------------------------------------------------------------
    "profile.error.name_empty": "El nombre no puede estar vacío.",
    "profile.error.birth_date_invalid": "No se pudo interpretar la fecha. Formato AAAA-MM-DD.",
    "profile.error.birth_time_invalid": "No se pudo interpretar la hora. Formato HH:MM.",
    "profile.error.unknown_field": "Campo desconocido.",
    "profile.field_edit_error": "{err}\nInténtalo de nuevo:",
    # -------------------------------------------------------------------------
    # Start / welcome
    # -------------------------------------------------------------------------
    "start.welcome": "¡Hola! Construiré tu lectura astrológica ✨",
    # -------------------------------------------------------------------------
    # Main menu
    # -------------------------------------------------------------------------
    "menu.title": "Menú principal:",
    "menu.cancelled": "Cancelado.",
    # -------------------------------------------------------------------------
    # Generate (blueprint request)
    # -------------------------------------------------------------------------
    "generate.no_profile": "Por favor, completa tu perfil primero:",
    "generate.no_quota": "Tu lectura gratuita ya se ha utilizado. Compra un paquete o suscripción:",
    "generate.queued": "Generando tu lectura, esto tardará aproximadamente un minuto…",
    # -------------------------------------------------------------------------
    # Q&A astrologer
    # -------------------------------------------------------------------------
    "qa.ask_prompt": "Envía tu pregunta al astrólogo:",
    "qa.thinking": "Pensando en tu respuesta… ⏳",
    "qa.no_profile": "Completa tu perfil natal primero (/profile).",
    "qa.no_quota": "Te has quedado sin créditos. Compra un paquete o suscripción para preguntar al astrólogo:",
    "qa.too_long": "La pregunta es demasiado larga (máx. 1000 caracteres).",
    "qa.empty": "Pregunta vacía. Por favor escribe tu pregunta:",
    # -------------------------------------------------------------------------
    # Transits
    # -------------------------------------------------------------------------
    "transit.thinking": "Calculando tus tránsitos… ⏳",
    "transit.no_profile": "Completa tu perfil natal primero (/profile).",
    "transit.no_quota": "Te has quedado sin créditos. Compra un paquete o suscripción para ver tus tránsitos:",
    "transit.failed": "No se pudieron calcular los tránsitos. Inténtalo más tarde.",
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": "🌟 Horóscopo de hoy",
    "daily.status_on": "Horóscopo diario ACTIVADO. Hora de entrega: {hour}:00 (tu zona horaria).",
    "daily.status_off": "Horóscopo diario DESACTIVADO.",
    "daily.not_subscriber": "El horóscopo diario es una función de suscripción. Suscríbete para recibirlo cada mañana:",
    "daily.no_profile": "Completa tu perfil natal primero (/profile).",
    "daily.enabled": "Horóscopo diario activado ✅",
    "daily.disabled": "Horóscopo diario desactivado.",
    "daily.hour_set": "Hora de entrega: {hour}:00 ✅",
    "daily.kb.turn_on": "🔔 Activar",
    "daily.kb.close": "✅ Listo",
    "daily.kb.turn_off": "🔕 Desactivar",
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": "Aún no hay lecturas. Pulsa «🔮 Blueprint» para crear la primera.",
    "history.title": "📜 Historial de lecturas:",
    "history.label": "🔮 {date} · {status}",
    "history.detail_header": "🔮 Blueprint #{id}",
    "history.detail_status": "Estado: {status}",
    "history.detail_created": "Creado: {created_at}",
    "history.detail_ready": "Lista: {completed_at}",
    "history.not_found": "No encontrado",
    # -------------------------------------------------------------------------
    # History / blueprint detail keyboard labels
    # -------------------------------------------------------------------------
    "history.kb.download": "📥 Descargar .md",
    "history.kb.preview": "👁 Vista previa",
    "history.kb.back": "← Volver",
    "history.kb.prev_page": "← Ant",
    "history.kb.next_page": "Sig →",
    "history.unavailable": "No disponible",
    # -------------------------------------------------------------------------
    # Buy / payments
    # -------------------------------------------------------------------------
    "buy.menu_title": "Elige qué comprar (pago con Telegram Stars ★):",
    "buy.no_plans": "Aún no hay planes disponibles. Vuelve más tarde.",
    "buy.plan_subscription": "⭐ {name} — {price}★",
    "buy.plan_package": "⭐ {name} · {count} lecturas — {price}★",
    "buy.invoice_subscription": "Suscripción por {period_days} días",
    "buy.invoice_package": "Paquete: {count} lecturas",
    "buy.plan_unavailable": "Este plan ya no está disponible.",
    "buy.payment_success": "¡Pago recibido! Acceso activado. ✨",
    "buy.payment_already_credited": "Este pago ya fue acreditado anteriormente.",
    "buy.kb.open": "💳 Comprar lecturas",
    # -------------------------------------------------------------------------
    # Shared / generic
    # -------------------------------------------------------------------------
    "kb.cancel": "✖️ Cancelar",
    # -------------------------------------------------------------------------
    # Master bot — owner onboarding
    # -------------------------------------------------------------------------
    "master.onboard.invite_invalid": "La invitación no es válida o ha expirado.",
    "master.onboard.slug_prompt": "¡Bienvenido! Vamos a crear un bot. Introduce el slug del tenant (letras latinas, sin espacios){prefill}:",
    "master.onboard.slug_prefill": " (sugerido: {slug})",
    "master.onboard.plain_start": "Este es el bot de incorporación de la plataforma. Abre un enlace de invitación para crear tu propio bot.",
    "master.onboard.slug_invalid": "El slug no debe estar vacío ni contener espacios. Inténtalo de nuevo:",
    "master.onboard.slug_taken": "Este slug ya está en uso. Introduce otro:",
    "master.onboard.display_name_prompt": "Nombre de producto a mostrar (p. ej. «Acme Astro»):",
    "master.onboard.display_name_empty": "El nombre no debe estar vacío. Introdúcelo de nuevo:",
    "master.onboard.lang_prompt": "Idioma predeterminado (código de dos letras, p. ej. ru o en):",
    "master.onboard.lang_invalid": "Se requiere un código de idioma de dos letras, p. ej. ru. Introdúcelo de nuevo:",
    "master.onboard.confirm": (
        "Verifica los datos:\nslug: {slug}\nnombre: {display_name}\nidioma: {language}\n\n"
        "¿Crear el bot?"
    ),
    "master.onboard.invite_gone": "La invitación ya no es válida.",
    "master.onboard.creating": "Creando el tenant… Comprobando si el bot puede crearse automáticamente.",
    "master.onboard.cancelled": "Incorporación cancelada.",
    "master.onboard.token_invalid": "Esto no parece un token de bot válido. Envía el token de @BotFather de nuevo:",
    "master.onboard.done": "¡Listo! El bot @{username} está activado. Estará disponible tras reiniciar el worker.",
    "master.kb.cancel": "Cancelar",
    "master.kb.create_bot": "Crear bot",
    # -------------------------------------------------------------------------
    # Master bot — owner console
    # -------------------------------------------------------------------------
    "owner.tenants.empty": "Aún no tienes tenants. Crea un bot mediante un enlace de invitación.",
    "owner.tenants.header": "Tus tenants:",
    "owner.tenants.line": "• {display_name} (/{slug}) — {status}",
    "owner.tenants.hint": "\nGestionar: /manage <slug>",
    "owner.manage.usage": "Uso: /manage <slug>",
    "owner.manage.not_found": "Tenant no encontrado o no tienes permiso.",
    "owner.manage.title": "Gestionar: {display_name} (/{slug}) — {status}",
    "owner.manage.kb.stats": "📊 Estadísticas",
    "owner.manage.kb.pause": "⏸ Pausar",
    "owner.manage.kb.resume": "▶️ Reanudar",
    "owner.manage.kb.transfer": "🔁 Transferir propiedad",
    "owner.stats.text": (
        "📊 Estadísticas (últimos {period_days} días)\n"
        "Activos: {active_customers}, pagadores: {paid_customers}\n"
        "DAU/WAU/MAU: {dau}/{wau}/{mau}\n"
        "Ingresos: {revenue_cents}, MRR: {mrr_cents}\n"
        "Solicitudes: {requests_by_kind}"
    ),
    "owner.no_rights": "Sin permiso",
    "owner.pause.platform_blocked": "El tenant de la plataforma no puede pausarse",
    "owner.pause.done": "⏸ Pausado.",
    "owner.resume.done": "▶️ Reanudado.",
    "owner.manage.kb.delete": "🗑 Eliminar",
    "owner.delete.prompt": (
        "⚠️ Esto eliminará permanentemente el bot y ocultará el tenant. "
        "Para confirmar, envía el slug: {slug}\n(o /cancel)"
    ),
    "owner.delete.mismatch": "El slug no coincide. Envía {slug} de nuevo o /cancel.",
    "owner.delete.done": "🗑 Bot eliminado.",
    "owner.delete.cancelled": "Cancelado.",
    "owner.delete.platform_blocked": "El tenant de la plataforma no puede eliminarse",
    # -------------------------------------------------------------------------
    # Superadmin cabinet
    # -------------------------------------------------------------------------
    "admin.denied": "No autorizado.",
    "admin.menu.title": "🛠 Panel de superadmin",
    "admin.menu.kb.tenants": "🏢 Bots",
    "admin.menu.kb.invites": "🎟 Invitaciones",
    "admin.tenants.title": "Todos los bots:",
    "admin.tenants.empty": "Aún no hay bots.",
    "admin.tenant.title": "Bot: {display_name} (/{slug}) — {status}",
    "admin.tenant.kb.stats": "📊 Estadísticas",
    "admin.tenant.kb.suspend": "⏸ Suspender",
    "admin.tenant.kb.resume": "▶️ Reanudar",
    "admin.tenant.kb.delete": "🗑 Eliminar",
    "admin.kb.back": "⬅️ Volver",
    "admin.tenant.suspended": "⏸ Bot suspendido.",
    "admin.tenant.resumed": "▶️ Bot reanudado.",
    "admin.invites.title": "Invitaciones activas:",
    "admin.invites.empty": "No hay invitaciones activas.",
    "admin.invites.kb.new": "➕ Nueva invitación",
    "admin.invite.kb.revoke": "🗑 Revocar",
    "admin.invite.created": "Invitación creada:\n{link}",
    "admin.invite.revoked": "Invitación revocada.",
    "admin.stale": "No encontrado — lista actualizada.",
    # -------------------------------------------------------------------------
    # Transfer
    # -------------------------------------------------------------------------
    "owner.transfer.usage": "Uso: /transfer <slug>",
    "owner.transfer.not_owner": "Tenant no encontrado o no eres el propietario.",
    "owner.transfer.prompt": (
        "Envía el ID de Telegram del nuevo propietario (un número). "
        "Debe tener ya una cuenta en este tenant (haber iniciado tu bot)."
    ),
    "owner.transfer.cancelled": "Cancelado.",
    "owner.transfer.target_invalid": "Se requiere un ID numérico de Telegram. Inténtalo de nuevo o /cancel.",
    "owner.transfer.no_rights_anymore": "Ya no tienes permiso para transferir.",
    "owner.transfer.no_account": (
        "Este usuario no tiene cuenta en el tenant. "
        "Debe iniciar tu bot primero."
    ),
    "owner.transfer.done": "✅ Listo. Propiedad transferida.",
    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    "lang.prompt": "Elige tu idioma:",
    "lang.changed": "Idioma actualizado.",
    # -------------------------------------------------------------------------
    # Onboarding flow
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": "Introduce tu nombre completo (tal como aparece en tu partida de nacimiento):",
    "onb.error.full_name": "No pude leer el nombre. Introduce tu nombre completo como texto:",
    "onb.prompt.birth_date": "Fecha de nacimiento en formato AAAA-MM-DD (p. ej. 1980-06-24):",
    "onb.error.birth_date": "No pude leer la fecha. Formato AAAA-MM-DD:",
    "onb.prompt.birth_time": "Hora de nacimiento HH:MM (p. ej. 10:00):",
    "onb.error.birth_time": "No pude leer la hora. Formato HH:MM:",
    "onb.prompt.birth_place": (
        "Lugar de nacimiento: envía tu ubicación (📎 → Ubicación, puedes marcar un punto "
        "en el mapa) o escribe una ciudad / parte de una dirección:"
    ),
    "onb.done": "¡Listo! Tu perfil está guardado. Pulsa «🔮 Blueprint» en el menú de abajo.",
    # Owner console — user management
    "owner.manage.kb.users": "👥 Usuarios",
    "owner.users.header": "Usuarios de {display_name}:",
    "owner.users.empty": "Aún no hay usuarios.",
    "owner.users.row": "{name} · {credits}💎",
    "owner.users.unnamed": "usuario #{id}",
    "owner.users.nav.prev": "◀️",
    "owner.users.nav.next": "▶️",
    "owner.user.card": (
        "👤 {name}\nTelegram ID: {tg_id}\nCréditos: {credits}💎\n"
        "Suscripción: {subscription}\nEstado: {status}"
    ),
    "owner.user.card.banned": "🚫 Baneado. Motivo: {reason}",
    "owner.user.status.active": "activo",
    "owner.user.status.banned": "baneado",
    "owner.user.not_found": "Usuario no encontrado.",
    "owner.user.kb.grant": "💎 Ajustar créditos",
    "owner.user.kb.ban": "🚫 Banear",
    "owner.user.kb.unban": "✅ Desbanear",
    "owner.user.kb.back": "⬅️ A la lista",
    "owner.user.grant.prompt": "Introduce el número de créditos (puede ser negativo, p. ej. -3):",
    "owner.user.grant.invalid": "No lo entendí. Introduce un número entero, p. ej. 5 o -2.",
    "owner.user.grant.done": "Hecho. Nuevo saldo: {credits}💎.",
    "owner.user.ban.prompt": "Indica el motivo del baneo:",
    "owner.user.ban.invalid": "El motivo no puede estar vacío. Indica un motivo:",
    "owner.user.ban.done": "Usuario baneado.",
    "owner.user.ban.staff_blocked": "No puedes banear a un propietario o administrador.",
    "owner.user.unban.done": "Usuario desbaneado.",
    "owner.user.cancelled": "Cancelado.",
    "account.banned.notice": "🚫 Tu acceso al bot está restringido. Motivo: {reason}",
    # -------------------------------------------------------------------------
    # Readings submenu
    # -------------------------------------------------------------------------
    "btn.readings": "📖 Lecturas",
    "readings.menu.title": "¿Qué lectura te gustaría?",
    "readings.queued": "Estoy preparando tu lectura. Tardará un minuto.",
    "readings.no_profile": "Primero, completa tu perfil de nacimiento.",
    "readings.no_quota": "No hay créditos disponibles. Compra un paquete para continuar.",
    "readings.kind.bazi": "🐉 BaZi",
    "readings.kind.numerology": "🔢 Numerología",
    "readings.kind.human_design": "🧬 Human Design",
    "readings.kind.astrology": "☉ Astrología",
    "readings.kind.vedic": "🕉 Védica",
    "readings.kind.gene_keys": "🗝 Gene Keys",
    "readings.kind.mayan": "🌀 Maya",
    "readings.kind.aspects": "✦ Aspectos",
    # -------------------------------------------------------------------------
    # History — recent readings section
    # -------------------------------------------------------------------------
    "history.readings_title": "📖 Lecturas recientes",
    "history.reading_row": "{kind} · {status} · {date}",
    "history.download": "⬇️ Descargar",
    # -------------------------------------------------------------------------
    # Content moderation
    # -------------------------------------------------------------------------
    "moderation.self_harm": "Si ahora estás en un momento difícil, busca apoyo: {helpline_url}. No sustituyo a un profesional, pero estoy aquí.",
    "moderation.violence": "Esta pregunta queda fuera de lo que puedo ayudarte.",
    "moderation.hate": "No estoy aquí para eso.",
    "moderation.medical": "Eso es para un médico, no para astrología. No doy recomendaciones clínicas.",
    "moderation.legal": "Eso es para un abogado. Puedo hablar de energías y ciclos, no de riesgos legales.",
    "moderation.blocked_generic": "Esta solicitud no se puede procesar.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
    "feature.disabled_generic": "Esta función no está disponible en este bot.",
    "owner.features.title": "⚙️ Funciones",
    "owner.features.btn": "⚙️ Funciones",
    "owner.features.section.readings": "— Lecturas —",
    "owner.features.label.qa": "Pregunta-Respuesta",
    "owner.features.label.blueprint": "Lectura",
    "owner.features.label.transits": "Tránsitos",
    "owner.features.label.daily": "Diario",
    # White-label branding (SP3)
    "brand.signature": "",
    "owner.branding.btn": "🎨 Marca",
    "owner.branding.title": "🎨 Marca (idioma: {language})",
    "owner.branding.label.name": "Nombre",
    "owner.branding.label.welcome": "Bienvenida",
    "owner.branding.label.help": "Ayuda",
    "owner.branding.label.signature": "Firma",
    "owner.branding.prompt": (
        "Envía nuevo texto para **{label}** ({language}), "
        "o /cancel para mantener, /reset para restaurar predeterminado."
    ),
    "owner.branding.saved": "✅ Actualizado.",
    "owner.branding.reset_done": "↩️ Restaurado al predeterminado.",
    "owner.branding.cancelled": "Cancelado.",
    "owner.branding.too_long": "Demasiado largo: {actual} caracteres (máx {limit}).",
    "owner.branding.bad_format": "El nombre debe tener 1-64 caracteres sin saltos de línea.",
    "owner.branding.empty_value": "Valor vacío no permitido. Usa /reset para limpiar.",
    "owner.branding.preview_empty": "(vacío)",
    # -------------------------------------------------------------------------
    # Referral links (SP4)
    # -------------------------------------------------------------------------
    "btn.invite": "🎁 Invitar a un amigo",
    "invite.title": "Invita a tus amigos a este bot.",
    "invite.link_label": "Tu enlace",
    "invite.earned": "Ganado: {credits} créditos de {friends} amigos.",
    "invite.share_text": "Prueba este bot",
    "invite.disabled": "Las referencias están desactivadas en este bot.",
    "invite.unknown_code": "Enlace de referencia no reconocido. Continuando sin bonificación.",
    "owner.referrals.title": "Programa de referidos",
    "owner.referrals.current_value": "Recompensa actual: {value} créditos.",
    "owner.referrals.prompt": "Envía un número entero entre 0 y {max} para cambiar la recompensa.",
    "owner.referrals.saved": "Guardado: {value} créditos.",
    "owner.referrals.reset": "Restablecido al valor predeterminado ({value}).",
    "owner.referrals.too_large": "El valor debe estar entre 0 y {max}.",
    "owner.referrals.not_a_number": "Envía un número entero.",
    "owner.referrals.cancel_hint": "Envía /cancel para cancelar.",
    "owner.referrals.menu_button": "Referidos",
    # -------------------------------------------------------------------------
    # Gift-a-friend (SP5)
    # -------------------------------------------------------------------------
    "btn.gift": "🎁 Regalo",
    "gift.title": "Regala a un amigo",
    "gift.balance_line": "Disponible: {balance}",
    "gift.amount_prompt": "Ingresa el monto del regalo (1–{max}):",
    "gift.cancelled": "Cancelado.",
    "gift.cancel_hint": "Envía /cancel para cancelar.",
    "gift.too_small": "Mínimo 1 crédito.",
    "gift.too_large": "Máximo {max} créditos.",
    "gift.not_a_number": "No es un número. Ingresa un número entero.",
    "gift.no_balance": "No tienes créditos para regalar.",
    "gift.created": "¡Regalo de {amount} créditos listo!\n\nEnlace: {link}",
    "gift.share_text": "¡Un regalo para ti! Abre el bot para reclamar tus créditos.",
    "gift.disabled": "Los regalos no están disponibles ahora.",
    "gift.received": "¡Recibiste un regalo: {amount} créditos!",
    "gift.self_blocked": "No puedes reclamar tu propio regalo.",
    "gift.history_title": "Tus regalos",
    "gift.history_empty": "Aún vacío.",
    "gift.history_row": "{date} — {amount} cr. — {status}",
    "gift.status.active": "pendiente",
    "gift.status.claimed": "reclamado",
    "gift.status.refunded": "reembolsado",
    "gift.btn.create_new": "Crear nuevo",
    "owner.gifts.menu_button": "Regalos",
    "owner.gifts.title": "Regalos",
    "owner.gifts.current_value": "Vida del regalo: {value} días.",
    "owner.gifts.prompt": "Ingresa la vida del regalo en días ({min}–{max}):",
    "owner.gifts.saved": "Guardado.",
    "owner.gifts.reset": "Restablecido al valor predeterminado.",
    "owner.gifts.too_small": "Mínimo {min} día.",
    "owner.gifts.too_large": "Máximo {max} días.",
    "owner.gifts.not_a_number": "Ingresa un número entero.",
    "owner.gifts.cancel_hint": "Envía /cancel para cancelar.",
    # SP6 — Divination (Tarot + I-Ching)
    "readings.kind.tarot": "🔮 Tarot",
    "readings.kind.iching": "☯ I Ching",
    "divination.question_prompt": "Formula tu pregunta o envía /skip:",
    "divination.skip_btn": "Omitir",
    "divination.no_question": "(sin pregunta)",
    "tarot.position.past": "Pasado",
    "tarot.position.present": "Presente",
    "tarot.position.future": "Futuro",
    "tarot.orientation.upright": "derecha",
    "tarot.orientation.reversed": "invertida",
    "iching.judgment_label": "Juicio",
    "iching.image_label": "Imagen",
    "iching.changing_line_label": "Línea mutante {n}",
    "iching.transformed_label": "Se convierte en",
}
