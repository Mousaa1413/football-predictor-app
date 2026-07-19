# =============================================================================
# Buildozer spec — Football Predictor (Kivy)
# نقطة الدخول: app.py
# التوقع: src/predictor.py (فورم + H2H) — بدون scikit-learn
# =============================================================================

[app]

# ---- هوية التطبيق ----
title = Football Predictor
package.name = footballpredictor
package.domain = org.footballpredictor
version = 0.1.0

# ---- المصدر ----
# Buildozer يبحث افتراضيًا عن main.py — نحدد app.py صراحة
source.dir = .
source.main = app.py

# امتدادات تُنسخ داخل الـ APK
source.include_exts = py,png,jpg,jpeg,kv,atlas,csv,db,txt,json,xml,ttf

# تضمين حزمة المنطق + بيانات محلية إن وُجدت (CSV/DB بعد fetch)
source.include_patterns = src/*.py,data/*.csv,data/*.db,data/.gitkeep

# استبعاد ما لا يلزم داخل الحزمة
source.exclude_dirs = .git,.github,.venv,venv,env,tests,bin,.buildozer,__pycache__,src/__pycache__,models,.idea,.vscode
source.exclude_patterns = *.pyc,*~,*.apk,*.aab,*.jks,.env,.env.*,*.md,fetch_data.py,predict.py,main.py,mobile_app.py,requirements*.txt

# ---- الاعتمادات (python-for-android recipes / pip) ----
#
# لماذا هذه القائمة؟
#   kivy            → واجهة app.py
#   pandas + numpy  → قراءة النتائج/الجدول وحساب الفورم (src/database + predictor)
#   requests + ...  → data_loader يستورد requests (حتى لو التوقع offline غالبًا)
#   openssl         → HTTPS على Android عند أي طلب API
#   sqlite3         → data/matches.db
#   pyjnius/android → جسر Android القياسي لـ Kivy
#   hostpython3     → بناء مضيف مستقر مع p4a الحديث
#
# scikit-learn / joblib:
#   غير مستخدمين في منطق التوقع البسيط الحالي → لا نضمّهما
#   (ثقيلان، ووصفات Android لهما متعبة وقد تفشل البناء)
#
requirements = python3,hostpython3,kivy==2.3.0,pillow,pyjnius,android,sqlite3,openssl,requests,urllib3,certifi,charset-normalizer,idna,numpy,pandas

# مكتبات نظام (وصفات p4a) — تُترك فارغة عادةً مع القائمة أعلاه
# android.gradle_dependencies =

# ---- واجهة العرض ----
orientation = portrait
fullscreen = 0
# icon.filename = %(source.dir)s/assets/icon.png
# presplash.filename = %(source.dir)s/assets/presplash.png

# ---- أذونات Android ----
# INTERNET فقط إن أردت تحديث البيانات من الـ API لاحقًا من الجهاز
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# ---- SDK / NDK ----
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.accept_sdk_license = True

# معماريات شائعة للأجهزة الحقيقية + بعض المحاكيات
android.archs = arm64-v8a,armeabi-v7a

android.allow_backup = True
android.logcat_filters = *:S python:D
android.release_artifact = apk
android.debug_artifact = apk

# نسخ بيانات assets كما هي (CSV/DB) دون ضغط إضافي يفسدها أحيانًا
# android.add_assets =

# لا نحتاج خدمات/boot في الخلفية
# services =

# تخطّي اختبارات p4a التي تبطّئ CI أحيانًا
p4a.branch = master
# p4a.local_recipes =
# p4a.bootstrap = sdl2

# تنظيف نسبي أسرع عند إعادة البناء (اختياري)
# android.skip_update = False
# android.copy_libs = 1

# ---- iOS (غير مستهدف حاليًا) ----
# ios.kivy_ios_url = https://github.com/kivy/kivy-ios
# ios.kivy_ios_branch = master

[buildozer]

log_level = 2
warn_on_root = 1

# مجلدات البناء/الإخراج
# build_dir = ./.buildozer
# bin_dir = ./bin
