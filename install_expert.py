"""Добавляет в меню авторов ссылку «Мои рецензии» (templates/base.html). Можно запускать повторно.
Запуск в папке проекта:  python install_expert.py
"""
import os

BASE = os.path.join("templates", "base.html")
ANCHOR = "request.blueprint == 'author_application' }}\">Статус автора</a>"
LINK = ("{% if current_user and current_user.role == 'author' %}<a href=\"{{ url_for('expert.mine') }}\" "
        "class=\"{{ 'active' if request.blueprint == 'expert' }}\">Мои рецензии</a>{% endif %}")


def main():
    if not os.path.exists(BASE):
        print("Не найден templates/base.html. Запускайте скрипт в папке проекта.")
        return 1
    with open(BASE, "rb") as f:
        text = f.read().decode("utf-8")
    if "expert.mine" in text:
        print("Ссылка «Мои рецензии» уже есть, ничего не меняю.")
        return 0
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    for i, line in enumerate(lines):
        if ANCHOR in line:
            # ссылка «Статус автора» стоит внутри {% if %}...{% endif %}: ставим нашу строку после этого блока
            j = i + 1
            while j < len(lines) and "{% endif %}" not in lines[j]:
                j += 1
            indent = line[: len(line) - len(line.lstrip())][:-2] if len(line) - len(line.lstrip()) >= 2 else ""
            lines.insert(j + 1, indent + LINK)
            break
    else:
        print("Не нашла ссылку «Статус автора» в base.html. Добавьте вручную в меню строку:")
        print(LINK)
        return 1
    with open(BASE, "wb") as f:
        f.write(newline.join(lines).encode("utf-8"))
    print("Готово: ссылка «Мои рецензии» добавлена в меню авторов.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
