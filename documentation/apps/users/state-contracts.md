# users state and choice contracts

## User

is_active controls account usability. is_staff controls Django/Wagtail operator access. is_superuser is the Django permission bypass flag.

email_verified and phone_number_verified indicate verification state; they do not authorize a contact mutation.

theme is light/dark presentation preference.

## Receipt

Payment status is NOT_PAYED, PAYED or CANCELED. Receipt state and User.balance are related accounting state but not interchangeable; change_balance() performs the transactional update.
