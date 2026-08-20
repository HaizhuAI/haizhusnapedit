"""SnapEdit official cloud provider (no local models).

Uses the same auth chain recovered from the SnapEdit APK:
  * ACCESS_TOKEN   = locally-minted HS256 JWT signed with the app's api_key secret
  * X-INTEGRITY    = integrity-service/v1/verify token
Both sent as "Bearer <token>" on every request to be-prod-1.snapedit.app.
All AI inference happens on SnapEdit's cloud (BytePlus); this host only
proxies requests and does light compositing (enhance faces / sky / passport).
"""
