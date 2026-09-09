"""Safe, actionable errors; never expose provider payloads, credentials or tracebacks."""
def public_assistant_error(error):
    status = getattr(error, "status_code", None)
    if status == 429:
        return 429, "AI Assist has reached the free provider’s capacity limit. Please try again later; scanner data remains available."
    if status in (401, 403):
        return 503, "AI Assist’s provider access needs an operator update. Scanner data remains available."
    if status == 404 or (isinstance(error, RuntimeError) and "configured free model" in str(error)):
        return 503, "AI Assist’s free model is unavailable and needs an operator update. Scanner data remains available."
    if isinstance(error, RuntimeError) and "OPENROUTER_API_KEY" in str(error):
        return 503, "AI Assist needs a free-provider API key configured by the operator. Scanner data remains available."
    return 503, "AI Assist is temporarily unavailable. Your scanner data remains available; please try again later."
