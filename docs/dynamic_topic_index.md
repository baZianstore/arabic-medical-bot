# مواصفة ربط فهرس الموضوعات بـ Supabase

## الهدف

توفير فهرس موضوعات طبي عام وديناميكي للموقع العام، بحيث تظهر تعديلات الأمراض التي يجريها المدير في لوحة Flask بعد مدة تخزين مؤقت قصيرة، من دون كشف مفتاح Supabase أو أي صلاحيات كتابة في المتصفح.

## المسار المعتمد

يتصل المتصفح بالمسار العام `GET /api/public/topics` على خدمة Render. يقرأ خادم Flask من Supabase باستخدام المفتاح الخادمي الموجود أصلًا في بيئة Render، ثم يعيد حقول allowlist فقط. يحتفظ المتصفح بالبيانات في ذاكرة React المؤقتة ولا يكتبها إلى Web Storage. إذا تعذر Render أو Supabase، تستمر الواجهة بعرض الفهرس الثابت المضمّن مع شارة واضحة بأنه نسخة احتياطية.

## عقد الاستجابة

| الحقل | النوع | المصدر | الحد |
|---|---|---|---|
| `id` | string | `diseases.id` | UUID أو معرّف نصي محدود |
| `title` | string | `diseases.name_ar` | 200 محرف |
| `title_en` | string | `diseases.name_en` | 200 محرف |
| `specialty` | string | `diseases.system` | 120 محرف |
| `weight` | enum | تحويل `importance` | متوسط، عالٍ، عالي جدًا |
| `status` | enum | وجود السجل المنشور | منشور |
| `order` | integer | `week_number` | 1–53 |

لا تعيد الواجهة التعريف أو الأعراض أو التشخيص أو العلاج أو الأسئلة أو بيانات المشتركين.

## RBAC ورفض الوصول

| الدور | المورد | الفعل | النطاق/الملكية | السماح | المنع الصريح | موضع الإنفاذ |
|---|---|---|---|---|---|---|
| زائر عام | فهرس الموضوعات | قراءة | حقول عامة محددة فقط | `GET /api/public/topics` | كتابة، حذف، تفاصيل مرض كاملة، أسئلة، مشتركون | Flask serializer + مسارات الإدارة المحمية |
| مدير | الأمراض | CRUD | عالمي | جلسة خادم بدور `admin` | مجهول أو جلسة بلا دور | `login_required` في Flask |
| عميل Supabase الخادمي | جدول الأمراض | قراءة/كتابة | الخدمة | مفتاح خادمي في Render فقط | المتصفح والمفتاح العام | بيئة Render + RLS/GRANT |
| anon/authenticated في Supabase | الجداول | أي فعل | — | لا شيء | رفض صريح افتراضي | RLS و`REVOKE ALL` |

## التخزين المؤقت والفشل

يحتفظ Render بنسخة ذاكرة لمدة 60 ثانية لتقليل الضغط. ترسل الاستجابة `ETag` و`Cache-Control: public, max-age=60, stale-while-revalidate=300`. عند فشل قاعدة البيانات يعاد HTTP 503 برسالة عامة و`Retry-After`. لا تسجل أجسام الاستجابة أو طلبات المستخدم. البحث والتصفية يحدثان في المتصفح فقط.

## حدود الشبكة

الأصل الجديد الوحيد هو `https://arabic-medical-bot.onrender.com` لطلبات GET العامة. لا ترسل الواجهة Cookie أو Authorization أو مفتاح Supabase. تبقى أصول الصور والفيديو في نطاق CDN المسموح الحالي.

## أوامر التحقق

```bash
pytest -q
ruff check . --exclude static/vendor
python -m compileall -q .
pnpm check
pnpm build
```

## معايير النجاح

يعيد endpoint حقول allowlist فقط وبحد أقصى 100 سجل، ويقبل طلبات GET عامة بلا جلسة، ويرفض الطرق غير المعرفة. تستبدل الواجهة fallback ببيانات Supabase الحية عند النجاح، وتعرض حالة واضحة عند الفشل، ولا تخزن أي مادة في `localStorage` أو `sessionStorage`. يجب أن تنجح اختبارات CORS وCache والأخطاء، ثم الفحص الإنتاجي على Render والموقع المنشور.

> `SECURITY-GATE: healthcare-app-security-guardrails loaded — phase=ربط Supabase الديناميكي — status=ENFORCED`
