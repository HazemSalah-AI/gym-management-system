# Phase 5 — Authentication & Authorization

## 1. الحالة: PARTIAL

تنفيذ الكود واختباراته اكتمل في النسخة المرفقة، لكن المرحلة ليست مكتملة تشغيليًا
حتى يتم اختبار Docker وPostgreSQL وإنشاء الأدمن الحقيقي على جهازك.

- **54 اختبارًا آليًا نجحوا** على Python 3.12.14 وSQLite مع تفعيل Foreign Keys.
- نجح اختبار إضافي عبر HTTP حقيقي على Uvicorn لمسار CSRF → Login → Me → Logout.
- تم توليد ومراجعة SQL الخاص بـPostgreSQL دون تنفيذه على PostgreSQL.
- **Docker وPostgreSQL الفعلي: NOT VERIFIED.** لا يوجد Docker هنا، ومحاولة
  تجهيز PostgreSQL اصطدمت بصلاحيات نظام التشغيل.
- لم يتم الوصول إلى قاعدة بياناتك، أو تشغيل migrations عليها، أو إنشاء أدمن حقيقي.

## 2. الخصائص المنفذة

المستخدمون، الأدوار، الصلاحيات، العلاقات، Argon2id، الجلسات القابلة للإبطال،
CSRF، مسارات الدخول والخروج والمستخدم الحالي، permission dependencies،
bootstrap آمن ومتكرر، اختبارات، وتوثيق التشغيل والتحقق اليدوي.

لم تتم إضافة واجهة مستخدم أو public signup. صلاحيات إدارة المستخدمين موجودة
كأساس للـRBAC؛ صفحات وعمليات إدارة المستخدمين نفسها ليست ضمن هذه المرحلة.

## 3. الملفات الجديدة

- `PHASE5_REPORT.md`
- `alembic/versions/6eb7f390a89e_add_authentication_and_revocable_sessions.py`
- `app/api/dependencies.py`
- `app/api/routes/auth.py`
- `app/core/csrf.py`
- `app/core/permissions.py`
- `app/core/security.py`
- `app/models/auth_session.py`
- `app/models/mixins.py`
- `app/models/permission.py`
- `app/models/role.py`
- `app/models/role_permission.py`
- `app/models/user.py`
- `app/repositories/auth_session.py`
- `app/repositories/bootstrap.py`
- `app/repositories/user.py`
- `app/schemas/auth.py`
- `app/services/auth.py`
- `app/services/bootstrap.py`
- `pytest.ini`
- `requirements-dev.txt`
- `scripts/__init__.py`
- `scripts/bootstrap_auth.py`
- `scripts/verify_auth.py`
- `tests/conftest.py`
- `tests/test_auth.py`
- `tests/test_authorization.py`
- `tests/test_bootstrap.py`
- `tests/test_security_and_migrations.py`

## 4. الملفات المعدلة

- `.dockerignore`
- `.env.example`
- `.gitignore`
- `README.md`
- `alembic/env.py`
- `app/core/config.py`
- `app/db/session.py`
- `app/main.py`
- `app/models/__init__.py`
- `docker-compose.yml`
- `requirements.txt`

تم الحفاظ على أسلوب SQLAlchemy المتزامن والمجلدات الحالية. الـDockerfile
والمigration القديمة لم يتغيرا. الملفات الأصلية التي لم تحتج تعديلًا بقيت كما هي.

## 5. تغييرات قاعدة البيانات

Migration: `6eb7f390a89e_add_authentication_and_revocable_sessions.py`.
Parent revision: `1936134f3938`.

| الجدول | الغرض والقيود |
| --- | --- |
| users | username/email unique indexes، role FK مع RESTRICT، active flag، Argon2 hash، timestamps وlast_login_at؛ checks لتخزين الهوية lowercase |
| roles | اسم دور unique؛ علاقات المستخدمين والصلاحيات |
| permissions | code unique ووصف |
| role_permissions | composite primary key يمنع تكرار العلاقة؛ FKs مع CASCADE وفهرس permission_id |
| auth_sessions | hash لتوكن الجلسة كمفتاح، user FK مع CASCADE، created_at وexpires_at مع فهارس |

تم استخدام Alembic `command.revision(..., autogenerate=True)` مع اتصال SQLite
اختباري معزول، لعدم توفر PostgreSQL. تمت مراجعة upgrade وdowngrade قبل التطبيق
على قواعد الاختبار. التوليد الأول كتب Boolean default كـ`1`؛ تم تصحيحه إلى
`sa.true()` ليُنتج `true` في PostgreSQL. لا توجد عمليات حذف لجداول سابقة في upgrade.

اختبار downgrade/upgrade تم فقط في قواعد اختبار فارغة ومعزولة. PostgreSQL SQL
يستخدم `TIMESTAMP WITH TIME ZONE` والقيمة الافتراضية الصحيحة للـBoolean، لكن
التحقق من التنفيذ الفعلي على PostgreSQL ما زال مطلوبًا.

## 6. تصميم Authentication

1. العميل يحصل على CSRF token وكوكي أولية.
2. يرسل username/password في جسم JSON مع `X-CSRF-Token`.
3. الـroute يفحص CSRF ويستدعي AuthService.
4. الـrepository يجلب المستخدم، والـservice يقارن كلمة المرور بهاش Argon2.
5. عند النجاح، يتم تحديث last_login_at وإنشاء سجل جلسة داخل نفس transaction.
6. يتجدد session token وCSRF token، وتُحفظ أقل بيانات هوية في الكوكي.
7. كل طلب محمي يفحص سجل الجلسة وصلاحيته والمستخدم الفعلي من قاعدة البيانات.

كلمة المرور لا تُخزن ولا تُعاد في الاستجابة. كل كلمة مرور لها salt مستقل.
عند فشل كتابة الجلسة أو تحديث وقت الدخول، يتم rollback للتغييرات معًا.

## 7. تصميم Authorization

`User → Role → Permissions → require_permission(code)`.

الـdependency تقرأ الصلاحيات من قاعدة البيانات باستخدام relationship loading
واضح. تغيير الدور أو منح/سحب صلاحية يظهر في الطلب التالي دون إعادة تسجيل دخول.
لا يوجد شرط `if role == Admin` موزع على الـroutes، ولا اعتماد على صلاحيات من frontend.

| Permission | Admin | Receptionist | Trainer | Owner |
| --- | --- | --- | --- | --- |
| members.read | نعم | نعم | نعم | نعم |
| members.write | نعم | نعم | لا | لا |
| payments.read | نعم | نعم | لا | نعم |
| payments.write | نعم | نعم | لا | لا |
| attendance.record | نعم | نعم | نعم | لا |
| users.manage | نعم | لا | لا | لا |
| reports.read | نعم | لا | لا | نعم |

اختيار الـOwner هنا هو الاطلاع على بيانات العمل والتقارير؛ إدارة الحسابات للأدمن.
المصفوفة مجمعة في ملف واحد ويمكن تعديلها ثم إعادة تشغيل bootstrap.

## 8. الضوابط الأمنية والقرارات

- الكوكي `gym_session`: HttpOnly، SameSite=Lax، host-only، مدة 28800 ثانية.
- وضع production يفرض Secure؛ يلزم HTTPS. secret ضعيف أو placeholder أو اسم
  environment غير معروف يمنع تشغيل التطبيق.
- تم إزالة بيانات الاتصال الثابتة من Compose، واستخدام `.env`؛ لا توجد أسرار
  أو `.env` ضمن ملفات التسليم أو سجل commits المنشأ هنا.
- CSRF على login وlogout، مع token عشوائي و`hmac.compare_digest`، وتغيير token
  بعد الدخول. يتطلب أي route مستقبلي يغير البيانات CSRF dependency أيضًا.
- عند الخروج يُحذف سجل الجلسة من السيرفر؛ الاختبارات تؤكد رفض إعادة استخدام
  الكوكي القديمة. انتهاء الثماني ساعات مطلق ولا يتم تمديده بتجديد الكوكي.
- المستخدم المحذوف أو غير النشط يحصل على 401 وتُمسح جلسته؛ عند رصد مستخدم غير
  نشط تُلغى جميع جلساته. أي خدمة مستقبلية لتعطيل الحساب/تغيير كلمة المرور ينبغي
  أن تبطل جلساته في نفس transaction الخاصة بالتغيير.
- بيانات اعتماد غير صحيحة أو حساب غير نشط: 401 بنفس الرسالة العامة.
- جلسة مفقودة/غير صالحة: 401. مستخدم معروف بلا صلاحية: 403. CSRF غير صالح: 403.
- response schemas تستبعد password_hash، وvalidation errors تستبعد قيم input
  التي قد تحتوي كلمة المرور، واستجابات auth عليها `Cache-Control: no-store`.
- bootstrap لا يغير أدمن موجودًا أو يرفع صلاحية مستخدم موجود تلقائيًا. كلمة
  المرور عن طريق getpass فقط، مع confirmation وحد أدنى 12 حرفًا.
- PostgreSQL advisory lock يحمي تزامن bootstrap؛ هذا المسار مكتوب لكنه لم
  يُختبر على PostgreSQL في هذه البيئة.

**سبب إضافة الجدول الخامس:** SessionMiddleware يوقّع الكوكي ولا يوفر بمفرده
جلسة مخزنة على السيرفر أو إبطالًا لها. لذلك تمت إضافة `auth_sessions` مع
`session_token` عشوائي في الكوكي وhash فقط في قاعدة البيانات. البيانات الأخرى
في الكوكي هي `user_id` و`csrf_token`؛ لا دور أو صلاحيات أو كلمة مرور.

مرجع hashing: [pwdlib](https://frankie567.github.io/pwdlib/reference/pwdlib/).
مرجع تحميل العلاقات: [SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html).
كما تمت مراجعة تنفيذ SessionMiddleware وArgon2Hasher من نسخ الحزم المثبتة.

## 9. الاختبارات والأوامر المنفذة

| التحقق | النتيجة |
| --- | --- |
| فحص بنية المشروع والملفات الأصلية | PASS |
| git status عند استلام ZIP | لا يوجد .git؛ الأرشيف لا يتضمن تاريخك الأصلي |
| استيراد التطبيق الأصلي وGET /health | PASS؛ لم تكن هناك اختبارات سابقة |
| تثبيت requirements الأصلية + dependencies الجديدة | PASS؛ لم تتغير إصدارات الحزم الأصلية |
| python -m pip check | PASS |
| توليد migration عبر Alembic API | PASS على SQLite؛ PostgreSQL غير متاح |
| مراجعة upgrade/downgrade قبل التطبيق | PASS |
| upgrade head / current at head / alembic check | PASS على SQLite عبر Alembic API |
| الجداول والفهارس والـFKs والـunique constraints | PASS على SQLite |
| python -m pytest -q | 54 passed؛ SQLite |
| اختبار PostgreSQL offline SQL | PASS؛ لا يثبت عمل PostgreSQL الفعلي |
| bootstrap idempotency وAdmin creation | PASS باستخدام مستخدمين مؤقتين داخل الاختبارات |
| Secure cookie وCSRF و401/403 وعدم تسريب hash | PASS |
| إبطال الجلسات وتغيير الأدوار والصلاحيات | PASS |
| تشغيل Uvicorn والتحقق عبر scripts.verify_auth | PASS على HTTP حقيقي وقاعدة SQLite مؤقتة |
| فحص literals للأسرار والملفات المتتبعة ومراجعة الكود | PASS؛ لا أسرار ثابتة في تغييرات المرحلة |
| Docker build / compose startup | NOT VERIFIED؛ Docker غير موجود |
| PostgreSQL live migration / connectivity / advisory lock | NOT VERIFIED؛ تجهيز السيرفر تعطل بسبب صلاحيات النظام |
| إنشاء الأدمن الحقيقي | BLOCKED؛ يتطلب جهازك وقاعدة بياناتك وإدخال كلمة المرور بأمان |

أظهر pytest تحذيرين من الحزم: انتقال Starlette test client من httpx إلى httpx2،
وإهمال alias قديم لـAnyIO. لم يفشل أي اختبار بسببهما. لم تتم ترقية حزم المشروع
الأصلية لمجرد إزالة التحذيرات. لم تكن هناك إعدادات lint/type-check في المشروع.

فحص Git للنسخة الأصلية كشف CRLF المعتاد على Windows ومسافة زائدة موجودة مسبقًا
في docstring الـmigration القديمة. لم يتم تغيير migration سابقة بسبب تنسيقها.

## 10. Git commits

تم إنشاء تاريخ مراجعة محلي مستقل، لأن `git archive` لا يرفق `.git`:

1. `feat: add authentication data model`
2. `feat: add session authentication`
3. `feat: add permission-based authorization`

قبل commit الأول تم اختبار نسخة الملفات staged: import، health، migration،
وعدم وجود schema drift. قبل الثاني تم اختبار نسخة staged: CSRF، login، me، logout.
قبل الثالث تم تشغيل كامل مجموعة الاختبارات ومراجعة التغييرات.

الـhashes الفعلية موجودة في `DELIVERY_COMMITS.txt` خارج مجلد المصدر داخل ZIP.
ملف `phase5-history.bundle` يحتوي على التاريخ الجديد للمراجعة. لا يمثل تاريخ
Git الأصلي عندك، ولم يحدث push أو اتصال بـGitHub.

## 11. Checklist كاملة

PASS هنا يعني أن المهمة البرمجية واختبارها المتاح نجحا؛ الاختبارات التشغيلية
غير المتاحة مذكورة صراحة في الصفوف المعنية وفي quality gate أعلاه.

| Task | الحالة | ما تم / سبب النقص |
| --- | --- | --- |
| 1 Dependencies | PARTIAL | التثبيت وpip check نجحا؛ Docker build غير متاح |
| 2 User Model | PASS | الحقول، uniqueness، normalization والعلاقة |
| 3 Role Model | PASS | الأدوار والعلاقات والقيود |
| 4 Permission Model | PASS | code unique والعلاقة |
| 5 Association Table | PASS | composite PK وFKs واختبار منع التكرار |
| 6 Register Models | PASS | Base.metadata وAlembic يريان الجداول |
| 7 Authentication Migration | PARTIAL | autogenerated ومراجعة واختبار SQLite وPG offline؛ تطبيق PostgreSQL مطلوب |
| 8 PostgreSQL Verification | BLOCKED | لا يوجد PostgreSQL يعمل هنا؛ فحص SQLite لا يعوضه |
| 9 Password Security | PASS | Argon2id واختبارات التحقق والهاش التالف |
| 10 User Repository | PASS | get_by_id/get_by_username وDB queries فقط |
| 11 Auth Service | PASS | verification وlast_login_at وtransaction وgeneric 401 |
| 12 Session Middleware | PASS | الاسم والمدة والكوكي وproduction validation |
| 13 Session Design | PASS | user_id وsession_token وCSRF فقط؛ شرح الإضافة أعلاه |
| 14 Current User | PASS | DB-backed، حذف/تعطيل المستخدم، مسح الجلسة |
| 15 RBAC | PASS | reusable permission dependency؛ 401/403 صحيحة |
| 16 CSRF | PASS | secure token وconstant-time compare وlogin/logout protection |
| 17 Auth Routes | PASS | csrf/login/logout/me مع safe schemas |
| 18 Router Registration | PASS | المسارات مسجلة دون prefix مكرر |
| 19 Permission Matrix | PASS | أربعة أدوار وسبع صلاحيات مركزية |
| 20 Bootstrap Script | PASS | seed/update/idempotency؛ tested on isolated SQLite |
| 21 Secure Admin Creation | PASS | getpass وconfirmation وlength؛ منع fallback الذي يُظهر كلمة المرور |
| 22 Run Real Bootstrap | BLOCKED | أدمن الاختبار فقط اتعمل؛ أدمنك الحقيقي يحتاج تشغيلًا وإدخالًا منك |
| 23 Authentication Tests | PASS | تدفق الدخول والأخطاء والخروج والتعطيل على SQLite وHTTP smoke |
| 24 Authorization Tests | PASS | السماح/الرفض/عدم الدخول وتغييرات الصلاحيات من backend |

## 12. المتبقي فعليًا

1. دمج الملفات في مجلد مشروعك الأصلي مع الاحتفاظ بـ`.git` و`.env`.
2. Docker build/start على جهازك وPostgreSQL migration/checks.
3. تشغيل الاختبارات الاختيارية على PostgreSQL للتحقق من المسارات الخاصة به.
4. إنشاء الأدمن الحقيقي بتيرمنال آمن ثم تشغيل verify_auth بحسابه.

هذه المخرجات لا تدّعي أن خادم production تم تشغيله أو اختباره.

## 13. التحقق اليدوي

اتبع `START_HERE_AR.md` الموجود خارج مجلد المصدر في ZIP أولًا.
بعد تجهيز `.env` وتشغيل الأوامر من مشروعك الأصلي:

```bash
python -m pip install -r requirements-dev.txt
docker compose build web
docker compose up -d
docker compose exec web alembic upgrade head
docker compose exec web alembic current
docker compose exec web alembic check
docker compose exec web python -m scripts.bootstrap_auth --seed-only
docker compose exec web python -m scripts.bootstrap_auth
python -m scripts.verify_auth
python -m pytest -q
GYM_TEST_POSTGRES=1 python -m pytest -q
```

الأمر الأخير يُنشئ ويحذف schemas اختبار عشوائية خاصة به في PostgreSQL، ولا
يختبر داخل جداول المشروع الحالية. يحتاج مستخدم DB لديه صلاحية CREATE SCHEMA.

الـAPI requests الدقيقة موضحة في README وفي `scripts/verify_auth.py`. السكربت
يمر بالطلبات كلها ويحفظ credentials/cookies في الذاكرة فقط. لا تكتب كلمة
المرور في curl أو command-line arguments أو ملف JSON، ولا ترسلها في الشات.

## 14. شرح مبسط لتدفق الطلب

اعتبر الجلسة تصريح دخول له رقم عشوائي. المتصفح يحتفظ بالتصريح في cookie،
والسيرفر يحتفظ ببصمة الرقم وصاحب التصريح ووقت انتهائه في قاعدة البيانات.

عند دخول طلب إلى `/auth/me`، الـdependency تفحص التصريح ثم تجلب المستخدم.
وعند دخول طلب يحتاج صلاحية معينة، تفحص صلاحيات دور هذا المستخدم قبل الوصول
إلى كود تنفيذ العملية. امتلاك جلسة يثبت الهوية؛ امتلاك permission يسمح بالعملية.

الـrepository يتعامل مع البيانات؛ الـservice يقرر صحة الدخول ويدير transaction؛
الـroute يتعامل مع HTTP والكوكي. لذلك يمكن إضافة صفحات الأعضاء والمدفوعات
لاحقًا مع إعادة استخدام نظام التحقق والصلاحيات نفسه.
