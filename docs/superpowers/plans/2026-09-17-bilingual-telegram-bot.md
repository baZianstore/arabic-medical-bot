# Bilingual Telegram Bot Implementation Plan

> **For agentic workers:** Implement this plan task-by-task with tests before production deployment.

**Goal:** تقديم محتوى طبي إنجليزي مع شرح عربي وصور ومراجع واختبار تفاعلي داخل البوت الحالي.

**Architecture:** تحفظ البطاقات الثنائية المراجعة في وحدة Python مستقلة، ويربطها `bot.py` بالأمراض القادمة من Supabase عبر الاسم الإنجليزي. يبقى CRUD والجدول الحاليان بلا تغيير، ويُستخدم fallback عربي لأي مرض غير معروف. تُخدم الصور من مجلد Flask الثابت على Render.

**Tech Stack:** Python 3.10+, python-telegram-bot 22.8, Flask, Supabase, pytest.

**Spec:** `docs/bilingual_bot_spec.md`

## Global Constraints

- لا PHI أو تحليل حالات مرضى.
- لا أسرار أو توكنات في Git.
- المحتوى أصلي ومراجع بمصادر رسمية.
- كل رسائل Telegram ضمن الحدود وبـHTML آمن.
- لا تغيير مخطط Supabase في هذه المرحلة.

---

### Task 1: Bilingual content module

**Files:** Create `bilingual_content.py`; Test `tests/test_bilingual_content.py`.

- [ ] بناء خمسة سجلات ثابتة typed، لكل منها ملخصان، نقاط، تشخيص، تدبير، إنذارات، سؤال، صورة، ومراجع.
- [ ] إضافة lookup آمن بالعربية والإنجليزية وتحقق بنيوي عند الاستيراد.
- [ ] اختبار وجود اللغتين وأربع إجابات ومراجع HTTPS وعدم تجاوز الميزانيات.

### Task 2: Telegram interaction

**Files:** Modify `bot.py`; Modify `tests/test_bot.py`.

- [ ] إضافة قائمة inline وأوامر `/menu`, `/learn`, `/quiz_en`, `/sources`.
- [ ] تحديث `/today` ونتيجة البحث المفردة والنشر اليومي لاستخدام البطاقة الثنائية عند توفرها.
- [ ] إضافة callback منفصل للاختبار الإنجليزي مع رفض المدخل غير الصالح.
- [ ] اختبار تنسيق HTML وحدود الرسائل والأزرار والـfallback.

### Task 3: Original medical images

**Files:** Create `static/medical_topics/*.jpg`; Modify `bilingual_content.py`.

- [ ] توليد خمس صور طبية مفاهيمية بلا نص أو بيانات أشخاص.
- [ ] ربط كل بطاقة بعنوان HTTPS ثابت على Render.
- [ ] إبقاء إرسال النص ناجحًا عند تعذر الصورة.

### Task 4: Release and production verification

**Files:** Modify `README.md`, `CHANGELOG.md`; Create `BILINGUAL_BOT_TEST_REPORT.md`.

- [ ] تشغيل pytest وruff وcompileall وsecret scan.
- [ ] commit وpush إلى `baZianstore/arabic-medical-bot`.
- [ ] مراقبة Render حتى Live.
- [ ] اختبار أوامر Telegram الإنتاجية والتحقق من غياب الأخطاء في السجلات.
