"""Portuguese (pt) UI translations. Keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": "🔮 Blueprint",
    "btn.profile": "👤 Perfil",
    "btn.history": "📜 Histórico",
    "btn.help": "ℹ️ Ajuda",
    "btn.ask": "❓ Perguntar ao astrólogo",
    "btn.transits": "🌌 Trânsitos",
    "btn.daily": "🔔 Horóscopo diário",
    "btn.buy": "💳 Comprar",
    "btn.language": "🌐 Idioma",
    # -------------------------------------------------------------------------
    # Blueprint status words
    # -------------------------------------------------------------------------
    "status.pending": "na fila",
    "status.calculating": "calculando",
    "status.generating": "gerando",
    "status.done": "pronto",
    "status.failed": "erro",
    "status.refunded": "reembolso",
    # -------------------------------------------------------------------------
    # Help text
    # -------------------------------------------------------------------------
    "help.text": (
        "Crio leituras astrológicas pessoais com base nos seus dados natais.\n\n"
        "Menu:\n"
        "❓ Perguntar ao astrólogo — pergunta com o seu contexto natal\n"
        "📖 Leituras — Blueprint, Trânsitos, BaZi, Human Design, Tarot e mais\n"
        "🔔 Horóscopo diário — entrega diária do horóscopo\n"
        "👤 Perfil — data, hora e local de nascimento\n"
        "📜 Histórico — todas as leituras passadas\n"
        "💳 Comprar — pacotes e assinaturas\n"
        "🌐 Idioma — alterar idioma da interface\n"
        "🎁 Convidar um amigo — link de indicação\n"
        "🎁 Presente — oferecer créditos a um amigo\n\n"
        "Suporte: @quantuum_support"
    ),
    # -------------------------------------------------------------------------
    # Profile display
    # -------------------------------------------------------------------------
    "profile.title": "👤 Seu perfil:",
    "profile.name": "Nome: {name}",
    "profile.birth_date": "Data de nascimento: {birth_date}",
    "profile.birth_time": "Hora: {birth_time}",
    "profile.place": "Local: {place}",
    # -------------------------------------------------------------------------
    # Profile screen messages
    # -------------------------------------------------------------------------
    "profile.empty": "Perfil não preenchido.",
    "profile.not_found": "Perfil não encontrado.",
    "profile.place.confirm": "Encontrado: {place}\n\nCorreto?",
    "profile.place.not_found": "Não encontrei esse local. Refine a cidade / endereço ou envie uma localização:",
    # -------------------------------------------------------------------------
    # Profile keyboard labels
    # -------------------------------------------------------------------------
    "profile.kb.fill": "📝 Preencher perfil",
    "profile.kb.edit_name": "✏️ Nome",
    "profile.kb.edit_birth_date": "✏️ Data",
    "profile.kb.edit_birth_time": "✏️ Hora",
    "profile.kb.edit_birth_place": "✏️ Local",
    "profile.kb.place_confirm": "✅ Sim",
    "profile.kb.place_retry": "✏️ Outro endereço",
    # -------------------------------------------------------------------------
    # Profile field prompts (edit flow)
    # -------------------------------------------------------------------------
    "profile.prompt.name": "Digite seu nome:",
    "profile.prompt.birth_date": "Data de nascimento AAAA-MM-DD (ex.: 1980-06-24):",
    "profile.prompt.birth_time": "Hora de nascimento HH:MM (ex.: 10:00):",
    "profile.prompt.birth_place": "Envie sua localização (📎 → Localização) ou digite uma cidade / endereço:",
    # -------------------------------------------------------------------------
    # Profile field validation errors
    # -------------------------------------------------------------------------
    "profile.error.name_empty": "O nome não pode estar vazio.",
    "profile.error.birth_date_invalid": "Não foi possível interpretar a data. Formato AAAA-MM-DD.",
    "profile.error.birth_time_invalid": "Não foi possível interpretar a hora. Formato HH:MM.",
    "profile.error.unknown_field": "Campo desconhecido.",
    "profile.field_edit_error": "{err}\nTente novamente:",
    # -------------------------------------------------------------------------
    # Start / welcome
    # -------------------------------------------------------------------------
    "start.welcome": "Olá! Vou construir sua leitura astrológica ✨",
    # -------------------------------------------------------------------------
    # Main menu
    # -------------------------------------------------------------------------
    "menu.title": "Menu principal:",
    "menu.cancelled": "Cancelado.",
    # -------------------------------------------------------------------------
    # Generate (blueprint request)
    # -------------------------------------------------------------------------
    "generate.no_profile": "Por favor, preencha seu perfil primeiro:",
    "generate.no_quota": "Sua geração gratuita já foi utilizada. Compre um pacote ou assinatura:",
    "generate.queued": "Gerando sua leitura, isso levará cerca de um minuto…",
    # -------------------------------------------------------------------------
    # Q&A astrologer
    # -------------------------------------------------------------------------
    "qa.ask_prompt": "Envie sua pergunta ao astrólogo:",
    "qa.thinking": "Pensando na sua resposta… ⏳",
    "qa.no_profile": "Preencha seu perfil natal primeiro (/profile).",
    "qa.no_quota": "Seus créditos acabaram. Compre um pacote ou assinatura para perguntar ao astrólogo:",
    "qa.too_long": "Pergunta muito longa (máx. 1000 caracteres).",
    "qa.empty": "Pergunta vazia. Por favor, escreva sua pergunta:",
    # -------------------------------------------------------------------------
    # Transits
    # -------------------------------------------------------------------------
    "transit.thinking": "Calculando seus trânsitos… ⏳",
    "transit.no_profile": "Preencha seu perfil natal primeiro (/profile).",
    "transit.no_quota": "Seus créditos acabaram. Compre um pacote ou assinatura para ver seus trânsitos:",
    "transit.failed": "Não foi possível calcular os trânsitos. Tente novamente mais tarde.",
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": "🌟 Horóscopo de hoje",
    "daily.status_on": "Horóscopo diário ativado. Horário de entrega: {hour}:00 (seu fuso horário).",
    "daily.status_off": "Horóscopo diário desativado.",
    "daily.not_subscriber": "O horóscopo diário é um recurso para assinantes. Assine para recebê-lo toda manhã:",
    "daily.no_profile": "Preencha seu perfil natal primeiro (/profile).",
    "daily.enabled": "Horóscopo diário ativado ✅",
    "daily.disabled": "Horóscopo diário desativado.",
    "daily.hour_set": "Horário de entrega: {hour}:00 ✅",
    "daily.kb.turn_on": "🔔 Ativar",
    "daily.kb.close": "✅ Pronto",
    "daily.kb.turn_off": "🔕 Desativar",
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": "Nenhuma leitura ainda. Toque em «🔮 Blueprint» para criar a primeira.",
    "history.title": "📜 Histórico de leituras:",
    "history.label": "🔮 {date} · {status}",
    "history.detail_header": "🔮 Blueprint #{id}",
    "history.detail_status": "Status: {status}",
    "history.detail_created": "Criado: {created_at}",
    "history.detail_ready": "Pronto: {completed_at}",
    "history.not_found": "Não encontrado",
    # -------------------------------------------------------------------------
    # History / blueprint detail keyboard labels
    # -------------------------------------------------------------------------
    "history.kb.download": "📥 Baixar .md",
    "history.kb.preview": "👁 Pré-visualização",
    "history.kb.back": "← Voltar",
    "history.kb.prev_page": "← Ant.",
    "history.kb.next_page": "Próx. →",
    "history.unavailable": "Indisponível",
    # -------------------------------------------------------------------------
    # Buy / payments
    # -------------------------------------------------------------------------
    "buy.menu_title": "Escolha o que comprar (pagamento via Telegram Stars ★):",
    "buy.no_plans": "Nenhum plano disponível ainda. Volte mais tarde.",
    "buy.plan_subscription": "⭐ {name} — {price}★",
    "buy.plan_package": "⭐ {name} · {count} leituras — {price}★",
    "buy.invoice_subscription": "Assinatura por {period_days} dias",
    "buy.invoice_package": "Pacote: {count} leituras",
    "buy.plan_unavailable": "Este plano não está mais disponível.",
    "buy.payment_success": "Pagamento recebido! Acesso ativado. ✨",
    "buy.payment_already_credited": "Este pagamento já foi creditado anteriormente.",
    "buy.kb.open": "💳 Comprar leituras",
    # -------------------------------------------------------------------------
    # Shared / generic
    # -------------------------------------------------------------------------
    "kb.cancel": "✖️ Cancelar",
    "errors.queue_failed": "Não foi possível colocar seu pedido na fila. Seu crédito foi devolvido — tente novamente em instantes.",
    # -------------------------------------------------------------------------
    # Master bot — owner onboarding
    # -------------------------------------------------------------------------
    "master.onboard.invite_invalid": "O convite é inválido ou expirou.",
    "master.onboard.slug_prompt": "Bem-vindo! Vamos criar um bot. Digite o slug do tenant (letras latinas, sem espaços){prefill}:",
    "master.onboard.slug_prefill": " (sugerido: {slug})",
    "master.onboard.plain_start": "Este é o bot de onboarding da plataforma. Abra um link de convite para criar seu próprio bot.",
    "master.onboard.slug_invalid": "O slug não pode estar vazio ou conter espaços. Tente novamente:",
    "master.onboard.slug_taken": "Este slug já está em uso. Digite outro:",
    "master.onboard.display_name_prompt": "Nome de exibição do produto (ex.: «Acme Astro»):",
    "master.onboard.display_name_empty": "O nome não pode estar vazio. Digite novamente:",
    "master.onboard.lang_prompt": "Idioma padrão (código de duas letras, ex.: ru ou en):",
    "master.onboard.lang_invalid": "Um código de idioma de duas letras é necessário, ex.: ru. Digite novamente:",
    "master.onboard.confirm": (
        "Verifique os dados:\nslug: {slug}\nnome: {display_name}\nidioma: {language}\n\n"
        "Criar o bot?"
    ),
    "master.onboard.invite_gone": "O convite não é mais válido.",
    "master.onboard.creating": "Criando o tenant… Verificando se o bot pode ser criado automaticamente.",
    "master.onboard.cancelled": "Onboarding cancelado.",
    "master.onboard.token_invalid": "Isso não parece um token de bot válido. Envie o token do @BotFather novamente:",
    "master.onboard.token_in_use": "Este bot já está vinculado a outro projeto. Use um bot diferente.",
    "master.onboard.done": "Pronto! O bot @{username} está ativado. Ficará disponível após a reinicialização do worker.",
    "master.kb.cancel": "Cancelar",
    "master.kb.create_bot": "Criar bot",
    # -------------------------------------------------------------------------
    # Master bot — owner console
    # -------------------------------------------------------------------------
    "owner.tenants.empty": "Você ainda não tem tenants. Crie um bot via link de convite.",
    "owner.tenants.header": "Seus tenants:",
    "owner.tenants.line": "• {display_name} (/{slug}) — {status}",
    "owner.tenants.hint": "\nGerenciar: /manage <slug>",
    "owner.manage.usage": "Uso: /manage <slug>",
    "owner.manage.not_found": "Tenant não encontrado ou você não tem permissão.",
    "owner.manage.title": "Gerenciar: {display_name} (/{slug}) — {status}",
    "owner.manage.kb.stats": "📊 Estatísticas",
    "owner.manage.kb.pause": "⏸ Pausar",
    "owner.manage.kb.resume": "▶️ Retomar",
    "owner.manage.kb.transfer": "🔁 Transferir propriedade",
    "owner.stats.text": (
        "📊 Estatísticas (últimos {period_days} dias)\n"
        "Ativos: {active_customers}, pagantes: {paid_customers}\n"
        "DAU/WAU/MAU: {dau}/{wau}/{mau}\n"
        "Receita: {revenue_cents}, MRR: {mrr_cents}\n"
        "Solicitações: {requests_by_kind}"
    ),
    "owner.no_rights": "Sem permissão",
    "owner.pause.platform_blocked": "O tenant da plataforma não pode ser pausado",
    "owner.pause.done": "⏸ Pausado.",
    "owner.resume.done": "▶️ Retomado.",
    "owner.manage.kb.delete": "🗑 Excluir",
    "owner.delete.prompt": (
        "⚠️ Isso excluirá permanentemente o bot e ocultará o tenant. "
        "Para confirmar, envie o slug: {slug}\n(ou /cancel)"
    ),
    "owner.delete.mismatch": "O slug não confere. Envie {slug} novamente ou /cancel.",
    "owner.delete.done": "🗑 Bot excluído.",
    "owner.delete.cancelled": "Cancelado.",
    "owner.delete.platform_blocked": "O tenant da plataforma não pode ser excluído",
    # -------------------------------------------------------------------------
    # Superadmin cabinet
    # -------------------------------------------------------------------------
    "admin.denied": "Não autorizado.",
    "admin.menu.title": "🛠 Painel do superadmin",
    "admin.menu.kb.tenants": "🏢 Bots",
    "admin.menu.kb.invites": "🎟 Convites",
    "admin.tenants.title": "Todos os bots:",
    "admin.tenants.empty": "Nenhum bot ainda.",
    "admin.tenant.title": "Bot: {display_name} (/{slug}) — {status}",
    "admin.tenant.kb.stats": "📊 Estatísticas",
    "admin.tenant.kb.suspend": "⏸ Suspender",
    "admin.tenant.kb.resume": "▶️ Retomar",
    "admin.tenant.kb.delete": "🗑 Excluir",
    "admin.kb.back": "⬅️ Voltar",
    "admin.tenant.suspended": "⏸ Bot suspenso.",
    "admin.tenant.resumed": "▶️ Bot retomado.",
    "admin.invites.title": "Convites ativos:",
    "admin.invites.empty": "Nenhum convite ativo.",
    "admin.invites.kb.new": "➕ Novo convite",
    "admin.invite.kb.revoke": "🗑 Revogar",
    "admin.invite.created": "Convite criado:\n{link}",
    "admin.invite.revoked": "Convite revogado.",
    "admin.stale": "Não encontrado — lista atualizada.",
    # -------------------------------------------------------------------------
    # Transfer ownership
    # -------------------------------------------------------------------------
    "owner.transfer.usage": "Uso: /transfer <slug>",
    "owner.transfer.not_owner": "Tenant não encontrado ou você não é o proprietário.",
    "owner.transfer.prompt": (
        "Informe o Telegram ID do novo proprietário (um número). "
        "Ele já deve ter uma conta neste tenant (ter iniciado seu bot)."
    ),
    "owner.transfer.cancelled": "Cancelado.",
    "owner.transfer.target_invalid": "É necessário um Telegram ID numérico. Tente novamente ou /cancel.",
    "owner.transfer.no_rights_anymore": "Você não tem mais permissão para transferir.",
    "owner.transfer.no_account": (
        "Este usuário não tem conta no tenant. "
        "Ele deve iniciar seu bot primeiro."
    ),
    "owner.transfer.done": "✅ Pronto. Propriedade transferida.",
    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    "lang.prompt": "Escolha seu idioma:",
    "lang.changed": "Idioma atualizado.",
    # -------------------------------------------------------------------------
    # Onboarding flow
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": "Digite seu nome completo (como na certidão de nascimento):",
    "onb.error.full_name": "Não consegui ler o nome. Digite seu nome completo como texto:",
    "onb.prompt.birth_date": "Data de nascimento no formato AAAA-MM-DD (ex.: 1980-06-24):",
    "onb.error.birth_date": "Não consegui ler a data. Formato AAAA-MM-DD:",
    "onb.prompt.birth_time": "Hora de nascimento HH:MM (ex.: 10:00):",
    "onb.error.birth_time": "Não consegui ler a hora. Formato HH:MM:",
    "onb.prompt.birth_place": (
        "Local de nascimento: envie sua localização (📎 → Localização, você pode marcar um ponto "
        "no mapa) ou digite uma cidade / parte de um endereço:"
    ),
    "onb.done": "Pronto! O seu perfil foi salvo. Toque em «🔮 Blueprint» no menu abaixo.",
    # Owner console — user management
    "owner.manage.kb.users": "👥 Usuários",
    "owner.users.header": "Usuários de {display_name}:",
    "owner.users.empty": "Ainda não há usuários.",
    "owner.users.row": "{name} · {credits}💎",
    "owner.users.unnamed": "usuário #{id}",
    "owner.users.nav.prev": "◀️",
    "owner.users.nav.next": "▶️",
    "owner.user.card": (
        "👤 {name}\nTelegram ID: {tg_id}\nCréditos: {credits}💎\n"
        "Assinatura: {subscription}\nStatus: {status}"
    ),
    "owner.user.card.banned": "🚫 Banido. Motivo: {reason}",
    "owner.user.status.active": "ativo",
    "owner.user.status.banned": "banido",
    "owner.user.not_found": "Usuário não encontrado.",
    "owner.user.kb.grant": "💎 Ajustar créditos",
    "owner.user.kb.ban": "🚫 Banir",
    "owner.user.kb.unban": "✅ Desbanir",
    "owner.user.kb.back": "⬅️ À lista",
    "owner.user.grant.prompt": "Digite o número de créditos (pode ser negativo, ex.: -3):",
    "owner.user.grant.invalid": "Não entendi. Digite um número inteiro, ex.: 5 ou -2.",
    "owner.user.grant.done": "Concluído. Novo saldo: {credits}💎.",
    "owner.user.ban.prompt": "Digite o motivo do banimento:",
    "owner.user.ban.invalid": "O motivo não pode estar vazio. Digite um motivo:",
    "owner.user.ban.done": "Usuário banido.",
    "owner.user.ban.staff_blocked": "Você não pode banir um proprietário ou administrador.",
    "owner.user.unban.done": "Usuário desbanido.",
    "owner.user.cancelled": "Cancelado.",
    "account.banned.notice": "🚫 Seu acesso ao bot está restrito. Motivo: {reason}",
    # -------------------------------------------------------------------------
    # Readings submenu
    # -------------------------------------------------------------------------
    "btn.readings": "📖 Leituras",
    "readings.menu.title": "Qual leitura você gostaria?",
    "readings.queued": "Estou preparando sua leitura. Levará um minuto.",
    "readings.no_profile": "Primeiro, preencha seu perfil de nascimento.",
    "readings.no_quota": "Sem créditos disponíveis. Compre um pacote para continuar.",
    "readings.kind.bazi": "🐉 BaZi",
    "readings.kind.numerology": "🔢 Numerologia",
    "readings.kind.human_design": "🧬 Human Design",
    "readings.kind.astrology": "☉ Astrologia",
    "readings.kind.vedic": "🕉 Védica",
    "readings.kind.gene_keys": "🗝 Gene Keys",
    "readings.kind.mayan": "🌀 Maia",
    "readings.kind.aspects": "✦ Aspectos",
    # -------------------------------------------------------------------------
    # History — recent readings section
    # -------------------------------------------------------------------------
    "history.readings_title": "📖 Leituras recentes",
    "history.reading_row": "{kind} · {status} · {date}",
    "history.download": "⬇️ Baixar",
    # -------------------------------------------------------------------------
    # Content moderation
    # -------------------------------------------------------------------------
    "moderation.self_harm": "Se você está num momento difícil, procure apoio: {helpline_url}. Não substituo um profissional, mas estou aqui.",
    "moderation.violence": "Essa pergunta está fora do que posso ajudar.",
    "moderation.hate": "Não estou aqui para isso.",
    "moderation.medical": "Isso é com um médico, não com astrologia. Não dou orientação clínica.",
    "moderation.legal": "Isso é com um advogado. Falo de energias e ciclos, não de riscos jurídicos.",
    "moderation.blocked_generic": "Esta solicitação não pode ser processada.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
    "feature.disabled_generic": "Este recurso não está disponível neste bot.",
    "owner.features.title": "⚙️ Recursos",
    "owner.features.btn": "⚙️ Recursos",
    "owner.features.section.readings": "— Leituras —",
    "owner.features.label.qa": "Pergunta-Resposta",
    "owner.features.label.blueprint": "Leitura",
    "owner.features.label.transits": "Trânsitos",
    "owner.features.label.daily": "Diário",
    # White-label branding (SP3)
    "brand.signature": "",
    "owner.branding.btn": "🎨 Marca",
    "owner.branding.title": "🎨 Marca (idioma: {language})",
    "owner.branding.label.name": "Nome",
    "owner.branding.label.welcome": "Boas-vindas",
    "owner.branding.label.help": "Ajuda",
    "owner.branding.label.signature": "Assinatura",
    "owner.branding.prompt": (
        "Envie o novo texto para **{label}** ({language}), "
        "ou /cancel para manter, /reset para restaurar o padrão."
    ),
    "owner.branding.saved": "✅ Atualizado.",
    "owner.branding.reset_done": "↩️ Restaurado para o padrão.",
    "owner.branding.cancelled": "Cancelado.",
    "owner.branding.too_long": "Muito longo: {actual} caracteres (máx {limit}).",
    "owner.branding.bad_format": "Nome deve ter 1-64 caracteres sem quebras de linha.",
    "owner.branding.empty_value": "Valor vazio não permitido. Use /reset para limpar.",
    "owner.branding.preview_empty": "(vazio)",
    # -------------------------------------------------------------------------
    # Referral links (SP4)
    # -------------------------------------------------------------------------
    "btn.invite": "🎁 Convidar um amigo",
    "invite.title": "Convide amigos para este bot.",
    "invite.link_label": "Seu link",
    "invite.earned": "Ganho: {credits} créditos de {friends} amigos.",
    "invite.share_text": "Experimente este bot",
    "invite.disabled": "Indicações estão desativadas neste bot.",
    "invite.unknown_code": "Link de indicação não reconhecido. Continuando sem bônus.",
    "owner.referrals.title": "Programa de indicação",
    "owner.referrals.current_value": "Recompensa atual: {value} créditos.",
    "owner.referrals.prompt": "Envie um inteiro entre 0 e {max} para alterar a recompensa.",
    "owner.referrals.saved": "Salvo: {value} créditos.",
    "owner.referrals.reset": "Redefinido para o padrão ({value}).",
    "owner.referrals.too_large": "O valor deve estar no intervalo 0-{max}.",
    "owner.referrals.not_a_number": "Envie um número inteiro.",
    "owner.referrals.cancel_hint": "Envie /cancel para cancelar.",
    "owner.referrals.menu_button": "Indicações",
    # -------------------------------------------------------------------------
    # Gift-a-friend (SP5)
    # -------------------------------------------------------------------------
    "btn.gift": "🎁 Presente",
    "gift.title": "Presenteie um amigo",
    "gift.balance_line": "Disponível: {balance}",
    "gift.amount_prompt": "Digite o valor do presente (1–{max}):",
    "gift.cancelled": "Cancelado.",
    "gift.cancel_hint": "Envie /cancel para cancelar.",
    "gift.too_small": "Mínimo 1 crédito.",
    "gift.too_large": "Máximo {max} créditos.",
    "gift.not_a_number": "Não é um número. Digite um número inteiro.",
    "gift.no_balance": "Você não tem créditos para presentear.",
    "gift.created": "Presente de {amount} créditos pronto!\n\nLink: {link}",
    "gift.share_text": "Um presente pra você! Abra o bot para resgatar seus créditos.",
    "gift.disabled": "Presentes não estão disponíveis no momento.",
    "gift.received": "Você recebeu um presente: {amount} créditos!",
    "gift.self_blocked": "Você não pode resgatar seu próprio presente.",
    "gift.history_title": "Seus presentes",
    "gift.history_empty": "Ainda vazio.",
    "gift.history_row": "{date} — {amount} cr. — {status}",
    "gift.status.active": "pendente",
    "gift.status.claimed": "resgatado",
    "gift.status.refunded": "reembolsado",
    "gift.btn.create_new": "Criar novo",
    "owner.gifts.menu_button": "Presentes",
    "owner.gifts.title": "Presentes",
    "owner.gifts.current_value": "Validade do presente: {value} dias.",
    "owner.gifts.prompt": "Digite a validade do presente em dias ({min}–{max}):",
    "owner.gifts.saved": "Salvo.",
    "owner.gifts.reset": "Redefinido para padrão.",
    "owner.gifts.too_small": "Mínimo {min} dia.",
    "owner.gifts.too_large": "Máximo {max} dias.",
    "owner.gifts.not_a_number": "Digite um número inteiro.",
    "owner.gifts.cancel_hint": "Envie /cancel para cancelar.",
    # SP6 — Divination (Tarot + I-Ching)
    "readings.kind.tarot": "🔮 Tarot",
    "readings.kind.iching": "☯ I Ching",
    "divination.question_prompt": "Formule sua pergunta ou envie /skip:",
    "divination.skip_btn": "Pular",
    "divination.no_question": "(sem pergunta)",
    "tarot.position.past": "Passado",
    "tarot.position.present": "Presente",
    "tarot.position.future": "Futuro",
    "tarot.orientation.upright": "em pé",
    "tarot.orientation.reversed": "invertida",
    "iching.judgment_label": "Julgamento",
    "iching.image_label": "Imagem",
    "iching.changing_line_label": "Linha mutante {n}",
    "iching.transformed_label": "Torna-se",
    # Console UX nav + provisioning
    "owner.manage.kb.back": "⬅️ Voltar ao menu",
    "owner.features.label.referrals": "Indicações",
    "owner.features.label.gifts": "Presentes",
    "master.provision.manual_prompt": (
        "A criação automática do bot não está disponível. Crie um novo bot pelo "
        "@BotFather e envie o token dele aqui em uma única mensagem."
    ),
    "master.provision.managed_prompt": (
        "Toque no botão abaixo — o Telegram criará o bot e eu o assumirei automaticamente. "
        "Você pode ajustar o nome de usuário na tela de criação."
    ),
    "master.provision.managed_button": "🤖 Criar bot",
}
