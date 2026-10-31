# Spec Delta

## ADDED Requirements

### Requirement: Reload keeps the signed-in shopper
A reload of a signed-in shopper page SHALL show that same shopper, including the name and the composer, while the server session still exists. The reload SHALL NOT ask for the password and SHALL NOT submit a new login. The remembered record SHALL NOT contain the password.

#### Scenario: Reload shows the shop
- **WHEN** the shopper is signed in and reloads the page, and the server session still exists
- **THEN** the page shows that shopper and the composer, and does not show the login form

#### Scenario: Reload does not start a new login
- **WHEN** the shopper reloads a signed-in page
- **THEN** the page does not submit email and password

#### Scenario: The password is not remembered
- **WHEN** the shopper signs in
- **THEN** the tab's remembered record does not contain the password

### Requirement: A missing server session shows login
The shopper page SHALL show the login form and SHALL forget the remembered shopper when the server reports that shopper is not signed in.

#### Scenario: Server session is gone
- **WHEN** the page loads with a remembered shopper and the server reports that shopper is not signed in
- **THEN** the page shows the login form and does not keep that remembered shopper

### Requirement: Sign out ends the session now
Sign out SHALL drop the server session, flush the transcript to Mem0 once, forget the remembered shopper, and the following page load SHALL show the login form.

#### Scenario: Sign out returns to login
- **WHEN** the shopper chooses Sign out
- **THEN** the server session is gone, the transcript was flushed once, and the next load shows the login form

### Requirement: Tab close flushes only if the tab does not return
Leaving the page SHALL NOT drop the server session before a reload of that same tab can keep it. A leave that no reload confirms SHALL drop the server session and SHALL flush the transcript to Mem0 once. A frozen page and an open microphone SHALL NOT schedule that flush.

#### Scenario: Reload cancels the flush
- **WHEN** the shopper reloads and the new page confirms the server session
- **THEN** the server session is still present and that leave does not flush Mem0

#### Scenario: Closed tab flushes
- **WHEN** the shopper leaves the page and no reload confirms the session
- **THEN** the server session is dropped and the transcript is flushed to Mem0 once

#### Scenario: Frozen page does not schedule a flush
- **WHEN** the page is hidden and kept for later restore without a new document
- **THEN** no flush is scheduled

#### Scenario: Open microphone does not schedule a flush
- **WHEN** the microphone is on and the page hides
- **THEN** no flush is scheduled
