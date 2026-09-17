# Weekly Usage Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** إنشاء عدادات تفاعل مجهولة، لوحة إحصاءات إدارية، ورسالة Telegram أسبوعية لمستلم مرتبط بأمان.

**Architecture:** يسجل البوت أحداث allowlist في عدادات يومية مجمعة داخل Supabase بواسطة RPC ذرية لا تستقبل معرف مستخدم. تجمع طبقة Python الفترات وتصوغ التقرير. تربط لوحة Flask مستلم Telegram برمز لمرة واحدة. تُرسل الرسالة يوم الأحد عبر مسار النشر اليومي الحالي ومهمة APScheduler، مع claim أسبوعي يمنع التكرار.

**Tech Stack:** Python 3.10+, python-telegram-bot 22.8, Flask 3.1, Supabase/PostgreSQL, Bootstrap RTL, pytest.

**Spec:** `docs/usage_analytics_spec.md`

## Global Constraints

- لا PHI، ولا معرف مستخدم داخل أحداث التحليلات.
- لا نصوص رسائل أو كلمات بحث أو إجابات فردية.
- `anon` و`authenticated` و`PUBLIC` مرفوضون افتراضيًا.
- عدادات event types وtopic IDs محكومة بقائمة ثابتة.
- فشل القياس لا يمنع وظيفة التعلم، لكن فشل الربط أو التفويض يرفض مغلقًا.
- الاختبارات تستخدم بيانات اصطناعية فقط.

---

### Task 1: Supabase analytics schema and repository

**Files:** Modify `schema.sql`, `database.py`; Test `tests/test_database.py`, `tests/test_security_and_content.py`.

**Interfaces:** Produces `record_usage_event`, `get_usage_report`, `create_report_link_token`, `consume_report_link_token`, `get_report_delivery_config`, `claim_weekly_report`, `complete_weekly_report`, `release_weekly_report`, and `prune_usage_data`.

- [ ] أضف اختبارات عميل وهمي للـallowlist والتجميع والربط والـclaim.
- [ ] أضف الجداول والقيود والفهارس وRLS والمنح ودالة الزيادة الذرية.
- [ ] نفّذ طبقة البيانات مع أخطاء عامة وعدم طباعة payload.
- [ ] شغّل اختبارات قاعدة البيانات والأمان.

### Task 2: Bot event instrumentation and secure linking

**Files:** Modify `bot.py`; Test `tests/test_bot.py`.

**Interfaces:** Consumes repository methods; produces `/link_report`, `build_weekly_report_message`, and `send_weekly_usage_report`.

- [ ] أضف دالة قياس آمنة تلتقط event type وtopic id فقط.
- [ ] غطِّ الأوامر والمشاهدات والبحث والاختبارات دون معرف مستخدم.
- [ ] أضف معالج الربط الخاص ورفض المجموعات والرموز غير الصالحة.
- [ ] أضف صياغة التقرير والـclaim/release والإرسال الأسبوعي.
- [ ] شغّل اختبارات التنسيق والربط والفشل.

### Task 3: Admin analytics dashboard

**Files:** Modify `web.py`, `templates/base.html`, `templates/dashboard.html`, `static/css/app.css`; Create `templates/analytics.html`; Test `tests/test_web.py`.

**Interfaces:** Produces protected `GET /analytics`, `POST /analytics/link-token`, and `POST /analytics/send-test`.

- [ ] اختبر رفض المستخدم المجهول وCSRF.
- [ ] اعرض KPI للفترتين والاتجاه اليومي وأفضل الموضوعات بلا JavaScript خارجي.
- [ ] أضف زر إنشاء رمز الربط مع إظهار الرمز مرة واحدة فقط في flash/session قصيرة.
- [ ] أضف إرسال تقرير اختباري مع فشل مغلق إن لم يوجد مستلم.
- [ ] اختبر الاستجابة على iPad وصفحة empty state.

### Task 4: Weekly scheduling and production release

**Files:** Modify `bot.py`, `web.py`, `README.md`, `CHANGELOG.md`; Create `ANALYTICS_SECURITY_TEST_REPORT.md`.

- [ ] استدعِ الإرسال الأسبوعي يوم الأحد في المهمة اليومية ومسار scheduler الحالي.
- [ ] طبّق مخطط SQL في Supabase وتحقق من المنح وRLS.
- [ ] شغّل pytest وruff وcompileall وpip-audit وفحص الأسرار.
- [ ] ارفع GitHub وراقب Render حتى Live.
- [ ] أنشئ رمز ربط من اللوحة، اربط حساب المشرف داخل Telegram، وأرسل تقريرًا اختباريًا.
- [ ] تحقق من أن التقرير يعرض بداية جمع البيانات بوضوح ولا يدعي بيانات تاريخية غير موجودة.
