export const LOGIN_TEXT = {
  brand: 'Mail Management',
  eyebrow: 'Secure Mail Desk',
  title: 'Welcome back',
  subtitle: 'Sign in with your registered email address to manage your mail workflow.',
  emailLabel: 'Email ID',
  emailPlaceholder: 'name@company.com',
  passwordLabel: 'Password',
  passwordPlaceholder: 'Enter your password',
  forgotPassword: 'Forgot password?',
  submit: 'Sign in',
  submitting: 'Signing in...',
  helper: 'Use your organization credentials to continue.',
  defaultError: 'Unable to sign in. Please check your email and password.',
  sideTitle: 'Organized mail operations, without the clutter.',
  sideDescription:
    'Track requests, coordinate teams, and keep every message moving through the right workflow.',
}

export const FORGOT_PASSWORD_TEXT = {
  brand: LOGIN_TEXT.brand,
  eyebrow: 'Password Recovery',
  title: 'Reset your password',
  subtitle:
    'Enter your email ID and we will send instructions to help you get back into your account.',
  emailLabel: 'Email ID',
  emailPlaceholder: LOGIN_TEXT.emailPlaceholder,
  submit: 'Send reset link',
  submitting: 'Sending...',
  backToLogin: 'Back to login',
  helper: 'Check your inbox and spam folder after requesting the reset link.',
  defaultError: 'Unable to send reset link. Please try again.',
  sideTitle: 'Access restored with a clean reset flow.',
  sideDescription:
    'A verified reset link helps protect your account while getting you back to work quickly.',
}

export const RESET_PASSWORD_TEXT = {
  brand: LOGIN_TEXT.brand,
  eyebrow: 'Password Reset',
  title: 'Create a new password',
  subtitle: 'Choose a new password for your Mail Management account.',
  passwordLabel: 'New password',
  passwordPlaceholder: 'Enter new password',
  confirmPasswordLabel: 'Confirm password',
  confirmPasswordPlaceholder: 'Re-enter new password',
  submit: 'Reset password',
  submitting: 'Resetting...',
  backToLogin: 'Back to login',
  helper: 'Use at least 6 characters with one letter and one number.',
  missingTokenError: 'This reset link is missing a token. Please request a new link.',
  passwordMismatchError: 'Passwords do not match.',
  defaultError: 'Unable to reset password. Please request a new link and try again.',
  success: 'Password reset successfully. You can now sign in.',
  sideTitle: 'A fresh password keeps the account protected.',
  sideDescription: 'Your old sessions are revoked after the reset is completed.',
}
