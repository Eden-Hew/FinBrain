-- Allow customer identities created through protected Telegram onboarding.
-- The previous onboarding migration added the channel but did not expand the
-- origin constraints introduced by email-first customer profiles.

alter table public.customers
  drop constraint if exists customers_profile_origin_check;
alter table public.customers
  add constraint customers_profile_origin_check check (
    profile_origin in ('manual', 'einvoice', 'email', 'telegram')
  );

alter table public.customer_endpoints
  drop constraint if exists customer_endpoints_origin_check;
alter table public.customer_endpoints
  add constraint customer_endpoints_origin_check check (
    origin in (
      'manual',
      'inbound_email',
      'telegram_onboarding',
      'telegram_contact_share'
    )
  );
