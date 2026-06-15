import argparse
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.utils.auth_utils import validate_password_rules


def create_admin(email: str, full_name: str, password: str) -> None:
    normalized_email = email.lower().strip()

    with SessionLocal() as db:
        existing_user = db.scalar(select(User).where(User.email == normalized_email))
        if existing_user:
            raise SystemExit(f'User already exists: {normalized_email}')

        admin_role = db.scalar(select(Role).where(Role.name == 'Admin'))
        if not admin_role:
            raise SystemExit('Admin role not found. Run alembic upgrade head first.')

        db.add(
            User(
                email=normalized_email,
                full_name=full_name.strip(),
                password_hash=hash_password(password),
                role_id=admin_role.id,
                is_active=True,
                must_reset_password=False,
            )
        )
        db.commit()

    print(f'Admin user created: {normalized_email}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Create the first admin user.')
    parser.add_argument('--email', required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()

    password = getpass('Password: ')
    confirm_password = getpass('Confirm password: ')
    if password != confirm_password:
        raise SystemExit('Passwords do not match.')

    password_error = validate_password_rules(password)
    if password_error:
        raise SystemExit(password_error)

    create_admin(email=args.email, full_name=args.name, password=password)


if __name__ == '__main__':
    main()
