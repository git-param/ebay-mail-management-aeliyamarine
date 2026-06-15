import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


class EmailService:
    def build_password_reset_link(self, token: str) -> str:
        settings = get_settings()
        return f'{settings.frontend_url.rstrip("/")}/reset-password?token={token}'

    def send_password_reset_email(self, *, email: str, reset_link: str) -> None:
        settings = get_settings()
        if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
            print(f'Password reset email queued for {email}: {reset_link}')
            return

        from_email = settings.smtp_from_email or settings.smtp_username
        message = EmailMessage()
        message['Subject'] = 'Reset your Mail Management password'
        message['From'] = from_email
        message['To'] = email
        message.set_content(
            '\n'.join(
                [
                    'We received a request to reset your Mail Management password.',
                    '',
                    f'Open this link to set a new password: {reset_link}',
                    '',
                    'If you did not request this, you can ignore this email.',
                ]
            )
        )

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
