import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Company, ImportRun


load_dotenv()


OPENREGISTER_API_URL = (
    "https://api.openregister.de/v1/search/company"
)


@dataclass
class ImportResult:
    requested: int = 0
    received: int = 0
    inserted: int = 0
    updated: int = 0
    duplicates: int = 0
    skipped: int = 0


class OpenRegisterError(Exception):
    """Ошибка взаимодействия с OpenRegister API."""


class OpenRegisterService:

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 30,
    ):
        self.api_key = (
            api_key
            or os.getenv("OPENREGISTER_API_KEY")
        )

        if not self.api_key:
            raise RuntimeError(
                "OPENREGISTER_API_KEY не найден. "
                "Добавьте ключ в файл .env."
            )

        self.timeout = timeout

        self.session = requests.Session()

        self.session.headers.update(
            {
                "Authorization": (
                    f"Bearer {self.api_key}"
                ),
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def search(
        self,
        limit: int,
        city: str | None = None,
        postal_code: str | None = None,
        industry_code: str | None = None,
        purpose_keyword: str | None = None,
        only_active: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Получить компании из OpenRegister.

        limit:
            100, 200, 300 или другое положительное число.

        city:
            Например "Hannover".

        postal_code:
            Например "30159".

        industry_code:
            WZ2025-код отрасли.

        purpose_keyword:
            Поиск слова внутри Unternehmensgegenstand / purpose.

        Возвращает сырые normalized dict.
        """

        if limit <= 0:
            raise ValueError(
                "limit должен быть больше нуля"
            )

        filters = self._build_filters(
            city=city,
            postal_code=postal_code,
            industry_code=industry_code,
            purpose_keyword=purpose_keyword,
            only_active=only_active,
        )

        companies: list[dict[str, Any]] = []

        page = 1

        # Используем страницы до 100 результатов.
        per_page = min(limit, 100)

        while len(companies) < limit:

            remaining = limit - len(companies)

            current_page_size = min(
                remaining,
                per_page,
            )

            payload = {
                "filters": filters,
                "pagination": {
                    "page": page,
                    "per_page": current_page_size,
                },
            }

            data = self._request(payload)

            raw_results = data.get(
                "results",
                [],
            )

            if not raw_results:
                break

            for raw_company in raw_results:

                company = self._normalize_company(
                    raw_company
                )

                companies.append(company)

                if len(companies) >= limit:
                    break

            pagination = data.get(
                "pagination",
                {},
            )

            total_pages = pagination.get(
                "total_pages"
            )

            if (
                total_pages is not None
                and page >= total_pages
            ):
                break

            # Защита от бесконечного цикла,
            # если API перестанет возвращать pagination.
            if len(raw_results) < current_page_size:
                break

            page += 1

        return companies[:limit]

    def import_companies(
        self,
        limit: int,
        city: str | None = None,
        postal_code: str | None = None,
        industry_code: str | None = None,
        purpose_keyword: str | None = None,
        update_existing: bool = True,
    ) -> ImportResult:
        """
        Получить компании из OpenRegister
        и сохранить их в SQLite.
        """

        result = ImportResult(
            requested=limit
        )

        db = SessionLocal()

        import_run = ImportRun(
            city=city,
            postal_code=postal_code,
            industry_code=industry_code,
            purpose_keyword=purpose_keyword,
            requested_limit=limit,
        )

        db.add(import_run)
        db.commit()
        db.refresh(import_run)

        try:
            companies = self.search(
                limit=limit,
                city=city,
                postal_code=postal_code,
                industry_code=industry_code,
                purpose_keyword=purpose_keyword,
            )

            result.received = len(companies)

            for data in companies:

                # Без названия компания нам практически
                # бесполезна.
                if not data["name"]:
                    result.skipped += 1
                    continue

                existing = self._find_existing(
                    db=db,
                    data=data,
                )

                if existing:

                    result.duplicates += 1

                    if update_existing:
                        self._update_company(
                            company=existing,
                            data=data,
                        )

                        result.updated += 1

                    continue

                company = Company(
                    openregister_id=(
                        data["openregister_id"]
                    ),
                    name=data["name"],
                    street=data["street"],
                    postal_code=(
                        data["postal_code"]
                    ),
                    city=data["city"],
                    country=data["country"],
                    formatted_address=(
                        data["formatted_address"]
                    ),
                    legal_form=(
                        data["legal_form"]
                    ),
                    register_type=(
                        data["register_type"]
                    ),
                    register_number=(
                        data["register_number"]
                    ),
                    register_court=(
                        data["register_court"]
                    ),
                    purpose=data["purpose"],
                    active=data["active"],
                    source="openregister",
                    source_retrieved_at=(
                        datetime.utcnow()
                    ),
                )

                db.add(company)

                result.inserted += 1

            import_run.received_count = (
                result.received
            )

            import_run.inserted_count = (
                result.inserted
            )

            import_run.updated_count = (
                result.updated
            )

            import_run.duplicate_count = (
                result.duplicates
            )

            import_run.skipped_count = (
                result.skipped
            )

            import_run.finished_at = (
                datetime.utcnow()
            )

            db.commit()

            return result

        except Exception:

            db.rollback()

            # Историю неудачного импорта в следующей
            # версии можно расширить полями status/error.
            raise

        finally:
            db.close()

    # ---------------------------------------------------------
    # Filters
    # ---------------------------------------------------------

    def _build_filters(
        self,
        city: str | None,
        postal_code: str | None,
        industry_code: str | None,
        purpose_keyword: str | None,
        only_active: bool,
    ) -> list[dict]:

        filters: list[dict] = []

        if only_active:
            filters.append(
                {
                    "field": "status",
                    "value": "active",
                }
            )

        if city:
            filters.append(
                {
                    "field": "city",
                    "value": city.strip(),
                }
            )

        if postal_code:
            filters.append(
                {
                    "field": "zip",
                    "value": postal_code.strip(),
                }
            )

        if industry_code:
            filters.append(
                {
                    "field": "industry_codes",
                    "value": (
                        industry_code.strip()
                    ),
                }
            )

        if purpose_keyword:
            filters.append(
                {
                    "field": "purpose",
                    "keywords": [
                        purpose_keyword.strip()
                    ],
                }
            )

        return filters

    # ---------------------------------------------------------
    # HTTP
    # ---------------------------------------------------------

    def _request(
        self,
        payload: dict,
    ) -> dict:

        try:
            response = self.session.post(
                OPENREGISTER_API_URL,
                json=payload,
                timeout=self.timeout,
            )

        except requests.RequestException as exc:

            raise OpenRegisterError(
                f"Ошибка соединения с OpenRegister: "
                f"{exc}"
            ) from exc

        if response.status_code == 401:
            raise OpenRegisterError(
                "OpenRegister отклонил API key."
            )

        if response.status_code == 429:
            raise OpenRegisterError(
                "Достигнут лимит запросов "
                "OpenRegister API."
            )

        if not response.ok:

            raise OpenRegisterError(
                "OpenRegister API error: "
                f"{response.status_code} "
                f"{response.text}"
            )

        try:
            return response.json()

        except ValueError as exc:

            raise OpenRegisterError(
                "OpenRegister вернул "
                "некорректный JSON."
            ) from exc

    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_company(
        raw: dict,
    ) -> dict[str, Any]:

        address = raw.get(
            "address"
        ) or {}

        return {
            "openregister_id": (
                raw.get("company_id")
            ),
            "name": (
                OpenRegisterService
                ._clean_text(
                    raw.get("name")
                )
            ),
            "street": (
                OpenRegisterService
                ._clean_text(
                    address.get("street")
                )
            ),
            "postal_code": (
                OpenRegisterService
                ._clean_text(
                    address.get(
                        "postal_code"
                    )
                )
            ),
            "city": (
                OpenRegisterService
                ._clean_text(
                    address.get("city")
                )
            ),
            "country": (
                OpenRegisterService
                ._clean_text(
                    address.get("country")
                    or raw.get("country")
                )
            ),
            "formatted_address": (
                OpenRegisterService
                ._clean_text(
                    address.get(
                        "formatted_value"
                    )
                )
            ),
            "legal_form": (
                raw.get("legal_form")
            ),
            "register_type": (
                raw.get("register_type")
            ),
            "register_number": (
                raw.get("register_number")
            ),
            "register_court": (
                raw.get("register_court")
            ),
            "purpose": (
                OpenRegisterService
                ._clean_text(
                    raw.get("purpose")
                )
            ),
            "active": (
                bool(
                    raw.get(
                        "active",
                        True,
                    )
                )
            ),
        }

    @staticmethod
    def _clean_text(
        value: Any,
    ) -> str | None:

        if value is None:
            return None

        value = str(value).strip()

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value or None

    # ---------------------------------------------------------
    # Duplicate detection
    # ---------------------------------------------------------

    def _find_existing(
        self,
        db: Session,
        data: dict,
    ) -> Company | None:

        openregister_id = data.get(
            "openregister_id"
        )

        # 1. Самый надёжный вариант:
        # OpenRegister company_id.
        if openregister_id:

            stmt = select(
                Company
            ).where(
                Company.openregister_id
                == openregister_id
            )

            company = db.scalar(stmt)

            if company:
                return company

        # 2. Резервный поиск:
        # название + улица + PLZ + город.
        if (
            data.get("name")
            and data.get("street")
            and data.get("postal_code")
            and data.get("city")
        ):

            stmt = select(
                Company
            ).where(
                Company.name
                == data["name"],
                Company.street
                == data["street"],
                Company.postal_code
                == data["postal_code"],
                Company.city
                == data["city"],
            )

            company = db.scalar(stmt)

            if company:
                return company

        return None

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    @staticmethod
    def _update_company(
        company: Company,
        data: dict,
    ) -> None:

        """
        Обновляем данные OpenRegister,
        но НЕ меняем do_not_contact.

        Это важно: повторный импорт никогда
        не должен случайно вернуть компанию,
        отказавшуюся от рекламы, обратно
        в mailing list.
        """

        company.name = (
            data["name"]
            or company.name
        )

        company.street = (
            data["street"]
            or company.street
        )

        company.postal_code = (
            data["postal_code"]
            or company.postal_code
        )

        company.city = (
            data["city"]
            or company.city
        )

        company.country = (
            data["country"]
            or company.country
        )

        company.formatted_address = (
            data["formatted_address"]
            or company.formatted_address
        )

        company.legal_form = (
            data["legal_form"]
            or company.legal_form
        )

        company.register_type = (
            data["register_type"]
            or company.register_type
        )

        company.register_number = (
            data["register_number"]
            or company.register_number
        )

        company.register_court = (
            data["register_court"]
            or company.register_court
        )

        company.purpose = (
            data["purpose"]
            or company.purpose
        )

        company.active = data["active"]

        company.source_retrieved_at = (
            datetime.utcnow()
        )
