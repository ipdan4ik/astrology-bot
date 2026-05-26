"""Turkish (tr) UI translations. Keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": "🔮 Yorum",
    "btn.profile": "👤 Profil",
    "btn.history": "📜 Geçmiş",
    "btn.help": "ℹ️ Yardım",
    "btn.ask": "❓ Astrologa sor",
    "btn.transits": "🌌 Transitler",
    "btn.daily": "🔔 Günlük yorum",
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
        "Natal verilerinizden kişisel astrolojik yorum (Quantuum Blueprint) oluşturuyorum.\n\n"
        "Alt menü:\n"
        "🔮 Yorum — yorum oluştur\n"
        "👤 Profil — natal verileri görüntüle ve düzenle\n"
        "📜 Geçmiş — önceki yorumlar\n\n"
        "Komutlar: /start /profile /blueprint\n"
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
    "daily.kb.turn_off": "🔕 Devre dışı bırak",
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": "Henüz yorum yok. İlk yorumu oluşturmak için «🔮 Yorum» düğmesine dokunun.",
    "history.title": "📜 Yorum geçmişi:",
    "history.label": "🔮 {date} · {status}",
    "history.detail_header": "🔮 Yorum #{id}",
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
    "onb.done": "Hazır! Profiliniz kaydedildi. /blueprint komutu yorumunuzu oluşturacak.",
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
}
