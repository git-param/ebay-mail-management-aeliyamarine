from app.core.config import get_settings


class EmailService:
    def build_password_reset_link(self, token: str) -> str:
        settings = get_settings()
        return f'{settings.frontend_url.rstrip("/")}/reset-password?token={token}'

    def send_password_reset_email(self, *, email: str, reset_link: str) -> None:
        # Placeholder for SMTP/provider integration. Keep the API behavior stable now,
        # and wire the actual email provider without changing auth routes later.
        print(f'Password reset email queued for {email}: {reset_link}')
