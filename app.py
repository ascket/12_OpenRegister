from datetime import datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shiny import App, Inputs, Outputs, Session, reactive, render, ui

from database import SessionLocal, init_db
from models import Company, ImportRun
from openregister_service import (
    OpenRegisterError,
    OpenRegisterService,
)


# ============================================================
# Database initialization
# ============================================================

init_db()


# ============================================================
# Constants
# ============================================================

EMPTY_SEARCH_COLUMNS = [
    "OpenRegister ID",
    "Компания",
    "Улица",
    "PLZ",
    "Город",
    "Юридическая форма",
    "Register",
    "Register Nr.",
    "Описание деятельности",
]


EMPTY_DB_COLUMNS = [
    "ID",
    "Компания",
    "Улица",
    "PLZ",
    "Город",
    "Юридическая форма",
    "Источник",
    "Не контактировать",
    "Последнее обновление",
]


# ============================================================
# Helper functions
# ============================================================

def search_results_to_dataframe(
    companies: list[dict],
) -> pd.DataFrame:
    """
    Преобразует результаты OpenRegister
    в DataFrame для отображения в Shiny.
    """

    if not companies:
        return pd.DataFrame(
            columns=EMPTY_SEARCH_COLUMNS
        )

    rows = []

    for company in companies:
        rows.append(
            {
                "OpenRegister ID": company.get(
                    "openregister_id"
                ),
                "Компания": company.get("name"),
                "Улица": company.get("street"),
                "PLZ": company.get("postal_code"),
                "Город": company.get("city"),
                "Юридическая форма": company.get(
                    "legal_form"
                ),
                "Register": company.get(
                    "register_type"
                ),
                "Register Nr.": company.get(
                    "register_number"
                ),
                "Описание деятельности": company.get(
                    "purpose"
                ),
            }
        )

    return pd.DataFrame(rows)


def get_database_companies() -> pd.DataFrame:
    """
    Загружает все компании из SQLite.
    """

    db = SessionLocal()

    try:
        stmt = (
            select(Company)
            .order_by(Company.name)
        )

        companies = db.scalars(stmt).all()

        rows = []

        for company in companies:
            rows.append(
                {
                    "ID": company.id,
                    "Компания": company.name,
                    "Улица": company.street,
                    "PLZ": company.postal_code,
                    "Город": company.city,
                    "Юридическая форма": (
                        company.legal_form
                    ),
                    "Источник": company.source,
                    "Не контактировать": (
                        company.do_not_contact
                    ),
                    "Последнее обновление": (
                        company.source_retrieved_at
                    ),
                }
            )

        if not rows:
            return pd.DataFrame(
                columns=EMPTY_DB_COLUMNS
            )

        return pd.DataFrame(rows)

    finally:
        db.close()


def get_import_history() -> pd.DataFrame:
    """
    Возвращает историю импортов.
    """

    db = SessionLocal()

    try:
        stmt = (
            select(ImportRun)
            .order_by(
                ImportRun.id.desc()
            )
        )

        imports = db.scalars(stmt).all()

        rows = []

        for item in imports:
            rows.append(
                {
                    "ID": item.id,
                    "Источник": item.source,
                    "Город": item.city,
                    "PLZ": item.postal_code,
                    "WZ-код": item.industry_code,
                    "Keyword": (
                        item.purpose_keyword
                    ),
                    "Запрошено": (
                        item.requested_limit
                    ),
                    "Получено": (
                        item.received_count
                    ),
                    "Добавлено": (
                        item.inserted_count
                    ),
                    "Обновлено": (
                        item.updated_count
                    ),
                    "Дубликаты": (
                        item.duplicate_count
                    ),
                    "Пропущено": (
                        item.skipped_count
                    ),
                    "Начало": item.started_at,
                    "Завершено": item.finished_at,
                }
            )

        return pd.DataFrame(rows)

    finally:
        db.close()


def find_existing_company(
    db,
    data: dict,
) -> Company | None:
    """
    Поиск дубля.

    Приоритет:
    1. OpenRegister company_id
    2. name + street + postal_code + city
    """

    openregister_id = data.get(
        "openregister_id"
    )

    if openregister_id:
        stmt = select(
            Company
        ).where(
            Company.openregister_id
            == openregister_id
        )

        existing = db.scalar(stmt)

        if existing:
            return existing

    name = data.get("name")
    street = data.get("street")
    postal_code = data.get("postal_code")
    city = data.get("city")

    if (
        name
        and street
        and postal_code
        and city
    ):
        stmt = select(
            Company
        ).where(
            Company.name == name,
            Company.street == street,
            Company.postal_code == postal_code,
            Company.city == city,
        )

        existing = db.scalar(stmt)

        if existing:
            return existing

    return None


def update_existing_company(
    company: Company,
    data: dict,
):
    """
    Обновляет существующую компанию.

    Важно:
    do_not_contact НЕ изменяется.
    """

    company.name = (
        data.get("name")
        or company.name
    )

    company.street = (
        data.get("street")
        or company.street
    )

    company.postal_code = (
        data.get("postal_code")
        or company.postal_code
    )

    company.city = (
        data.get("city")
        or company.city
    )

    company.country = (
        data.get("country")
        or company.country
    )

    company.formatted_address = (
        data.get("formatted_address")
        or company.formatted_address
    )

    company.legal_form = (
        data.get("legal_form")
        or company.legal_form
    )

    company.register_type = (
        data.get("register_type")
        or company.register_type
    )

    company.register_number = (
        data.get("register_number")
        or company.register_number
    )

    company.register_court = (
        data.get("register_court")
        or company.register_court
    )

    company.purpose = (
        data.get("purpose")
        or company.purpose
    )

    company.active = data.get(
        "active",
        company.active,
    )

    company.source_retrieved_at = (
        datetime.utcnow()
    )


def save_search_results(
    companies: list[dict],
    *,
    requested_limit: int,
    city: str | None,
    postal_code: str | None,
    industry_code: str | None,
    purpose_keyword: str | None,
) -> dict:
    """
    Сохраняет уже найденные компании
    без повторного запроса к OpenRegister.
    """

    db = SessionLocal()

    inserted = 0
    updated = 0
    duplicates = 0
    skipped = 0

    try:
        for data in companies:

            name = data.get("name")

            if not name:
                skipped += 1
                continue

            existing = find_existing_company(
                db,
                data,
            )

            if existing:
                duplicates += 1

                update_existing_company(
                    existing,
                    data,
                )

                updated += 1
                continue

            company = Company(
                openregister_id=data.get(
                    "openregister_id"
                ),
                name=name,
                street=data.get("street"),
                postal_code=data.get(
                    "postal_code"
                ),
                city=data.get("city"),
                country=data.get("country"),
                formatted_address=data.get(
                    "formatted_address"
                ),
                legal_form=data.get(
                    "legal_form"
                ),
                register_type=data.get(
                    "register_type"
                ),
                register_number=data.get(
                    "register_number"
                ),
                register_court=data.get(
                    "register_court"
                ),
                purpose=data.get("purpose"),
                active=data.get(
                    "active",
                    True,
                ),
                source="openregister",
                source_retrieved_at=(
                    datetime.utcnow()
                ),
                do_not_contact=False,
            )

            db.add(company)

            inserted += 1

        import_run = ImportRun(
            source="openregister",
            city=city or None,
            postal_code=postal_code or None,
            industry_code=industry_code or None,
            purpose_keyword=(
                purpose_keyword or None
            ),
            requested_limit=requested_limit,
            received_count=len(companies),
            inserted_count=inserted,
            updated_count=updated,
            duplicate_count=duplicates,
            skipped_count=skipped,
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
        )

        db.add(import_run)

        db.commit()

        return {
            "received": len(companies),
            "inserted": inserted,
            "updated": updated,
            "duplicates": duplicates,
            "skipped": skipped,
        }

    except IntegrityError:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ============================================================
# UI
# ============================================================

search_page = ui.nav_panel(
    "Поиск компаний",

    ui.layout_sidebar(

        ui.sidebar(

            ui.h4("OpenRegister"),

            ui.input_text(
                "search_city",
                "Город",
                placeholder="Например: Hannover",
            ),

            ui.input_text(
                "search_postal_code",
                "PLZ",
                placeholder="Например: 30159",
            ),

            ui.input_text(
                "search_industry_code",
                "WZ2025 код отрасли",
                placeholder="Например: 56.11",
            ),

            ui.input_text(
                "search_purpose",
                "Ключевое слово деятельности",
                placeholder="Например: Photovoltaik",
            ),

            ui.input_select(
                "search_limit",
                "Количество компаний",
                choices={
                    "100": "100",
                    "200": "200",
                    "300": "300",
                },
                selected="100",
            ),

            ui.input_checkbox(
                "search_only_active",
                "Только активные компании",
                True,
            ),

            ui.hr(),

            ui.input_action_button(
                "search_button",
                "Найти компании",
                class_="btn-primary w-100",
            ),

            ui.br(),
            ui.br(),

            ui.input_action_button(
                "save_button",
                "Сохранить в SQLite",
                class_="btn-success w-100",
            ),

            width=330,
        ),

        ui.card(

            ui.card_header(
                "Результаты поиска"
            ),

            ui.layout_columns(

                ui.input_text(
                    "result_name_filter",
                    "Фильтр по названию",
                    placeholder="Название компании",
                ),

                ui.input_text(
                    "result_city_filter",
                    "Фильтр по городу",
                    placeholder="Город",
                ),

                ui.input_checkbox(
                    "result_full_address",
                    "Только с полным адресом",
                    False,
                ),

                col_widths=[4, 4, 4],
            ),

            ui.output_ui(
                "search_status"
            ),

            ui.output_data_frame(
                "search_table"
            ),
        ),
    ),
)


database_page = ui.nav_panel(
    "База компаний",

    ui.card(

        ui.card_header(
            "Сохранённые компании"
        ),

        ui.layout_columns(

            ui.input_text(
                "db_name_filter",
                "Компания",
                placeholder="Поиск...",
            ),

            ui.input_text(
                "db_city_filter",
                "Город",
                placeholder="Hannover",
            ),

            ui.input_text(
                "db_postal_filter",
                "PLZ",
                placeholder="30159",
            ),

            ui.input_checkbox(
                "db_contactable_only",
                "Исключить Do Not Contact",
                True,
            ),

            col_widths=[
                3,
                3,
                3,
                3,
            ],
        ),

        ui.output_ui(
            "database_status"
        ),

        ui.output_data_frame(
            "database_table"
        ),
    ),
)


history_page = ui.nav_panel(
    "История импортов",

    ui.card(
        ui.card_header(
            "OpenRegister imports"
        ),

        ui.output_data_frame(
            "import_history"
        ),
    ),
)


app_ui = ui.page_navbar(
    search_page,
    database_page,
    history_page,

    title="Company Finder",
    id="main_navigation",
    fillable=True,
)


# ============================================================
# Server
# ============================================================

def server(
    input: Inputs,
    output: Outputs,
    session: Session,
):

    # --------------------------------------------------------
    # Reactive state
    # --------------------------------------------------------

    search_results = reactive.value([])

    search_message = reactive.value(
        "Введите параметры поиска."
    )

    database_version = reactive.value(0)

    last_search_params = reactive.value({})

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    @reactive.effect
    @reactive.event(input.search_button)
    def perform_search():

        city = input.search_city().strip()
        postal_code = (
            input.search_postal_code().strip()
        )
        industry_code = (
            input.search_industry_code().strip()
        )
        purpose_keyword = (
            input.search_purpose().strip()
        )

        limit = int(
            input.search_limit()
        )

        # Требуем хотя бы один значимый фильтр,
        # чтобы случайно не запросить огромную
        # общую выборку.
        if not any(
            [
                city,
                postal_code,
                industry_code,
                purpose_keyword,
            ]
        ):
            search_message.set(
                "Укажите хотя бы город, PLZ, "
                "WZ-код или ключевое слово."
            )

            return

        search_message.set(
            "Выполняется запрос к OpenRegister..."
        )

        try:
            service = OpenRegisterService()

            companies = service.search(
                limit=limit,
                city=city or None,
                postal_code=(
                    postal_code or None
                ),
                industry_code=(
                    industry_code or None
                ),
                purpose_keyword=(
                    purpose_keyword or None
                ),
                only_active=(
                    input.search_only_active()
                ),
            )

            search_results.set(
                companies
            )

            last_search_params.set(
                {
                    "requested_limit": limit,
                    "city": city,
                    "postal_code": postal_code,
                    "industry_code": (
                        industry_code
                    ),
                    "purpose_keyword": (
                        purpose_keyword
                    ),
                }
            )

            full_address_count = sum(
                1
                for company in companies
                if (
                    company.get("street")
                    and company.get(
                        "postal_code"
                    )
                    and company.get("city")
                )
            )

            search_message.set(
                f"Найдено: {len(companies)}. "
                f"С полным адресом: "
                f"{full_address_count}."
            )

        except OpenRegisterError as exc:

            search_results.set([])

            search_message.set(
                f"Ошибка OpenRegister: {exc}"
            )

        except Exception as exc:

            search_results.set([])

            search_message.set(
                f"Ошибка: {exc}"
            )

    # --------------------------------------------------------
    # Filtered search result
    # --------------------------------------------------------

    @reactive.calc
    def filtered_search_dataframe():

        companies = search_results()

        df = search_results_to_dataframe(
            companies
        )

        if df.empty:
            return df

        name_filter = (
            input.result_name_filter()
            .strip()
            .lower()
        )

        city_filter = (
            input.result_city_filter()
            .strip()
            .lower()
        )

        if name_filter:
            df = df[
                df["Компания"]
                .fillna("")
                .str.lower()
                .str.contains(
                    name_filter,
                    regex=False,
                )
            ]

        if city_filter:
            df = df[
                df["Город"]
                .fillna("")
                .str.lower()
                .str.contains(
                    city_filter,
                    regex=False,
                )
            ]

        if input.result_full_address():

            df = df[
                df["Улица"].notna()
                & df["PLZ"].notna()
                & df["Город"].notna()
            ]

            df = df[
                (df["Улица"] != "")
                & (df["PLZ"] != "")
                & (df["Город"] != "")
            ]

        return df.reset_index(
            drop=True
        )

    # --------------------------------------------------------
    # Search status
    # --------------------------------------------------------

    @render.ui
    def search_status():

        return ui.div(
            ui.strong(
                search_message()
            ),
            style=(
                "padding: 10px 0 15px 0;"
            ),
        )

    # --------------------------------------------------------
    # Search table
    # --------------------------------------------------------

    @render.data_frame
    def search_table():

        return render.DataGrid(
            filtered_search_dataframe(),
            filters=True,
        )

    # --------------------------------------------------------
    # Save search results
    # --------------------------------------------------------

    @reactive.effect
    @reactive.event(input.save_button)
    def save_results():

        companies = search_results()

        if not companies:

            search_message.set(
                "Нет результатов для сохранения. "
                "Сначала выполните поиск."
            )

            return

        params = last_search_params()

        try:

            result = save_search_results(
                companies=companies,
                requested_limit=(
                    params.get(
                        "requested_limit",
                        len(companies),
                    )
                ),
                city=params.get("city"),
                postal_code=params.get(
                    "postal_code"
                ),
                industry_code=params.get(
                    "industry_code"
                ),
                purpose_keyword=params.get(
                    "purpose_keyword"
                ),
            )

            search_message.set(
                "Сохранение завершено. "
                f"Добавлено: "
                f"{result['inserted']}; "
                f"обновлено: "
                f"{result['updated']}; "
                f"дубликатов: "
                f"{result['duplicates']}; "
                f"пропущено: "
                f"{result['skipped']}."
            )

            # Инвалидируем вывод БД.
            database_version.set(
                database_version() + 1
            )

        except IntegrityError:

            search_message.set(
                "Ошибка SQLite: обнаружено "
                "нарушение уникальности."
            )

        except Exception as exc:

            search_message.set(
                f"Ошибка сохранения: {exc}"
            )

    # --------------------------------------------------------
    # Database data
    # --------------------------------------------------------

    @reactive.calc
    def database_dataframe():

        # Создаём dependency:
        database_version()

        df = get_database_companies()

        if df.empty:
            return df

        name_filter = (
            input.db_name_filter()
            .strip()
            .lower()
        )

        city_filter = (
            input.db_city_filter()
            .strip()
            .lower()
        )

        postal_filter = (
            input.db_postal_filter()
            .strip()
        )

        if name_filter:
            df = df[
                df["Компания"]
                .fillna("")
                .str.lower()
                .str.contains(
                    name_filter,
                    regex=False,
                )
            ]

        if city_filter:
            df = df[
                df["Город"]
                .fillna("")
                .str.lower()
                .str.contains(
                    city_filter,
                    regex=False,
                )
            ]

        if postal_filter:
            df = df[
                df["PLZ"]
                .fillna("")
                .astype(str)
                .str.startswith(
                    postal_filter
                )
            ]

        if input.db_contactable_only():

            df = df[
                df["Не контактировать"]
                == False  # noqa: E712
            ]

        return df.reset_index(
            drop=True
        )

    # --------------------------------------------------------
    # Database table
    # --------------------------------------------------------

    @render.data_frame
    def database_table():

        return render.DataGrid(
            database_dataframe(),
            filters=True,
        )

    # --------------------------------------------------------
    # Database statistics
    # --------------------------------------------------------

    @render.ui
    def database_status():

        df = database_dataframe()

        count = len(df)

        if count == 0:
            return ui.div(
                "В базе пока нет компаний.",
                style="padding: 10px 0;",
            )

        full_address = 0

        if all(
            column in df.columns
            for column in [
                "Улица",
                "PLZ",
                "Город",
            ]
        ):
            full_address = (
                df["Улица"].notna()
                & df["PLZ"].notna()
                & df["Город"].notna()
            ).sum()

        return ui.div(
            ui.strong(
                f"Показано компаний: {count}"
            ),
            " | ",
            f"С полным адресом: "
            f"{full_address}",
            style="padding: 10px 0;",
        )

    # --------------------------------------------------------
    # Import history
    # --------------------------------------------------------

    @render.data_frame
    def import_history():

        database_version()

        df = get_import_history()

        return render.DataGrid(
            df,
            filters=True,
        )


# ============================================================
# App
# ============================================================

app = App(
    app_ui,
    server,
)
