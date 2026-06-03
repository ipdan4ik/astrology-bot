"""Simplified Chinese (zh) UI translations. Keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": "🔮 Blueprint",
    "btn.profile": "👤 档案",
    "btn.history": "📜 历史",
    "btn.help": "ℹ️ 帮助",
    "btn.ask": "❓ 咨询占星师",
    "btn.transits": "🌌 行运",
    "btn.daily": "🔔 每日星座运势",
    "btn.buy": "💳 购买",
    "btn.language": "🌐 语言",
    # -------------------------------------------------------------------------
    # Blueprint status words
    # -------------------------------------------------------------------------
    "status.pending": "排队中",
    "status.calculating": "计算中",
    "status.generating": "生成中",
    "status.done": "完成",
    "status.failed": "失败",
    "status.refunded": "已退款",
    # -------------------------------------------------------------------------
    # Help text
    # -------------------------------------------------------------------------
    "help.text": (
        "我根据您的出生数据生成个性化占星解读。\n\n"
        "菜单：\n"
        "❓ 咨询占星师 — 结合您的星盘回答问题\n"
        "📖 解读 — Blueprint、行运、BaZi、人类设计、塔罗等\n"
        "🔔 每日运势 — 每天自动推送运势\n"
        "👤 个人资料 — 出生日期、时间和地点\n"
        "📜 历史记录 — 所有过往解读\n"
        "💳 购买 — 套餐和订阅\n"
        "🌐 语言 — 更改界面语言\n"
        "🎁 邀请朋友 — 推荐链接\n"
        "🎁 礼物 — 赠送积分给朋友\n\n"
        "客服：@quantuum_support"
    ),
    # -------------------------------------------------------------------------
    # Profile display
    # -------------------------------------------------------------------------
    "profile.title": "👤 您的档案：",
    "profile.name": "姓名：{name}",
    "profile.birth_date": "出生日期：{birth_date}",
    "profile.birth_time": "出生时间：{birth_time}",
    "profile.place": "出生地点：{place}",
    # -------------------------------------------------------------------------
    # Profile screen messages
    # -------------------------------------------------------------------------
    "profile.empty": "档案尚未填写。",
    "profile.not_found": "未找到档案。",
    "profile.place.confirm": "找到：{place}\n\n确认无误？",
    "profile.place.not_found": "未能找到该地点。请提供更精确的城市/地址，或发送位置：",
    # -------------------------------------------------------------------------
    # Profile keyboard labels
    # -------------------------------------------------------------------------
    "profile.kb.fill": "📝 填写档案",
    "profile.kb.edit_name": "✏️ 姓名",
    "profile.kb.edit_birth_date": "✏️ 日期",
    "profile.kb.edit_birth_time": "✏️ 时间",
    "profile.kb.edit_birth_place": "✏️ 地点",
    "profile.kb.place_confirm": "✅ 是",
    "profile.kb.place_retry": "✏️ 重新输入地址",
    # -------------------------------------------------------------------------
    # Profile field prompts (edit flow)
    # -------------------------------------------------------------------------
    "profile.prompt.name": "请输入姓名：",
    "profile.prompt.birth_date": "出生日期 YYYY-MM-DD（例如 1980-06-24）：",
    "profile.prompt.birth_time": "出生时间 HH:MM（例如 10:00）：",
    "profile.prompt.birth_place": "发送您的位置（📎 → 位置）或输入城市/地址：",
    # -------------------------------------------------------------------------
    # Profile field validation errors
    # -------------------------------------------------------------------------
    "profile.error.name_empty": "姓名不能为空。",
    "profile.error.birth_date_invalid": "无法识别日期。格式：YYYY-MM-DD。",
    "profile.error.birth_time_invalid": "无法识别时间。格式：HH:MM。",
    "profile.error.unknown_field": "未知字段。",
    "profile.field_edit_error": "{err}\n请重试：",
    # -------------------------------------------------------------------------
    # Start / welcome
    # -------------------------------------------------------------------------
    "start.welcome": "您好！我将为您生成占星解读 ✨",
    # -------------------------------------------------------------------------
    # Main menu
    # -------------------------------------------------------------------------
    "menu.title": "主菜单：",
    "menu.cancelled": "已取消。",
    # -------------------------------------------------------------------------
    # Generate (blueprint request)
    # -------------------------------------------------------------------------
    "generate.no_profile": "请先填写您的档案：",
    "generate.no_quota": "免费次数已用完。请购买解读套餐或订阅：",
    "generate.queued": "正在生成您的解读，大约需要一分钟……",
    # -------------------------------------------------------------------------
    # Q&A astrologer
    # -------------------------------------------------------------------------
    "qa.ask_prompt": "请向占星师提问：",
    "qa.thinking": "正在思考回答… ⏳",
    "qa.no_profile": "请先填写本命档案（/profile）。",
    "qa.no_quota": "您的次数已用完。请购买套餐或订阅后再向占星师提问：",
    "qa.too_long": "问题过长（最多 1000 个字符）。",
    "qa.empty": "问题为空。请输入您的问题：",
    # -------------------------------------------------------------------------
    # Transits
    # -------------------------------------------------------------------------
    "transit.thinking": "正在计算行运… ⏳",
    "transit.no_profile": "请先填写本命档案（/profile）。",
    "transit.no_quota": "您的次数已用完。请购买套餐或订阅后查看行运：",
    "transit.failed": "无法计算行运。请稍后再试。",
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": "🌟 今日星座运势",
    "daily.status_on": "每日星座运势已开启。推送时间：{hour}:00（您的时区）。",
    "daily.status_off": "每日星座运势已关闭。",
    "daily.not_subscriber": "每日星座运势是订阅专属功能。订阅后每天早晨接收：",
    "daily.no_profile": "请先填写本命档案（/profile）。",
    "daily.enabled": "每日星座运势已开启 ✅",
    "daily.disabled": "每日星座运势已关闭。",
    "daily.hour_set": "推送时间：{hour}:00 ✅",
    "daily.kb.turn_on": "🔔 开启",
    "daily.kb.close": "✅ 完成",
    "daily.kb.turn_off": "🔕 关闭",
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": "暂无解读记录。点击「🔮 解读」创建第一条。",
    "history.title": "📜 解读历史：",
    "history.label": "🔮 {date} · {status}",
    "history.detail_header": "🔮 解读 #{id}",
    "history.detail_status": "状态：{status}",
    "history.detail_created": "创建时间：{created_at}",
    "history.detail_ready": "完成时间：{completed_at}",
    "history.not_found": "未找到",
    # -------------------------------------------------------------------------
    # History / blueprint detail keyboard labels
    # -------------------------------------------------------------------------
    "history.kb.download": "📥 下载 .md",
    "history.kb.preview": "👁 预览",
    "history.kb.back": "← 返回",
    "history.kb.prev_page": "← 上一页",
    "history.kb.next_page": "下一页 →",
    "history.unavailable": "不可用",
    # -------------------------------------------------------------------------
    # Buy / payments
    # -------------------------------------------------------------------------
    "buy.menu_title": "请选择购买内容（通过 Telegram Stars ★ 支付）：",
    "buy.no_plans": "暂无可用套餐，请稍后再查看。",
    "buy.plan_subscription": "⭐ {name} — {price}★",
    "buy.plan_package": "⭐ {name} · {count} 次解读 — {price}★",
    "buy.invoice_subscription": "订阅 {period_days} 天",
    "buy.invoice_package": "套餐：{count} 次解读",
    "buy.plan_unavailable": "该套餐已不再提供。",
    "buy.payment_success": "付款成功！权限已激活。✨",
    "buy.payment_already_credited": "此付款已被记录。",
    "buy.kb.open": "💳 购买解读",
    # -------------------------------------------------------------------------
    # Shared / generic
    # -------------------------------------------------------------------------
    "kb.cancel": "✖️ 取消",
    # -------------------------------------------------------------------------
    # Master bot — owner onboarding
    # -------------------------------------------------------------------------
    "master.onboard.invite_invalid": "邀请链接无效或已过期。",
    "master.onboard.slug_prompt": "欢迎！让我们创建一个机器人。请输入租户 slug（仅限拉丁字母，不含空格）{prefill}：",
    "master.onboard.slug_prefill": "（建议：{slug}）",
    "master.onboard.plain_start": "这是平台入驻机器人。请打开邀请链接以创建您自己的机器人。",
    "master.onboard.slug_invalid": "Slug 不得为空或包含空格。请重试：",
    "master.onboard.slug_taken": "此 slug 已被占用。请输入其他 slug：",
    "master.onboard.display_name_prompt": "产品显示名称（例如「Acme Astro」）：",
    "master.onboard.display_name_empty": "名称不得为空。请重新输入：",
    "master.onboard.lang_prompt": "默认语言（两字母代码，例如 ru 或 en）：",
    "master.onboard.lang_invalid": "需要两字母语言代码，例如 ru。请重新输入：",
    "master.onboard.confirm": (
        "请核对信息：\nslug: {slug}\n名称: {display_name}\n语言: {language}\n\n"
        "创建机器人？"
    ),
    "master.onboard.invite_gone": "邀请链接已失效。",
    "master.onboard.creating": "正在创建租户… 正在检查是否可以自动创建机器人。",
    "master.onboard.cancelled": "入驻已取消。",
    "master.onboard.token_invalid": "这不像是有效的机器人 token。请重新发送来自 @BotFather 的 token：",
    "master.onboard.done": "完成！机器人 @{username} 已激活。重启 worker 后即可使用。",
    "master.kb.cancel": "取消",
    "master.kb.create_bot": "创建机器人",
    # -------------------------------------------------------------------------
    # Master bot — owner console
    # -------------------------------------------------------------------------
    "owner.tenants.empty": "您还没有任何租户。请通过邀请链接创建机器人。",
    "owner.tenants.header": "您的租户：",
    "owner.tenants.line": "• {display_name} (/{slug}) — {status}",
    "owner.tenants.hint": "\n管理：/manage <slug>",
    "owner.manage.usage": "用法：/manage <slug>",
    "owner.manage.not_found": "未找到租户或您没有权限。",
    "owner.manage.title": "管理：{display_name} (/{slug}) — {status}",
    "owner.manage.kb.stats": "📊 统计",
    "owner.manage.kb.pause": "⏸ 暂停",
    "owner.manage.kb.resume": "▶️ 恢复",
    "owner.manage.kb.transfer": "🔁 转让所有权",
    "owner.stats.text": (
        "📊 统计（最近 {period_days} 天）\n"
        "活跃用户：{active_customers}，付费用户：{paid_customers}\n"
        "DAU/WAU/MAU: {dau}/{wau}/{mau}\n"
        "收入：{revenue_cents}，MRR: {mrr_cents}\n"
        "请求量：{requests_by_kind}"
    ),
    "owner.no_rights": "无权限",
    "owner.pause.platform_blocked": "平台租户不可暂停",
    "owner.pause.done": "⏸ 已暂停。",
    "owner.resume.done": "▶️ 已恢复。",
    "owner.manage.kb.delete": "🗑 删除",
    "owner.delete.prompt": (
        "⚠️ 这将永久删除机器人并隐藏租户。"
        "请发送 slug 以确认：{slug}\n（或 /cancel）"
    ),
    "owner.delete.mismatch": "Slug 不匹配。请重新发送 {slug} 或 /cancel。",
    "owner.delete.done": "🗑 机器人已删除。",
    "owner.delete.cancelled": "已取消。",
    "owner.delete.platform_blocked": "平台租户不可删除",
    # -------------------------------------------------------------------------
    # Superadmin cabinet
    # -------------------------------------------------------------------------
    "admin.denied": "无授权。",
    "admin.menu.title": "🛠 超级管理员面板",
    "admin.menu.kb.tenants": "🏢 机器人",
    "admin.menu.kb.invites": "🎟 邀请",
    "admin.tenants.title": "所有机器人：",
    "admin.tenants.empty": "暂无机器人。",
    "admin.tenant.title": "机器人：{display_name} (/{slug}) — {status}",
    "admin.tenant.kb.stats": "📊 统计",
    "admin.tenant.kb.suspend": "⏸ 暂停",
    "admin.tenant.kb.resume": "▶️ 恢复",
    "admin.tenant.kb.delete": "🗑 删除",
    "admin.kb.back": "⬅️ 返回",
    "admin.tenant.suspended": "⏸ 机器人已暂停。",
    "admin.tenant.resumed": "▶️ 机器人已恢复。",
    "admin.invites.title": "有效邀请：",
    "admin.invites.empty": "暂无有效邀请。",
    "admin.invites.kb.new": "➕ 新建邀请",
    "admin.invite.kb.revoke": "🗑 撤销",
    "admin.invite.created": "邀请已创建：\n{link}",
    "admin.invite.revoked": "邀请已撤销。",
    "admin.stale": "未找到 — 列表已刷新。",
    # -------------------------------------------------------------------------
    # Transfer
    # -------------------------------------------------------------------------
    "owner.transfer.usage": "用法：/transfer <slug>",
    "owner.transfer.not_owner": "未找到租户或您不是所有者。",
    "owner.transfer.prompt": (
        "请转发新所有者的 Telegram ID（数字）。"
        "该用户必须已在此租户中拥有账户（已启动您的机器人）。"
    ),
    "owner.transfer.cancelled": "已取消。",
    "owner.transfer.target_invalid": "需要有效的数字 Telegram ID。请重试或 /cancel。",
    "owner.transfer.no_rights_anymore": "您已失去转让权限。",
    "owner.transfer.no_account": (
        "该用户在租户中没有账户。"
        "他们必须先启动您的机器人。"
    ),
    "owner.transfer.done": "✅ 完成。所有权已转让。",
    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    "lang.prompt": "请选择语言：",
    "lang.changed": "语言已更新。",
    # -------------------------------------------------------------------------
    # Onboarding flow
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": "请输入全名（与出生证明一致）：",
    "onb.error.full_name": "无法识别姓名。请以文字输入全名：",
    "onb.prompt.birth_date": "出生日期，格式 YYYY-MM-DD（例如 1980-06-24）：",
    "onb.error.birth_date": "无法识别日期。格式 YYYY-MM-DD：",
    "onb.prompt.birth_time": "出生时间 HH:MM（例如 10:00）：",
    "onb.error.birth_time": "无法识别时间。格式 HH:MM：",
    "onb.prompt.birth_place": (
        "出生地点：发送位置（📎 → 位置，可在地图上标记）或输入城市/部分地址："
    ),
    "onb.done": "完成！您的资料已保存。点击下方菜单中的「🔮 解读」。",
    # Owner console — user management
    "owner.manage.kb.users": "👥 用户",
    "owner.users.header": "{display_name} 的用户：",
    "owner.users.empty": "暂无用户。",
    "owner.users.row": "{name} · {credits}💎",
    "owner.users.unnamed": "用户 #{id}",
    "owner.users.nav.prev": "◀️",
    "owner.users.nav.next": "▶️",
    "owner.user.card": (
        "👤 {name}\nTelegram ID: {tg_id}\n余额: {credits}💎\n"
        "订阅: {subscription}\n状态: {status}"
    ),
    "owner.user.card.banned": "🚫 已封禁。原因：{reason}",
    "owner.user.status.active": "正常",
    "owner.user.status.banned": "已封禁",
    "owner.user.not_found": "未找到该用户。",
    "owner.user.kb.grant": "💎 调整余额",
    "owner.user.kb.ban": "🚫 封禁",
    "owner.user.kb.unban": "✅ 解封",
    "owner.user.kb.back": "⬅️ 返回列表",
    "owner.user.grant.prompt": "请输入要调整的余额数值（可为负数，例如 -3）：",
    "owner.user.grant.invalid": "输入无效。请输入整数，例如 5 或 -2。",
    "owner.user.grant.done": "操作成功。新余额：{credits}💎。",
    "owner.user.ban.prompt": "请输入封禁原因：",
    "owner.user.ban.invalid": "原因不能为空。请输入原因：",
    "owner.user.ban.done": "用户已封禁。",
    "owner.user.ban.staff_blocked": "无法封禁所有者或管理员。",
    "owner.user.unban.done": "用户已解封。",
    "owner.user.cancelled": "已取消。",
    "account.banned.notice": "🚫 您的机器人访问权限已被限制。原因：{reason}",
    # -------------------------------------------------------------------------
    # Readings submenu
    # -------------------------------------------------------------------------
    "btn.readings": "📖 解读",
    "readings.menu.title": "想要哪种解读？",
    "readings.queued": "正在生成你的解读，需要一分钟。",
    "readings.no_profile": "请先填写出生信息。",
    "readings.no_quota": "没有可用积分。购买套餐以继续。",
    "readings.kind.bazi": "🐉 BaZi（八字）",
    "readings.kind.numerology": "🔢 数字学",
    "readings.kind.human_design": "🧬 Human Design（人类图）",
    "readings.kind.astrology": "☉ 星座",
    "readings.kind.vedic": "🕉 吠陀",
    "readings.kind.gene_keys": "🗝 Gene Keys",
    "readings.kind.mayan": "🌀 玛雅",
    "readings.kind.aspects": "✦ 相位",
    # -------------------------------------------------------------------------
    # History — recent readings section
    # -------------------------------------------------------------------------
    "history.readings_title": "📖 最近解读",
    "history.reading_row": "{kind} · {status} · {date}",
    "history.download": "⬇️ 下载",
    # -------------------------------------------------------------------------
    # Content moderation
    # -------------------------------------------------------------------------
    "moderation.self_harm": "如果你正处在艰难时刻，请寻求支持：{helpline_url}。我不能替代专业人士，但我会在这里。",
    "moderation.violence": "这个问题超出了我能帮助的范围。",
    "moderation.hate": "我不是为这个而在这里的。",
    "moderation.medical": "这是医生的问题，不是占星的问题。我不提供临床建议。",
    "moderation.legal": "这是律师的问题。我谈能量与周期，不谈法律风险。",
    "moderation.blocked_generic": "无法处理此请求。",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
    "feature.disabled_generic": "此功能在此机器人上不可用。",
    "owner.features.title": "⚙️ 功能",
    "owner.features.btn": "⚙️ 功能",
    "owner.features.section.readings": "— 解读 —",
    "owner.features.label.qa": "问答",
    "owner.features.label.blueprint": "解读",
    "owner.features.label.transits": "过境",
    "owner.features.label.daily": "每日",
    # White-label branding (SP3)
    "brand.signature": "",
    "owner.branding.btn": "🎨 品牌",
    "owner.branding.title": "🎨 品牌 (语言: {language})",
    "owner.branding.label.name": "名称",
    "owner.branding.label.welcome": "欢迎语",
    "owner.branding.label.help": "帮助",
    "owner.branding.label.signature": "签名",
    "owner.branding.prompt": (
        "为 **{label}** ({language}) 发送新文本，"
        "或 /cancel 保持当前，/reset 恢复默认。"
    ),
    "owner.branding.saved": "✅ 已更新。",
    "owner.branding.reset_done": "↩️ 已恢复默认。",
    "owner.branding.cancelled": "已取消。",
    "owner.branding.too_long": "太长：{actual} 字符（最多 {limit}）。",
    "owner.branding.bad_format": "名称必须为 1-64 字符且不含换行。",
    "owner.branding.empty_value": "不允许空值。使用 /reset 清除。",
    "owner.branding.preview_empty": "(空)",
    # -------------------------------------------------------------------------
    # Referral links (SP4)
    # -------------------------------------------------------------------------
    "btn.invite": "🎁 邀请朋友",
    "invite.title": "邀请朋友加入此机器人。",
    "invite.link_label": "您的链接",
    "invite.earned": "已赚取：来自 {friends} 位朋友的 {credits} 积分。",
    "invite.share_text": "试试这个机器人",
    "invite.disabled": "此机器人中推荐计划已禁用。",
    "invite.unknown_code": "推荐链接无法识别，将继续但不提供奖励。",
    "owner.referrals.title": "推荐计划",
    "owner.referrals.current_value": "当前奖励：{value} 积分。",
    "owner.referrals.prompt": "发送 0 到 {max} 之间的整数以更改奖励。",
    "owner.referrals.saved": "已保存：{value} 积分。",
    "owner.referrals.reset": "已重置为默认值（{value}）。",
    "owner.referrals.too_large": "值必须在 0-{max} 范围内。",
    "owner.referrals.not_a_number": "请发送一个整数。",
    "owner.referrals.cancel_hint": "发送 /cancel 以取消。",
    "owner.referrals.menu_button": "推荐",
    # -------------------------------------------------------------------------
    # Gift-a-friend (SP5)
    # -------------------------------------------------------------------------
    "btn.gift": "🎁 礼物",
    "gift.title": "送给朋友",
    "gift.balance_line": "可用：{balance}",
    "gift.amount_prompt": "输入礼物金额（1–{max}）：",
    "gift.cancelled": "已取消。",
    "gift.cancel_hint": "发送 /cancel 取消。",
    "gift.too_small": "最少 1 个积分。",
    "gift.too_large": "最多 {max} 个积分。",
    "gift.not_a_number": "这不是数字。请输入整数。",
    "gift.no_balance": "您没有可赠送的积分。",
    "gift.created": "{amount} 积分的礼物已就绪！\n\n链接：{link}",
    "gift.share_text": "送你一份礼物！打开机器人领取积分。",
    "gift.disabled": "礼物当前不可用。",
    "gift.received": "您收到了礼物：{amount} 积分！",
    "gift.self_blocked": "您不能领取自己的礼物。",
    "gift.history_title": "您的礼物",
    "gift.history_empty": "暂无。",
    "gift.history_row": "{date} — {amount} 积分 — {status}",
    "gift.status.active": "待领取",
    "gift.status.claimed": "已领取",
    "gift.status.refunded": "已退还",
    "gift.btn.create_new": "新建",
    "owner.gifts.menu_button": "礼物",
    "owner.gifts.title": "礼物",
    "owner.gifts.current_value": "礼物有效期：{value} 天。",
    "owner.gifts.prompt": "输入礼物有效期天数（{min}–{max}）：",
    "owner.gifts.saved": "已保存。",
    "owner.gifts.reset": "已重置为默认值。",
    "owner.gifts.too_small": "最少 {min} 天。",
    "owner.gifts.too_large": "最多 {max} 天。",
    "owner.gifts.not_a_number": "请输入整数。",
    "owner.gifts.cancel_hint": "发送 /cancel 取消。",
    # SP6 — Divination (Tarot + I-Ching)
    "readings.kind.tarot": "🔮 塔罗",
    "readings.kind.iching": "☯ 易经",
    "divination.question_prompt": "请提出你的问题或发送 /skip：",
    "divination.skip_btn": "跳过",
    "divination.no_question": "（无问题）",
    "tarot.position.past": "过去",
    "tarot.position.present": "现在",
    "tarot.position.future": "未来",
    "tarot.orientation.upright": "正位",
    "tarot.orientation.reversed": "逆位",
    "iching.judgment_label": "判词",
    "iching.image_label": "象",
    "iching.changing_line_label": "变爻 {n}",
    "iching.transformed_label": "变为",
}
