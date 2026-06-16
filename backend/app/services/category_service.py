import re
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category, CategoryKeyword

OTHER_CATEGORY_NAME = 'Other'


def normalize_keyword(keyword: str) -> str:
    return re.sub(r'\s+', ' ', keyword.strip().lower())


def validate_unique_keywords(keywords: list[str]) -> list[str]:
    normalized_seen = set()
    cleaned_keywords = []

    for keyword in keywords:
        normalized = normalize_keyword(keyword)
        if not normalized:
            continue
        if normalized in normalized_seen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Duplicate keywords are not allowed')
        normalized_seen.add(normalized)
        cleaned_keywords.append(keyword.strip())

    return cleaned_keywords


def get_category_or_404(db: Session, category_id: UUID) -> Category:
    category = db.scalar(
        select(Category)
        .options(selectinload(Category.keywords))
        .where(Category.id == category_id)
    )
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Category not found')
    return category


def ensure_category_name_available(db: Session, name: str, category_id: UUID | None = None) -> None:
    statement = select(Category).where(func.lower(Category.name) == name.strip().lower())
    if category_id:
        statement = statement.where(Category.id != category_id)

    if db.scalar(statement):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='A category with this name already exists')


def ensure_keyword_available(
    db: Session,
    category_id: UUID,
    keyword: str,
    keyword_id: UUID | None = None,
) -> None:
    statement = (
        select(CategoryKeyword)
        .where(CategoryKeyword.category_id == category_id)
        .where(func.lower(CategoryKeyword.keyword) == normalize_keyword(keyword))
    )
    if keyword_id:
        statement = statement.where(CategoryKeyword.id != keyword_id)

    if db.scalar(statement):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Duplicate keywords are not allowed')


def categorize_message(db: Session, message_text: str) -> UUID | None:
    text = f' {normalize_keyword(message_text)} '
    categories = db.scalars(
        select(Category)
        .options(selectinload(Category.keywords))
        .where(Category.is_active.is_(True))
        .order_by(Category.created_at.asc(), Category.id.asc())
    ).all()

    other_category_id = None
    for category in categories:
        if category.name.lower() == OTHER_CATEGORY_NAME.lower():
            other_category_id = category.id

        for keyword in category.keywords:
            normalized_keyword = normalize_keyword(keyword.keyword)
            if normalized_keyword and normalized_keyword in text:
                return category.id

    return other_category_id
