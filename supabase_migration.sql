-- Migration: Add Stripe support to profiles table

ALTER TABLE profiles 
ADD COLUMN IF NOT EXISTS stripe_customer_id text,
ADD COLUMN IF NOT EXISTS stripe_subscription_id text;

-- Optional: add an index on stripe_customer_id for faster lookups during webhooks
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_customer_id ON profiles(stripe_customer_id);
