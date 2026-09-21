# Accounts

*Internal policy reference. Covers the account itself — creating, editing, closing,
switching, logging in — and the account-security escalation. See
`cancellations_and_order_changes.md` for anything about a specific order, even where the
customer describes it as an account problem.*

## 1. Creating, editing, switching, closing an account

An account can be created with just an email address; no phone verification is required.
Editing saved details (name, saved addresses, marketing preferences) and closing an account
("premium account removal", "deleting my account" — a customer's own words for this do not
change what it is, client brief v3 §3) can both be self-served from account settings once
logged in, or actioned by support on request. Closing an account does not cancel or refund
any live order — that is a separate action under `cancellations_and_order_changes.md` if the
customer also wants it, and should be checked for explicitly rather than assumed.

"Switching accounts" (a customer with two email addresses wanting them merged, or wanting to
move their order history to a different login) has no automated self-service route; it is a
manual data-move support has to do directly, so set expectations that it takes longer than
an ordinary account edit.

## 2. Password and PIN reset

A standard password reset is self-service: a reset link is emailed to the address on file
and expires after 24 hours. Where the customer reports they no longer have access to that
email address at all, this stops being a plain forgotten password and becomes an identity
question — see §3.

**A plain forgotten password is administrative, not urgent** (client brief v3 §4): nothing
the customer has paid for is blocked by being logged out. Do not read the customer's
frustration at being locked out as urgency; it is not the same axis as consequence.

## 3. Registration and sign-up problems

Most sign-up failures are a validation error (email already registered, password not meeting
the site's complexity rule) rather than a system fault. Where a customer says they cannot
register at all because the email is "already in use" but they do not remember ever creating
an account, treat this as a password reset (§2) on the existing account rather than a new
sign-up, since account creation only needs an email address (§1) and duplicate emails are
therefore always a sign of an existing account, not a system bug.

## 4. Account security — suspected unauthorised access

This is different in kind from §2–3 and should never be handled by the ordinary self-service
reset. Signs to treat as account security rather than a plain lockout: the customer did not
lock themselves out and cannot explain why access changed, an order or a saved address
changed that they did not make, a charge they do not recognise, or a phishing email they are
reporting. **Do not send a standard password reset link and consider the matter closed** —
this category is escalated under the client brief (`account_security`, brief v3 §5) precisely
because the fix might not be a password reset at all (the account may still be compromised
after one), so the correct response from this system is to flag it for a human to
investigate, not to attempt a fix.
