# Kolbo Video — Preview HTTPS 4.4.9
Fail-closed compatibility probe for existing Android 4.4.9 APK. This endpoint is **not** the Kolbo Mesh production API.
This instance cannot store uploaded photographs, accept production jobs, or generate AI.
GET /v1/app-config returns api_contract 449; GET /studio clearly states Preview Only.
All POST/PUT/PATCH/DELETE operations reject with 503. No credentials or tokens are accepted.
Render Free has no durable filesystem: never disable this restriction until an externally durable database and media object store are configured and tested.
No chargeable GPU is launched; note Render workspace overages must still be independently controlled.
