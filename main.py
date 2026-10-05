from database import init_db
from openregister_service import (
    OpenRegisterError,
    OpenRegisterService,
)


def main():

    init_db()

    service = OpenRegisterService()

    try:

        result = service.import_companies(
            limit=100,
            city="Hannover",

            # Здесь задаём WZ2025-код
            # нужной отрасли:
            industry_code="56.11",

            # Или вместо industry_code
            # можно использовать:
            # purpose_keyword="Solar",
        )

    except OpenRegisterError as exc:

        print(
            f"Ошибка OpenRegister: {exc}"
        )

        return

    print()
    print("IMPORT FINISHED")
    print("---------------------------")
    print(
        f"Запрошено:       "
        f"{result.requested}"
    )
    print(
        f"Получено API:    "
        f"{result.received}"
    )
    print(
        f"Добавлено:       "
        f"{result.inserted}"
    )
    print(
        f"Обновлено:       "
        f"{result.updated}"
    )
    print(
        f"Дубликатов:      "
        f"{result.duplicates}"
    )
    print(
        f"Пропущено:       "
        f"{result.skipped}"
    )


if __name__ == "__main__":
    main()
