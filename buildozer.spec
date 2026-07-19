# =============================================================================
# Buildozer spec — Football Predictor (Kivy)
# نقطة الدخول على Android: main.py (في CI يُنسخ من app.py)
# التوقع: src/predictor.py (فورم + H2H) — بدون scikit-learn
# =============================================================================

[app]

# ---- هوية التطبيق ----
title = Football Predictor
package.name = footballpredictor
package.domain = org.footballpredictor
version = 0.1.0

# ---- المصدر ----
# p4a/Buildozer يتوقع main.py في source.dir (لا يوجد مفتاح source.main)
source.dir = .

# امتدادات تُنسخ داخل الـ APK
source.include_exts = py,png,jpg,jpeg,kv,atlas,csv,db,txt,json,xml,ttf

# أنماط إضافية (لا تحل محل include_exts؛ تُستخدم لإلغاء استبعاد إن لزم)
source.include_patterns = src/*.py,data/*.csv,data/*.db

# استبعاد ما لا يلزم داخل الحزمة
# ملاحظة: لا تستبعد main.py — هو نقطة دخول Android (يُجهَّز من app.py في الـ workflow)
source.exclude_dirs = tests,bin,venv,.venv,env,.git,.github,.buildozer,__pycache__,models,.idea,.vscode,p4a-recipes
source.exclude_patterns = *.pyc,*~,*.apk,*.aab,*.jks,.env,.env.*,*.md,fetch_data.py,predict.py,mobile_app.py,requirements*.txt,main_cli.py

# ---- الاعتمادات (python-for-android recipes / pip) ----
#
# لماذا هذه القائمة؟
#   python3,kivy     → تشغيل واجهة app/main
#   pillow           → صور Kivy
#   pyjnius,android  → جسر Android
#   sqlite3          → data/matches.db
#   openssl + requests (+ deps) → HTTPS إن لزم
#   numpy,pandas     → database/predictor
#
# مهم: p4a master الافتراضي python 3.14.2 — pandas 2.3.0 يفشل compile عليه:
#   ccalendar.pyx.c: error: member reference type 'int' is not a pointer
#   (_PyUFuncObject_GET_ITEM_DATA / PyDataType_* implicit decl على cp314)
# لذلك نثبت hostpython3+python3 على 3.11.13 (متوافق مع numpy/pandas 2.3 و Kivy 2.3).
# يجب تطابق إصدار hostpython3 و python3 حرفيًا (فحص p4a).
# scikit-learn / joblib: غير مستخدمين في منطق التوقع الحالي
#
requirements = hostpython3==3.11.13,python3==3.11.13,kivy==2.3.0,pillow,pyjnius,android,sqlite3,openssl,requests,urllib3,certifi,charset-normalizer,idna,numpy,pandas

# ---- واجهة العرض ----
orientation = portrait
fullscreen = 0

# ---- أذونات Android ----
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# ---- SDK / NDK ----
# متوافق مع p4a الحديث على Ubuntu 22.04
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True

# معماريات الأجهزة الحقيقية الشائعة
android.archs = arm64-v8a,armeabi-v7a

android.allow_backup = True
android.logcat_filters = *:S python:D
android.release_artifact = apk
android.debug_artifact = apk

# فرع p4a — master أحدث الوصفات (numpy/pandas/kivy)
p4a.branch = master
p4a.bootstrap = sdl2
# وصفة numpy محلية: patch لـ #include <unordered_map> (NDK libc++)
p4a.local_recipes = %(source.dir)s/p4a-recipes

[buildozer]

log_level = 2
warn_on_root = 0
