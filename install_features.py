"""Подключает этапы ФТ-1.2, ФТ-1.3 и ФТ-1.6 к вашему сайту.

Запуск (один раз, из папки проекта):  python install_features.py
Что делает:
  1. в app.py добавляет две строки: from features import register_features и register_features(app);
  2. в templates/base.html добавляет подключение стилей features.css и вторую строку меню
     («Рекомендации», «Отзывы», «Админка»).
Повторный запуск ничего не дублирует. Копии старых файлов сохраняются рядом с расширением .bak.
"""
import os
import shutil
import sys

APP_MARK = "register_features(app)"
BASE_MARK = "KINO-FEATURES"

APP_CODE = [
    "# Подбор фильмов, отзывы и админка (ФТ-1.2, ФТ-1.3, ФТ-1.6)",
    "from features import register_features",
    "register_features(app)",
]

CSS_LINE = '  <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'features.css\') }}"> {# KINO-FEATURES #}'

SUBNAV = [
    "{# KINO-FEATURES: вторая строка меню #}",
    "{% if current_user %}",
    "<div class=\"subnav\"><div class=\"wrap subnav-in\">",
    "  <a href=\"{{ url_for('recommendations.index') }}\" class=\"{{ 'active' if request.blueprint == 'recommendations' }}\">Рекомендации</a>",
    "  <a href=\"{{ url_for('reviews.index') }}\" class=\"{{ 'active' if request.blueprint == 'reviews' }}\">Отзывы</a>",
    "  {% if current_user.role == 'admin' %}<a href=\"{{ url_for('admin.applications') }}\" class=\"{{ 'active' if request.blueprint == 'admin' }}\">Админка</a>{% endif %}",
    "</div></div>",
    "{% endif %}",
]


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def patch_app(path):
    text = read(path)
    if APP_MARK in text:
        print("app.py: уже подключено, пропускаю")
        return True
    nl = "\r\n" if "\r\n" in text else "\n"
    marker = 'if __name__ == "__main__":'
    if marker not in text:
        marker = "if __name__ == '__main__':"
    if marker not in text:
        print("app.py: не нашла строку if __name__ == \"__main__\". Добавьте вручную перед ней:\n  " + "\n  ".join(APP_CODE[1:]))
        return False
    shutil.copyfile(path, path + ".bak")
    block = nl.join(APP_CODE) + nl + nl + nl
    write(path, text.replace(marker, block + marker, 1))
    print("app.py: готово")
    return True


def patch_base(path):
    text = read(path)
    if BASE_MARK in text:
        print("base.html: уже подключено, пропускаю")
        return True
    nl = "\r\n" if "\r\n" in text else "\n"
    if "</head>" not in text or "</header>" not in text:
        print("base.html: не нашла </head> или </header>. Напишите мне, подскажу, куда вставить.")
        return False
    shutil.copyfile(path, path + ".bak")
    text = text.replace("</head>", CSS_LINE + nl + "</head>", 1)
    text = text.replace("</header>", "</header>" + nl + nl.join(SUBNAV), 1)
    write(path, text)
    print("base.html: готово")
    return True


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    ok = patch_app(os.path.join(folder, "app.py"))
    ok = patch_base(os.path.join(folder, "templates", "base.html")) and ok
    needed = ["features.py", "static/features.css", "templates/recommendations.html"]
    missing = [n for n in needed if not os.path.exists(os.path.join(folder, n))]
    if missing:
        print("Не хватает файлов:", ", ".join(missing), "— распакуйте архив в папку проекта целиком.")
        ok = False
    print("Готово." if ok else "Есть замечания, смотрите выше.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
