PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_LENGTH = 30


class AuthMessages:
    INVALID_LOGIN = 'Invalid email or password'
    INACTIVE_USER = 'User account is disabled'
    INVALID_REFRESH_TOKEN = 'Invalid refresh token'
    INVALID_RESET_TOKEN = 'Invalid or expired reset token'
    MISSING_AUTH_TOKEN = 'Missing authorization token'
    INVALID_AUTH_TOKEN = 'Invalid authorization token'

    LOGOUT_SUCCESS = 'Logged out successfully'
    PASSWORD_RESET_SENT = 'If that email exists, a password reset link has been sent'
    PASSWORD_RESET_SUCCESS = 'Password has been reset successfully'

    PASSWORD_TOO_SHORT = f'Password must be at least {PASSWORD_MIN_LENGTH} characters.'
    PASSWORD_TOO_LONG = f'Password cannot be more than {PASSWORD_MAX_LENGTH} characters.'
    PASSWORD_REUSED = 'New password cannot be the same as your current password.'
    PASSWORD_NEEDS_LETTER = 'Password must include at least one letter.'
    PASSWORD_NEEDS_NUMBER = 'Password must include at least one number.'


class AuditActions:
    LOGIN_FAILURE = 'LOGIN_FAILURE'
    LOGIN_BLOCKED_INACTIVE_USER = 'LOGIN_BLOCKED_INACTIVE_USER'
    LOGIN_SUCCESS = 'LOGIN_SUCCESS'
    LOGOUT = 'LOGOUT'
    PASSWORD_RESET_REQUESTED = 'PASSWORD_RESET_REQUESTED'
    PASSWORD_RESET_COMPLETED = 'PASSWORD_RESET_COMPLETED'
