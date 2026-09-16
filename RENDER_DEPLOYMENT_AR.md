# نشر بوت التعليم الطبي على Render

هذا الدليل يشرح نشر لوحة Flask وبوت Telegram من المستودع العام:

**https://github.com/baZianstore/arabic-medical-bot**

> **حقيقة مهمة:** خدمة Render المجانية ليست خدمة تعمل 24/7 بلا انقطاع. فهي تدخل في وضع السكون بعد 15 دقيقة من عدم استقبال حركة HTTP، وتحتاج قرابة دقيقة للاستيقاظ عند أول طلب جديد. كما قد يعيد Render تشغيلها في أي وقت. لذلك تصلح الخطة المجانية للاختبار والمشاريع التعليمية، لكنها لا تضمن استجابة فورية أو نشرًا يوميًا في الدقيقة المحددة. للحصول على تشغيل دائم بلا سكون يلزم اختيار خطة Web Service مدفوعة.[1]

## 1. إنشاء حساب Render

1. افتح [Render](https://dashboard.render.com/register) من Safari أو أي متصفح.
2. اختر التسجيل بواسطة **GitHub** لتسهيل ربط المستودع.
3. أكمل التحقق المطلوب، ثم افتح **Dashboard**.
4. إذا لم يظهر GitHub ضمن مصادر النشر، افتح **Account Settings → Account Security → Git Deployment Credentials** واضغط **Add credential** ثم وافق على وصول Render إلى المستودع.[2]

## 2. المتغيرات المطلوبة قبل النشر

لا ترفع ملف `.env` إلى GitHub. يحتوي `render.yaml` أسماء المتغيرات فقط، بينما تدخل القيم الحساسة داخل Render. المتغيرات المطلوبة هي:

| المتغير | ما يوضع فيه |
|---|---|
| `BOT_TOKEN` | الرمز الذي أصدره BotFather |
| `SUPABASE_URL` | رابط مشروع Supabase |
| `SUPABASE_SECRET_KEY` | **Secret key خادمي** يبدأ عادة بـ`sb_secret_`، وليس مفتاح `anon` العام |
| `ADMIN_USERNAME` | اسم دخول لوحة الإدارة |
| `ADMIN_PASSWORD` | كلمة قوية وفريدة لا تقل عن 12 محرفًا |

ينشئ Render تلقائيًا `FLASK_SECRET_KEY` و`WEBHOOK_SECRET` و`SCHEDULER_SECRET` وفق `render.yaml`.

**لا تستخدم `SUPABASE_ANON_KEY` في الإنتاج.** مخطط المشروع يمنع دور `anon` من قراءة الجداول أو تعديلها، وهذا مقصود أمنيًا. احصل على المفتاح الخادمي من **Supabase Dashboard → Project Settings → API Keys → Secret keys**، ولا تضعه في GitHub أو JavaScript أو تطبيق عميل.

## 3. استيراد المستودع بواسطة Blueprint

1. افتح [Render Dashboard](https://dashboard.render.com/).
2. اضغط **New → Blueprint**.
3. اربط GitHub إذا طُلب ذلك.
4. ابحث عن المستودع `baZianstore/arabic-medical-bot` واضغط **Connect**.
5. اترك **Blueprint Path** على القيمة الافتراضية `render.yaml` لأنه موجود في جذر المشروع.
6. اختر الفرع `main`.
7. راجع الخدمة المقترحة. يجب أن تكون من النوع **Web Service** والخطة **Free** والمنطقة **Frankfurt**.
8. سيطلب Render قيم المتغيرات التي تحمل `sync: false`. أدخل القيم الخمس المذكورة أعلاه.
9. اضغط **Deploy Blueprint**.

يقرأ Render من الملف هذه الإعدادات:

```yaml
buildCommand: pip install -r requirements.txt
startCommand: python main.py
healthCheckPath: /health
```

تدعم Blueprints المتغيرات السرية بصيغة `sync: false`، ولا تخزن قيمها في المستودع.[3]

## 4. متابعة أول عملية نشر

افتح الخدمة ثم صفحة **Deploys**. يبدأ Render بتثبيت الحزم ثم تشغيل `python main.py`. تكون العملية ناجحة عندما تصبح الحالة **Live** ولا يظهر خطأ إعدادات في السجل.

إذا فشل التشغيل برسالة تطلب `SUPABASE_SECRET_KEY`، فقد أدخلت مفتاح `anon` فقط. أضف المفتاح الخادمي ثم اختر **Manual Deploy → Deploy latest commit**.

إذا فشل بسبب كلمة مرور الإدارة، اجعل `ADMIN_PASSWORD` بطول 12 محرفًا على الأقل ولا تستخدم `admin123` في الإنتاج.

## 5. روابط الخدمة بعد نجاح النشر

يعطي Render كل Web Service رابطًا فريدًا ينتهي بـ`onrender.com`. ستجده أعلى صفحة الخدمة بعد أن تصبح **Live**.[2]

| الاستخدام | الرابط |
|---|---|
| لوحة الإدارة | `https://اسم-الخدمة.onrender.com/login` |
| فحص الصحة | `https://اسم-الخدمة.onrender.com/health` |
| Telegram webhook | `https://اسم-الخدمة.onrender.com/telegram/webhook` |

لا تفتح رابط webhook يدويًا؛ هو يستقبل طلبات Telegram الموقعة فقط. يقرأ التطبيق `RENDER_EXTERNAL_HOSTNAME` تلقائيًا ويسجل webhook مع Telegram عند بدء التشغيل.

## 6. التحقق من أن البوت يعمل

1. افتح رابط `/health`. يجب أن ترى:

```json
{"status":"ok"}
```

2. افتح البوت داخل Telegram واضغط **Start** أو أرسل `/start`.
3. جرب `/today` ثم `/quiz` ثم `/stats`.
4. افتح رابط `/login` وسجل الدخول بواسطة `ADMIN_USERNAME` و`ADMIN_PASSWORD`.
5. تحقق من ظهور خمسة أمراض و15 سؤالًا. إذا ظهرت أصفار، شغّل `python seed_data.py` مرة واحدة من بيئة محلية أو GitHub Codespaces بعد وضع مفاتيح Supabase فيها مؤقتًا.

## 7. النشر اليومي على الخطة المجانية

يوجد قالب GitHub Actions في:

```text
deployment/github/daily_publish.yml
```

لأن التكامل الذي رفع المستودع لا يملك صلاحية إنشاء Workflows تلقائيًا، أنشئ من GitHub الملف التالي وانسخ إليه محتوى القالب:

```text
.github/workflows/daily_publish.yml
```

ثم أضف من **GitHub → Settings → Secrets and variables → Actions** سرين:

| السر | القيمة |
|---|---|
| `APP_URL` | رابط Render الكامل دون `/` في النهاية |
| `SCHEDULER_SECRET` | القيمة نفسها الموجودة في متغير Render |

يساعد هذا الطلب اليومي على إيقاظ الخدمة واستدعاء مسار النشر. ومع ذلك، قد تتأخر المهام المجدولة أو يستغرق Render نحو دقيقة للاستيقاظ، لذلك يبقى التوقيت تقريبيًا على الخطة المجانية.

## 8. مقارنة خيارَي التشغيل

| الخيار | النتيجة | التكلفة | الإعداد |
|---|---|---:|---|
| Render Free مع طلب GitHub يومي | مناسب للتجربة، لكنه ينام وقد يتأخر عند الاستيقاظ | مجاني ضمن حدود Render | بسيط |
| Render Web Service مدفوع | لا يدخل في السكون، واستجابة البوت أكثر ثباتًا | حسب خطة Render | نفس المشروع مع تغيير الخطة |

## 9. استكشاف الأخطاء السريع

إذا لم يرد البوت، افتح `/health` أولًا وانتظر استيقاظ Render، ثم أعد إرسال الأمر. افحص **Logs** بحثًا عن رسالة إعدادات ناقصة، وتأكد من أن `BOT_MODE=webhook` و`APP_ENV=production`. إذا ظهر خطأ Supabase `401` أو `permission denied`، تحقق من رابط المشروع ومن استخدام `SUPABASE_SECRET_KEY` الخادمي. لا تنسخ المفاتيح إلى سجل دعم أو لقطة شاشة.

## المراجع

[1]: https://render.com/docs/free "Render Free Instances"
[2]: https://render.com/docs/your-first-deploy "Your First Render Deploy"
[3]: https://render.com/docs/infrastructure-as-code "Render Blueprints"
