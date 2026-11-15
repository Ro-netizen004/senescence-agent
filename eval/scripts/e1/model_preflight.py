"""Non-scientific model-access check; never persist credentials or API bodies."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from google import genai
from google.genai import types

OUT=Path(__file__).resolve().parents[3]/"eval/results/v2/e1/e1_v2_1_20261022_01"

def main():
    path=OUT/"MODEL_ACCESS_PREFLIGHT.json"
    if path.exists():
        raise FileExistsError(path)
    result={"timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "model":"gemini-3.5-flash","non_scientific":True,
            "api_key_present":bool(os.getenv("GEMINI_API_KEY")),
            "call_count":0,"authentication_succeeded":False,
            "scientific_data_sent":False,"retry_count":0}
    if os.getenv("GEMINI_MODEL")!="gemini-3.5-flash":
        result["status"]="MODEL_CONFIGURATION_MISMATCH"
    elif not result["api_key_present"]:
        result["status"]="CREDENTIAL_ABSENT"
    else:
        client=genai.Client(api_key=os.getenv("GEMINI_API_KEY"),
                            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))
        try:
            result["call_count"]=1
            response=client.models.get(model=result["model"])
            result["authentication_succeeded"]=bool(response)
            result["status"]="PASS" if response else "EMPTY_RESPONSE"
        except Exception as exc:
            result["status"]="PREFLIGHT_BLOCKED"
            result["error_type"]=type(exc).__name__
            code=getattr(exc,"code",None)
            result["api_error_code"]=code if isinstance(code,int) else None
            # Whitelist enum names only; never serialize exception text or body.
            status=getattr(exc,"status",None)
            result["api_error_status"]=status if status in {
                "INVALID_ARGUMENT","UNAUTHENTICATED","PERMISSION_DENIED",
                "NOT_FOUND","RESOURCE_EXHAUSTED","UNAVAILABLE","INTERNAL"} else None
        finally:
            client.close()
    with path.open("x") as handle:
        json.dump(result,handle,indent=2)
        handle.write("\n")
    print(json.dumps(result))
    if result["status"]!="PASS":
        raise SystemExit(1)

if __name__=="__main__":
    main()
