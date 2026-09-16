# نموذج الأمان والخصوصية

> `SECURITY-GATE: healthcare-app-security-guardrails loaded — phase=design — status=ENFORCED`

## تصنيف البيانات ومسارها

| البيانات | التصنيف | المسار | الاحتفاظ |
|---|---|---|---|
| الأمراض والأسئلة | محتوى تعليمي عام | لوحة الإدارة ← Flask ← Supabase، ثم Supabase ← البوت ← Telegram | حتى حذف المشرف |
| Telegram `user_id` | معرّف حساب غير سريري لازم للإرسال | Telegram ← البوت ← Supabase | حتى إلغاء الاشتراك أو الحذف الإداري |
| اسم مستخدم Telegram | غير مطلوب تشغيليًا | لا يخزنه التطبيق افتراضيًا، والحقل يبقى nullable للتوافق | لا شيء افتراضيًا |
| مفاتيح الخدمات وكلمة الإدارة | سر | متغيرات بيئة الخادم فقط | حتى التدوير |
| جلسة الإدارة | بيانات مصادقة | Cookie موقّعة `HttpOnly` | 30 دقيقة |

**لا يوجد مسار لبيانات مرضى أو PHI.** البوت تعليمي ولا يجمع الأعراض أو التشخيصات أو التقارير أو الوصفات. تمنع الوثائق استخدامه لإدارة الحالات الفردية.

## مصفوفة RBAC

| الدور | المورد | الفعل | النطاق/الملكية | السماح | المنع الصريح | موضع الإنفاذ |
|---|---|---|---|---|---|---|
| زائر ويب | صفحة الدخول والصحة | قراءة/دخول | عام | GET للصحة والدخول، POST دخول صحيح | كل صفحات وعمليات الإدارة | Flask decorators |
| `admin` | الأمراض والأسئلة والإحصاءات | قراءة/إنشاء/تعديل/حذف | عالمي | جلسة خادمية موقعة بدور `admin` وCSRF صالح | مجهول، دور آخر، CSRF مفقود، UUID غير صالح | Flask routes والخدمة |
| مستخدم تيليغرام | المحتوى والاشتراك | قراءة/إنشاء ذاتي | حسابه فقط | أوامر البوت وتسجيل `user_id` الحالي | إدارة المحتوى أو التسجيل نيابة عن شخص آخر | Telegram handlers |
| مجدول النشر | عملية النشر اليومية | تنفيذ | عالمي | Bearer secret صحيح | سر مفقود أو غير صحيح | `/tasks/daily-publish` |
| Telegram | webhook | إنشاء Update | endpoint واحد | ترويسة secret مطابقة | أي طلب آخر | `/telegram/webhook` |
| `anon`/`authenticated` في Supabase | جميع الجداول | جميع الأفعال | لا شيء | لا سماح | منع كامل | Grants + RLS |
| `service_role` | الجداول | CRUD خادمي | عالمي | مفتاح سري داخل الخادم | أي عميل متصفح | Supabase grants + بيئة الخادم |

## الأصول الخارجية المسموح بها

التطبيق يتصل فقط بـTelegram Bot API وبمشروع Supabase المحدد في البيئة. Bootstrap مخزّن محليًا، ولا توجد تحليلات أو خطوط أو scripts خارجية. تُرسل إلى Telegram الرسائل التعليمية ومعرّف الدردشة اللازم للتوصيل فقط. لا توجد بيانات سريرية فردية.

## سجل البوابة

```text
SECURITY-GATE
skill: healthcare-app-security-guardrails
phase: design
classes: public educational content, non-clinical account identifier, server secrets
PHI server/third-party path: NONE
session mechanism: signed HttpOnly cookie; Web Storage: FORBIDDEN
RBAC artifact: SECURITY.md#مصفوفة-rbac
new external origins/vendors: Telegram API, configured Supabase project
status: PASS
```

هذه ضوابط هندسية وليست شهادة امتثال قانوني أو تنظيمي.
