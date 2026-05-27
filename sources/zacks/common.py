"""Shared Zacks constants."""
DOMAIN = "zacks.com"

# Imperva/Incapsula challenge cookies — bound to the original browser
# fingerprint and won't transfer to a fresh Chromium. Skip them so Imperva
# re-issues the challenge naturally.
SKIP_COOKIES = ("reese84", "incap_ses_", "visid_incap_", "nlbi_")
