# Football Match Predictor

مشروع بايثون لتوقع نتائج مباريات كرة القدم اعتمادًا على بيانات [football-data.org](https://www.football-data.org/).

يدعم:

- **CLI** على الكمبيوتر/Termux
- **واجهة موبايل Kivy** + بناء **APK** عبر **GitHub Actions**

> نموذج إحصائي بسيط للتجربة والتعليم — **ليس** نصيحة مراهنات.

---

## شرح الوحدات (كل ملف ماذا يفعل؟)

| الملف / المجلد | الدور |
|----------------|--------|
| `config.py` | الإعدادات المركزية: المسارات، الدوريات، أوزان التوقع، مفتاح API من البيئة |
| `main.py` | واجهة CLI الرئيسية (`update` / `predict` / `teams` / `schedule` / `status`) |
| `fetch_data.py` | سكربت مستقل لجلب النتائج + الجدول وحفظها في CSV و SQLite |
| `predict.py` | سكربت مستقل للتوقع (مباراة واحدة أو الجدول كامل) |
| `mobile_app.py` | واجهة Kivy للأندرويد (توقّع / جدول / فرق / تحديث) |
| `src/data_loader.py` | طبقة الـ API: طلبات، rate-limit، تحويل JSON → DataFrame، حفظ CSV |
| `src/database.py` | طبقة SQLite: إنشاء الجداول، حفظ/قراءة `matches` و `schedule` |
| `src/predictor.py` | محرك التوقع: فورم، هجوم/دفاع، H2H، احتمالات Softmax |
| `data/` | التخزين المحلي (`matches.db`, CSV) — **لا يُرفع** للـ git عادةً |
| `models/` | مكان محفوظات ML مستقبلًا (حاليًا غير مستخدم) |
| `buildozer.spec` | إعدادات تعبئة تطبيق Android |
| `.github/workflows/build-apk.yml` | CI يبني APK ويرفعه كـ Artifact |
| `.env.example` | نموذج لمتغير مفتاح الـ API |
| `requirements.txt` | اعتمادات CLI |
| `requirements-mobile.txt` | اعتمادات تشغيل الواجهة محليًا (Kivy) |

### تدفق البيانات باختصار

```text
football-data.org API
        │
        ▼
 src/data_loader.py  ──CSV──► data/*.csv
        │
        ▼
 src/database.py     ──SQL──► data/matches.db
        │
        ▼
 src/predictor.py    ──► احتمالات + سبب
        │
   ┌────┴────┐
   ▼         ▼
 main.py   mobile_app.py
 (CLI)      (Kivy/APK)
```

### كيف يعمل التوقع؟ (`src/predictor.py`)

لكل فريق من آخر 5 مباريات:

- **هجوم** = متوسط الأهداف المسجّلة
- **دفاع** = متوسط الأهداف المستقبلة
- **فورم** = نقاط / أقصى نقاط (فوز=3، تعادل=1، خسارة=0)

ثم:

```text
EGH = (هجوم_المضيف + دفاع_الضيف) / 2
EGA = (هجوم_الضيف + دفاع_المضيف) / 2
goal_score = EGH - EGA
form_score = فورم_المضيف - فورم_الضيف
h2h_score  = تفوق نقاط المواجهات المباشرة

final = goal_score + 0.8*form_score + 0.6*h2h_score
```

`final` تتحول لاحتمالات (مضيف / تعادل / ضيف) عبر Softmax تقريبي.

---

## التثبيت (CLI)

```bash
cd football_predictor
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# مفتاح API — لا تضعه في الكود
export FOOTBALL_DATA_API_TOKEN="your_token_here"
# أو انسخ .env.example إلى .env واملأه (الواجهة mobile تقرأه)
```

احصل على مفتاح مجاني من: https://www.football-data.org/client/register

### أوامر سريعة

```bash
python main.py update
python main.py update --full-history
python main.py predict "Arsenal" "Chelsea"
python main.py teams
python main.py schedule
python main.py status
```

أو:

```bash
python fetch_data.py
python predict.py --home Arsenal --away Chelsea
python predict.py --schedule
```

---

## الرفع على GitHub

```bash
cd football_predictor
git init
git add .
git commit -m "Initial commit: football predictor + APK workflow"
git branch -M main
git remote add origin https://github.com/<USER>/<REPO>.git
git push -u origin main
```

### أسرار GitHub (مهمة)

في المستودع: **Settings → Secrets and variables → Actions**

| Secret | الغرض |
|--------|--------|
| `FOOTBALL_DATA_API_TOKEN` | مفتاح football-data.org (جلب بيانات أثناء CI اختياريًا، وتشغيل التحديث لاحقًا) |

> المفتاح **لا يُثبت** داخل `config.py`. يُقرأ من `FOOTBALL_DATA_API_TOKEN` فقط.

ملفات مستبعدة تلقائيًا عبر `.gitignore`: `.env`, `data/*.csv`, `data/*.db`, `__pycache__`, مخرجات Buildozer.

---

## بناء APK عبر GitHub Actions

الملف: `.github/workflows/build-apk.yml`

1. ارفع المشروع إلى GitHub.
2. (اختياري) أضف السر `FOOTBALL_DATA_API_TOKEN` لجلب بيانات داخل الـ APK.
3. من تبويب **Actions** شغّل workflow **Build Android APK** (أو ادفع على `main`).
4. بعد نجاح البناء: **Artifacts → football-predictor-apk** → حمّل الـ APK.

البناء يستخدم Buildozer على Ubuntu (قد يستغرق 30–90 دقيقة أول مرة).

### تشغيل الواجهة محليًا (قبل الـ APK)

```bash
pip install -r requirements-mobile.txt
python mobile_app.py
```

### بناء محلي بـ Buildozer (Linux)

```bash
pip install buildozer cython
buildozer android debug
# الناتج غالبًا في bin/*.apk
```

---

## قاعدة البيانات

`data/matches.db`

### `matches`

| العمود | الوصف |
|--------|--------|
| date | التاريخ |
| league | PL / PD |
| home_team / away_team | الفريقان |
| home_goals / away_goals | الأهداف |
| result | 1 مضيف / 0 تعادل / 2 ضيف |

### `schedule`

المباريات القادمة (بدون نتيجة).

---

## حد الـ API

الخطة المجانية ≈ **10 طلبات/دقيقة**. المشروع يؤخّر ~6.5s بين الطلبات ويعيد المحاولة عند `429`.

---

## ملاحظات

- التوقع الحالي **لا يعتمد** على `scikit-learn` (أُزيل من المتطلبات الأساسية لتسهيل Termux وAndroid).
- بعض فرق الموسم الجديد قد لا تظهر في النتائج الحديثة فيُتخطى توقعها.
- على Android: إن شحنت APK بدون بيانات، استخدم زر **تحديث** مع ضبط المفتاح في بيئة الجهاز، أو ابنِ الـ APK بعد `fetch_data` في CI.
