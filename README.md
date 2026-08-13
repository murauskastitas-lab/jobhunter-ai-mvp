# JobHunter AI MVP v1

Upload CV -> AI profile check -> choose location/remote -> discover public job opportunities -> AI match scoring -> personalized application drafts.

This MVP uses public job APIs (Arbeitnow and Remotive) rather than scraping protected websites or bypassing CAPTCHAs. It intentionally leaves bulk unsolicited email automation disabled; application drafts are generated for review. Add authentication, usage limits, privacy controls, provider-specific application integrations, and compliant outreach before production scale.

Railway variables: OPENAI_API_KEY and optionally OPENAI_MODEL=gpt-5-mini.
