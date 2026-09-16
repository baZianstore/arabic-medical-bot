# خريطة قدرات بوت التعليم الطبي

| معرّف الوحدة | المسؤولية | تعتمد على |
|---|---|---|
| `configuration-security` | الإعدادات، الأسرار، الجلسات، CSRF، والرؤوس الأمنية | — |
| `content-storage` | مخطط Supabase والوصول إلى الأمراض والأسئلة والمشتركين | `configuration-security` |
| `telegram-bot` | أوامر تيليغرام والاختبارات والنشر اليومي | `content-storage` |
| `admin-dashboard` | تسجيل الدخول ولوحة CRUD العربية | `content-storage` |
| `runtime-deployment` | تشغيل polling محليًا وwebhook سحابيًا وجدولة 08:00 | `telegram-bot`, `admin-dashboard` |
| `documentation-packaging` | دليل iPad والاستكشاف والحزمة النهائية | جميع الوحدات |

**ترتيب البناء:** `configuration-security` ← `content-storage` ← (`telegram-bot` و`admin-dashboard`) ← `runtime-deployment` ← `documentation-packaging`.
