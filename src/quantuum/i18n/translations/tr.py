"""Turkish (tr) UI translations. Keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": "🔮 Blueprint",
    "btn.profile": "👤 Profil",
    "btn.history": "📜 Geçmiş",
    "btn.help": "ℹ️ Yardım",
    "btn.ask": "❓ Astrologa sor",
    "btn.transits": "🌌 Transitler",
    "btn.daily": "🔔 Günlük yorum",
    "btn.buy": "💳 Satın al",
    "btn.language": "🌐 Dil",
    # -------------------------------------------------------------------------
    # Blueprint status words
    # -------------------------------------------------------------------------
    "status.pending": "kuyrukta",
    "status.calculating": "hesaplanıyor",
    "status.generating": "oluşturuluyor",
    "status.done": "hazır",
    "status.failed": "hata",
    "status.refunded": "iade edildi",
    # -------------------------------------------------------------------------
    # Help text
    # -------------------------------------------------------------------------
    "help.text": (
        "Doğum verilerinden kişisel astrolojik yorumlar oluşturuyorum.\n\n"
        "Menü:\n"
        "❓ Astrologa sor — doğum haritanla birlikte soru sor\n"
        "📖 Yorumlar — Blueprint, Transitler, BaZi, Human Design, Tarot ve daha fazlası\n"
        "🔔 Günlük burç yorumu — her gün otomatik teslim\n"
        "👤 Profil — doğum tarihi, saati ve yeri\n"
        "📜 Geçmiş — tüm önceki yorumlar\n"
        "💳 Satın al — paketler ve abonelikler\n"
        "🌐 Dil — arayüz dilini değiştir\n"
        "🎁 Arkadaşını davet et — referans linki\n"
        "🎁 Hediye — arkadaşına kredi hediye et\n\n"
        "Destek: @quantuum_support"
    ),
    # -------------------------------------------------------------------------
    # Profile display
    # -------------------------------------------------------------------------
    "profile.title": "👤 Profiliniz:",
    "profile.name": "Ad: {name}",
    "profile.birth_date": "Doğum tarihi: {birth_date}",
    "profile.birth_time": "Saat: {birth_time}",
    "profile.place": "Yer: {place}",
    # -------------------------------------------------------------------------
    # Profile screen messages
    # -------------------------------------------------------------------------
    "profile.empty": "Profil doldurulmamış.",
    "profile.not_found": "Profil bulunamadı.",
    "profile.place.confirm": "Bulundu: {place}\n\nDoğru mu?",
    "profile.place.not_found": "Bu yer bulunamadı. Şehri / adresi belirtin ya da konum gönderin:",
    # -------------------------------------------------------------------------
    # Profile keyboard labels
    # -------------------------------------------------------------------------
    "profile.kb.fill": "📝 Profili doldur",
    "profile.kb.edit_name": "✏️ Ad",
    "profile.kb.edit_birth_date": "✏️ Tarih",
    "profile.kb.edit_birth_time": "✏️ Saat",
    "profile.kb.edit_birth_place": "✏️ Yer",
    "profile.kb.place_confirm": "✅ Evet",
    "profile.kb.place_retry": "✏️ Farklı adres",
    # -------------------------------------------------------------------------
    # Profile field prompts (edit flow)
    # -------------------------------------------------------------------------
    "profile.prompt.name": "Adınızı girin:",
    "profile.prompt.birth_date": "Doğum tarihi YYYY-AA-GG (örn. 1980-06-24):",
    "profile.prompt.birth_time": "Doğum saati SS:DD (örn. 10:00):",
    "profile.prompt.birth_place": "Konumunuzu gönderin (📎 → Konum) veya şehir / adres yazın:",
    # -------------------------------------------------------------------------
    # Profile field validation errors
    # -------------------------------------------------------------------------
    "profile.error.name_empty": "Ad boş olamaz.",
    "profile.error.birth_date_invalid": "Tarih anlaşılamadı. Biçim: YYYY-AA-GG.",
    "profile.error.birth_time_invalid": "Saat anlaşılamadı. Biçim: SS:DD.",
    "profile.error.unknown_field": "Bilinmeyen alan.",
    "profile.field_edit_error": "{err}\nLütfen tekrar deneyin:",
    # -------------------------------------------------------------------------
    # Start / welcome
    # -------------------------------------------------------------------------
    "start.welcome": "Merhaba! Astrolojik yorumunuzu oluşturacağım ✨",
    # -------------------------------------------------------------------------
    # Main menu
    # -------------------------------------------------------------------------
    "menu.title": "Ana menü:",
    "menu.cancelled": "İptal edildi.",
    # -------------------------------------------------------------------------
    # Generate (blueprint request)
    # -------------------------------------------------------------------------
    "generate.no_profile": "Lütfen önce profilinizi doldurun:",
    "generate.no_quota": "Ücretsiz yorumunuz kullanıldı. Paket veya abonelik satın alın:",
    "generate.queued": "Yorumunuz oluşturuluyor, yaklaşık bir dakika sürecek…",
    # -------------------------------------------------------------------------
    # Q&A astrologer
    # -------------------------------------------------------------------------
    "qa.ask_prompt": "Astrologa sorunuzu yazın:",
    "qa.thinking": "Cevap hazırlanıyor… ⏳",
    "qa.no_profile": "Önce natal profilinizi doldurun (/profile).",
    "qa.no_quota": "Krediniz tükendi. Astrologa soru sormak için paket veya abonelik satın alın:",
    "qa.too_long": "Soru çok uzun (maks. 1000 karakter).",
    "qa.empty": "Soru boş. Lütfen sorunuzu yazın:",
    # -------------------------------------------------------------------------
    # Transits
    # -------------------------------------------------------------------------
    "transit.thinking": "Transitler hesaplanıyor… ⏳",
    "transit.no_profile": "Önce natal profilinizi doldurun (/profile).",
    "transit.no_quota": "Krediniz tükendi. Transitleri görmek için paket veya abonelik satın alın:",
    "transit.failed": "Transitler hesaplanamadı. Daha sonra tekrar deneyin.",
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": "🌟 Bugünün burç yorumu",
    "daily.status_on": "Günlük burç AÇIK. Gönderim saati: {hour}:00 (saat diliminize göre).",
    "daily.status_off": "Günlük burç KAPALI.",
    "daily.not_subscriber": "Günlük burç abonelik özelliğidir. Her sabah almak için abone olun:",
    "daily.no_profile": "Önce natal profilinizi doldurun (/profile).",
    "daily.enabled": "Günlük burç etkinleştirildi ✅",
    "daily.disabled": "Günlük burç devre dışı bırakıldı.",
    "daily.hour_set": "Gönderim saati: {hour}:00 ✅",
    "daily.kb.turn_on": "🔔 Etkinleştir",
    "daily.kb.close": "✅ Tamam",
    "daily.kb.turn_off": "🔕 Devre dışı bırak",
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": "Henüz yorum yok. İlk yorumu oluşturmak için «🔮 Blueprint» düğmesine dokunun.",
    "history.title": "📜 Yorum geçmişi:",
    "history.label": "🔮 {date} · {status}",
    "history.detail_header": "🔮 Blueprint #{id}",
    "history.detail_status": "Durum: {status}",
    "history.detail_created": "Oluşturuldu: {created_at}",
    "history.detail_ready": "Hazır: {completed_at}",
    "history.not_found": "Bulunamadı",
    # -------------------------------------------------------------------------
    # History / blueprint detail keyboard labels
    # -------------------------------------------------------------------------
    "history.kb.download": "📥 .md indir",
    "history.kb.preview": "👁 Önizleme",
    "history.kb.back": "← Geri",
    "history.kb.prev_page": "← Önceki",
    "history.kb.next_page": "Sonraki →",
    "history.unavailable": "Kullanılamıyor",
    # -------------------------------------------------------------------------
    # Buy / payments
    # -------------------------------------------------------------------------
    "buy.menu_title": "Ne satın almak istediğinizi seçin (ödeme: Telegram Yıldızları ★):",
    "buy.no_plans": "Henüz mevcut plan yok. Daha sonra tekrar bakın.",
    "buy.plan_subscription": "⭐ {name} — {price}★",
    "buy.plan_package": "⭐ {name} · {count} yorum — {price}★",
    "buy.invoice_subscription": "{period_days} günlük abonelik",
    "buy.invoice_package": "Paket: {count} yorum",
    "buy.plan_unavailable": "Bu plan artık mevcut değil.",
    "buy.payment_success": "Ödeme alındı! Erişim etkinleştirildi. ✨",
    "buy.payment_already_credited": "Bu ödeme daha önce zaten kaydedildi.",
    "buy.kb.open": "💳 Yorum satın al",
    # -------------------------------------------------------------------------
    # Shared / generic
    # -------------------------------------------------------------------------
    "kb.cancel": "✖️ İptal",
    "errors.queue_failed": "İsteğin kuyruğa alınamadı. Kredin iade edildi — lütfen birazdan tekrar dene.",
    # -------------------------------------------------------------------------
    # Master bot — owner onboarding
    # -------------------------------------------------------------------------
    "master.onboard.invite_invalid": "Davet geçersiz veya süresi dolmuş.",
    "master.onboard.slug_prompt": "Hoş geldiniz! Bir bot oluşturalım. Kiracı slug'ını girin (latin harfler, boşluk yok){prefill}:",
    "master.onboard.slug_prefill": " (öneri: {slug})",
    "master.onboard.plain_start": "Bu, platform onboarding botudur. Kendi botunuzu oluşturmak için davet bağlantısını açın.",
    "master.onboard.slug_invalid": "Slug boş olamaz ve boşluk içeremez. Lütfen tekrar deneyin:",
    "master.onboard.slug_taken": "Bu slug zaten alınmış. Başka bir tane girin:",
    "master.onboard.display_name_prompt": "Ürün görünen adı (örn. «Acme Astro»):",
    "master.onboard.display_name_empty": "Ad boş olamaz. Tekrar girin:",
    "master.onboard.lang_prompt": "Varsayılan dil (iki harfli kod, örn. ru veya en):",
    "master.onboard.lang_invalid": "İki harfli dil kodu gerekli, örn. ru. Tekrar girin:",
    "master.onboard.confirm": (
        "Bilgileri kontrol edin:\nslug: {slug}\nad: {display_name}\ndil: {language}\n\n"
        "Botu oluşturalım mı?"
    ),
    "master.onboard.invite_gone": "Davet artık geçerli değil.",
    "master.onboard.creating": "Kiracı oluşturuluyor… Botun otomatik oluşturulabilirliği kontrol ediliyor.",
    "master.onboard.cancelled": "Onboarding iptal edildi.",
    "master.onboard.token_invalid": "Bu geçerli bir bot tokeni gibi görünmüyor. @BotFather'dan tokeninizi tekrar gönderin:",
    "master.onboard.token_in_use": "Bu bot zaten başka bir projeye bağlı. Farklı bir bot kullan.",
    "master.onboard.done": "Hazır! @{username} botu etkinleştirildi. Worker yeniden başlatıldıktan sonra kullanılabilir olacak.",
    "master.kb.cancel": "İptal",
    "master.kb.create_bot": "Bot oluştur",
    # -------------------------------------------------------------------------
    # Master bot — owner console
    # -------------------------------------------------------------------------
    "owner.tenants.empty": "Henüz kiracınız yok. Davet bağlantısıyla bir bot oluşturun.",
    "owner.tenants.header": "Kiracılarınız:",
    "owner.tenants.line": "• {display_name} (/{slug}) — {status}",
    "owner.tenants.hint": "\nYönetim: /manage <slug>",
    "owner.manage.usage": "Kullanım: /manage <slug>",
    "owner.manage.not_found": "Kiracı bulunamadı veya yetkiniz yok.",
    "owner.manage.title": "Yönetim: {display_name} (/{slug}) — {status}",
    "owner.manage.kb.stats": "📊 İstatistikler",
    "owner.manage.kb.pause": "⏸ Duraklat",
    "owner.manage.kb.resume": "▶️ Devam et",
    "owner.manage.kb.transfer": "🔁 Sahipliği devret",
    "owner.stats.text": (
        "📊 İstatistikler (son {period_days} gün)\n"
        "Aktif: {active_customers}, ödeme yapan: {paid_customers}\n"
        "DAU/WAU/MAU: {dau}/{wau}/{mau}\n"
        "Gelir: {revenue_cents}, MRR: {mrr_cents}\n"
        "İstekler: {requests_by_kind}"
    ),
    "owner.no_rights": "Yetki yok",
    "owner.pause.platform_blocked": "Platform kiracısı duraklatılamaz",
    "owner.pause.done": "⏸ Duraklatıldı.",
    "owner.resume.done": "▶️ Devam ettirildi.",
    "owner.manage.kb.delete": "🗑 Sil",
    "owner.delete.prompt": (
        "⚠️ Bu işlem botu kalıcı olarak siler ve kiracıyı gizler. "
        "Onaylamak için slug'ı gönderin: {slug}\n(veya /cancel)"
    ),
    "owner.delete.mismatch": "Slug eşleşmiyor. {slug} ifadesini tekrar gönderin veya /cancel.",
    "owner.delete.done": "🗑 Bot silindi.",
    "owner.delete.cancelled": "İptal edildi.",
    "owner.delete.platform_blocked": "Platform kiracısı silinemez",
    # -------------------------------------------------------------------------
    # Superadmin cabinet
    # -------------------------------------------------------------------------
    "admin.denied": "Yetkiniz yok.",
    "admin.menu.title": "🛠 Süper yönetici paneli",
    "admin.menu.kb.tenants": "🏢 Botlar",
    "admin.menu.kb.invites": "🎟 Davetler",
    "admin.tenants.title": "Tüm botlar:",
    "admin.tenants.empty": "Henüz bot yok.",
    "admin.tenant.title": "Bot: {display_name} (/{slug}) — {status}",
    "admin.tenant.kb.stats": "📊 İstatistikler",
    "admin.tenant.kb.suspend": "⏸ Askıya al",
    "admin.tenant.kb.resume": "▶️ Devam et",
    "admin.tenant.kb.delete": "🗑 Sil",
    "admin.kb.back": "⬅️ Geri",
    "admin.tenant.suspended": "⏸ Bot askıya alındı.",
    "admin.tenant.resumed": "▶️ Bot devam ettirildi.",
    "admin.invites.title": "Aktif davetler:",
    "admin.invites.empty": "Aktif davet yok.",
    "admin.invites.kb.new": "➕ Yeni davet",
    "admin.invite.kb.revoke": "🗑 İptal et",
    "admin.invite.created": "Davet oluşturuldu:\n{link}",
    "admin.invite.revoked": "Davet iptal edildi.",
    "admin.stale": "Bulunamadı — liste yenilendi.",
    # -------------------------------------------------------------------------
    # Transfer
    # -------------------------------------------------------------------------
    "owner.transfer.usage": "Kullanım: /transfer <slug>",
    "owner.transfer.not_owner": "Kiracı bulunamadı veya sahip değilsiniz.",
    "owner.transfer.prompt": (
        "Yeni sahibin Telegram ID'sini (sayı) iletin. "
        "Kişinin bu kiracıda zaten bir hesabı olmalıdır (botunuzu başlatmış olmalı)."
    ),
    "owner.transfer.cancelled": "İptal edildi.",
    "owner.transfer.target_invalid": "Sayısal bir Telegram ID gerekli. Tekrar deneyin veya /cancel.",
    "owner.transfer.no_rights_anymore": "Artık devretme yetkiniz yok.",
    "owner.transfer.no_account": (
        "Bu kullanıcının kiracıda hesabı yok. "
        "Önce botunuzu başlatması gerekiyor."
    ),
    "owner.transfer.done": "✅ Hazır. Sahiplik devredildi.",
    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    "lang.prompt": "Dil seçin:",
    "lang.changed": "Dil güncellendi.",
    # -------------------------------------------------------------------------
    # Onboarding flow
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": "Tam adınızı girin (doğum belgesindeki gibi):",
    "onb.error.full_name": "Ad anlaşılamadı. Tam adınızı metin olarak girin:",
    "onb.prompt.birth_date": "Doğum tarihi YYYY-AA-GG biçiminde (örn. 1980-06-24):",
    "onb.error.birth_date": "Tarih anlaşılamadı. Biçim YYYY-AA-GG:",
    "onb.prompt.birth_time": "Doğum saati SS:DD biçiminde (örn. 10:00):",
    "onb.error.birth_time": "Saat anlaşılamadı. Biçim SS:DD:",
    "onb.prompt.birth_place": (
        "Doğum yeri: konumunuzu gönderin (📎 → Konum, haritada pin bırakabilirsiniz) "
        "veya şehir / adresin bir bölümünü yazın:"
    ),
    "onb.done": "Tamam! Profilin kaydedildi. Aşağıdaki menüde «🔮 Blueprint» düğmesine dokun.",
    # Owner console — user management
    "owner.manage.kb.users": "👥 Kullanıcılar",
    "owner.users.header": "{display_name} kullanıcıları:",
    "owner.users.empty": "Henüz kullanıcı yok.",
    "owner.users.row": "{name} · {credits}💎",
    "owner.users.unnamed": "kullanıcı #{id}",
    "owner.users.nav.prev": "◀️",
    "owner.users.nav.next": "▶️",
    "owner.user.card": (
        "👤 {name}\nTelegram ID: {tg_id}\nKredi: {credits}💎\n"
        "Abonelik: {subscription}\nDurum: {status}"
    ),
    "owner.user.card.banned": "🚫 Yasaklandı. Neden: {reason}",
    "owner.user.status.active": "aktif",
    "owner.user.status.banned": "yasaklı",
    "owner.user.not_found": "Kullanıcı bulunamadı.",
    "owner.user.kb.grant": "💎 Kredi ayarla",
    "owner.user.kb.ban": "🚫 Yasakla",
    "owner.user.kb.unban": "✅ Yasağı kaldır",
    "owner.user.kb.back": "⬅️ Listeye dön",
    "owner.user.grant.prompt": "Kredi sayısını girin (negatif olabilir, örn. -3):",
    "owner.user.grant.invalid": "Anlaşılamadı. Tam sayı girin, örn. 5 veya -2.",
    "owner.user.grant.done": "Tamam. Yeni bakiye: {credits}💎.",
    "owner.user.ban.prompt": "Yasak gerekçesini girin:",
    "owner.user.ban.invalid": "Gerekçe boş olamaz. Bir gerekçe girin:",
    "owner.user.ban.done": "Kullanıcı yasaklandı.",
    "owner.user.ban.staff_blocked": "Bir sahibi veya yöneticiyi yasaklayamazsınız.",
    "owner.user.unban.done": "Kullanıcının yasağı kaldırıldı.",
    "owner.user.cancelled": "İptal edildi.",
    "account.banned.notice": "🚫 Bota erişiminiz kısıtlandı. Neden: {reason}",
    # -------------------------------------------------------------------------
    # Readings submenu
    # -------------------------------------------------------------------------
    "btn.readings": "📖 Okumalar",
    "readings.menu.title": "Hangi okumayı istersin?",
    "readings.queued": "Okumanı hazırlıyorum. Bir dakika sürecek.",
    "readings.no_profile": "Önce doğum profilini doldur.",
    "readings.no_quota": "Kredin kalmadı. Devam etmek için paket al.",
    "readings.kind.bazi": "🐉 BaZi",
    "readings.kind.numerology": "🔢 Numeroloji",
    "readings.kind.human_design": "🧬 Human Design",
    "readings.kind.astrology": "☉ Astroloji",
    "readings.kind.vedic": "🕉 Vedik",
    "readings.kind.gene_keys": "🗝 Gene Keys",
    "readings.kind.mayan": "🌀 Maya",
    "readings.kind.aspects": "✦ Açılar",
    # -------------------------------------------------------------------------
    # History — recent readings section
    # -------------------------------------------------------------------------
    "history.readings_title": "📖 Son okumalar",
    "history.reading_row": "{kind} · {status} · {date}",
    "history.download": "⬇️ İndir",
    # -------------------------------------------------------------------------
    # Content moderation
    # -------------------------------------------------------------------------
    "moderation.self_harm": "Şu an zor bir noktadaysan, lütfen destek al: {helpline_url}. Uzmanın yerine geçmem ama buradayım.",
    "moderation.violence": "Bu soru, yardım edebileceklerimin dışında.",
    "moderation.hate": "Bunun için burada değilim.",
    "moderation.medical": "Bu doktorluk konusu, astroloji değil. Klinik tavsiye vermem.",
    "moderation.legal": "Bu avukatlık konusu. Enerjilerden ve döngülerden bahsederim, hukuki risklerden değil.",
    "moderation.blocked_generic": "Bu istek işleme alınamıyor.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
    "feature.disabled_generic": "Bu özellik bu bot için kullanılamıyor.",
    "owner.features.title": "⚙️ Özellikler",
    "owner.features.btn": "⚙️ Özellikler",
    "owner.features.section.readings": "— Okumalar —",
    "owner.features.label.qa": "Soru-Cevap",
    "owner.features.label.blueprint": "Okuma",
    "owner.features.label.transits": "Transitler",
    "owner.features.label.daily": "Günlük",
    # White-label branding (SP3)
    "brand.signature": "",
    "owner.branding.btn": "🎨 Markalama",
    "owner.branding.title": "🎨 Markalama (dil: {language})",
    "owner.branding.label.name": "Ad",
    "owner.branding.label.welcome": "Karşılama",
    "owner.branding.label.help": "Yardım",
    "owner.branding.label.signature": "İmza",
    "owner.branding.prompt": (
        "**{label}** ({language}) için yeni metin gönderin, "
        "veya korumak için /cancel, varsayılana döndürmek için /reset."
    ),
    "owner.branding.saved": "✅ Güncellendi.",
    "owner.branding.reset_done": "↩️ Varsayılana sıfırlandı.",
    "owner.branding.cancelled": "İptal edildi.",
    "owner.branding.too_long": "Çok uzun: {actual} karakter (maks {limit}).",
    "owner.branding.bad_format": "Ad 1-64 karakter olmalı ve satır sonu içermemeli.",
    "owner.branding.empty_value": "Boş değer izin verilmez. Temizlemek için /reset kullanın.",
    "owner.branding.preview_empty": "(boş)",
    # -------------------------------------------------------------------------
    # Referral links (SP4)
    # -------------------------------------------------------------------------
    "btn.invite": "🎁 Arkadaş davet et",
    "invite.title": "Bu bota arkadaşlarınızı davet edin.",
    "invite.link_label": "Bağlantınız",
    "invite.earned": "Kazanıldı: {friends} arkadaştan {credits} kredi.",
    "invite.share_text": "Bu botu deneyin",
    "invite.disabled": "Bu botta referans programı devre dışı.",
    "invite.unknown_code": "Referans bağlantısı tanınmadı. Bonussuz devam ediliyor.",
    "owner.referrals.title": "Referans programı",
    "owner.referrals.current_value": "Mevcut ödül: {value} kredi.",
    "owner.referrals.prompt": "Ödülü değiştirmek için 0 ile {max} arasında bir tam sayı gönderin.",
    "owner.referrals.saved": "Kaydedildi: {value} kredi.",
    "owner.referrals.reset": "Varsayılana sıfırlandı ({value}).",
    "owner.referrals.too_large": "Değer 0-{max} aralığında olmalıdır.",
    "owner.referrals.not_a_number": "Bir tam sayı gönderin.",
    "owner.referrals.cancel_hint": "İptal etmek için /cancel gönderin.",
    "owner.referrals.menu_button": "Referanslar",
    # -------------------------------------------------------------------------
    # Gift-a-friend (SP5)
    # -------------------------------------------------------------------------
    "btn.gift": "🎁 Hediye",
    "gift.title": "Bir arkadaşa hediye et",
    "gift.balance_line": "Mevcut: {balance}",
    "gift.amount_prompt": "Hediye miktarını girin (1–{max}):",
    "gift.cancelled": "İptal edildi.",
    "gift.cancel_hint": "İptal etmek için /cancel gönderin.",
    "gift.too_small": "En az 1 kredi.",
    "gift.too_large": "En fazla {max} kredi.",
    "gift.not_a_number": "Bu sayı değil. Tam sayı girin.",
    "gift.no_balance": "Hediye edecek krediniz yok.",
    "gift.created": "{amount} kredilik hediye hazır!\n\nLink: {link}",
    "gift.share_text": "Sana bir hediye! Kredilerini almak için botu aç.",
    "gift.disabled": "Hediyeler şu anda kullanılamıyor.",
    "gift.received": "Bir hediye aldın: {amount} kredi!",
    "gift.self_blocked": "Kendi hediyenizi alamazsınız.",
    "gift.history_title": "Hediyeleriniz",
    "gift.history_empty": "Henüz boş.",
    "gift.history_row": "{date} — {amount} kr. — {status}",
    "gift.status.active": "beklemede",
    "gift.status.claimed": "alındı",
    "gift.status.refunded": "iade edildi",
    "gift.btn.create_new": "Yeni oluştur",
    "owner.gifts.menu_button": "Hediyeler",
    "owner.gifts.title": "Hediyeler",
    "owner.gifts.current_value": "Hediye ömrü: {value} gün.",
    "owner.gifts.prompt": "Hediye ömrünü gün olarak girin ({min}–{max}):",
    "owner.gifts.saved": "Kaydedildi.",
    "owner.gifts.reset": "Varsayılana sıfırlandı.",
    "owner.gifts.too_small": "En az {min} gün.",
    "owner.gifts.too_large": "En fazla {max} gün.",
    "owner.gifts.not_a_number": "Tam sayı girin.",
    "owner.gifts.cancel_hint": "İptal etmek için /cancel gönderin.",
    # SP6 — Divination (Tarot + I-Ching)
    "readings.kind.tarot": "🔮 Tarot",
    "readings.kind.iching": "☯ I Ching",
    "divination.question_prompt": "Sorunu yaz veya /skip gönder:",
    "divination.skip_btn": "Atla",
    "divination.no_question": "(soru yok)",
    "tarot.position.past": "Geçmiş",
    "tarot.position.present": "Şimdi",
    "tarot.position.future": "Gelecek",
    "tarot.orientation.upright": "dik",
    "tarot.orientation.reversed": "ters",
    "iching.judgment_label": "Yargı",
    "iching.image_label": "İmge",
    "iching.changing_line_label": "Değişen çizgi {n}",
    "iching.transformed_label": "Şuna dönüşür",
}
