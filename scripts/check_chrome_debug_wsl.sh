#!/usr/bin/env bash
# Fast WSL-side discovery. Never reads /etc/resolv.conf.
# Probe order:
#   1. 127.0.0.1:9222 (mirrored mode)
#   2. explicit CRC_CDP_URL
#   3. Windows NAT gateway:9223 (portproxy fallback)

set -uo pipefail

CHROME_PORT="${CRC_CHROME_PORT:-9222}"
PROXY_PORT="${CRC_PROXY_PORT:-9223}"
CONNECT_TIMEOUT="${CRC_CONNECT_TIMEOUT:-1}"
MAX_TIME="${CRC_MAX_TIME:-2}"
SKILL_PATH="${CRC_SKILL_PATH:-/home/hp/.hermes-shared/skills/devops/chrome-cdp-reader/SKILL.md}"
MODE="human"

case "${1:-}" in
  --url) MODE="url" ;;
  --export) MODE="export" ;;
  --json) MODE="json" ;;
  "") ;;
  *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
esac

command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

network_mode="unknown"
if command -v wslinfo >/dev/null 2>&1; then
  network_mode="$(timeout 2s wslinfo --networking-mode 2>/dev/null | tr -d '\r' || true)"
  [[ -n "$network_mode" ]] || network_mode="unknown"
fi

windows_user="$(timeout 3s cmd.exe /d /c echo %USERNAME% 2>/dev/null | tr -d '\r' | tail -n 1)"
if [[ -z "$windows_user" || "$windows_user" == "%USERNAME%" ]]; then
  windows_user="${WIN_USER:-}"
fi

state_file=""
if [[ -n "$windows_user" ]]; then
  state_file="/mnt/c/Users/$windows_user/AppData/Local/Temp/chrome-cdp-reader/state.json"
fi

gateway="$(ip -4 route show default 2>/dev/null | awk 'NR==1 {print $3}')"

declare -a candidates=()
[[ -n "${CRC_CDP_URL:-}" ]] && candidates+=("${CRC_CDP_URL%/}")
candidates+=("http://127.0.0.1:$CHROME_PORT")
[[ -n "$gateway" ]] && candidates+=("http://$gateway:$PROXY_PORT")

declare -A seen=()
declare -a unique=()
for endpoint in "${candidates[@]}"; do
  [[ -n "$endpoint" ]] || continue
  if [[ -z "${seen[$endpoint]+x}" ]]; then
    seen["$endpoint"]=1
    unique+=("$endpoint")
  fi
done

probe() {
  local endpoint="$1"
  local body
  body="$(curl --fail --silent --show-error --noproxy '*' \
    --connect-timeout "$CONNECT_TIMEOUT" --max-time "$MAX_TIME" \
    "$endpoint/json/version" 2>/dev/null)" || return 1

  python3 - "$body" <<'PY'
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    raise SystemExit(1)
if not data.get("Browser") or not data.get("webSocketDebuggerUrl"):
    raise SystemExit(1)
PY
}

selected=""
for endpoint in "${unique[@]}"; do
  if probe "$endpoint"; then selected="$endpoint"; break; fi
done

if [[ -z "$selected" ]]; then
  echo "Chrome CDP is not reachable." >&2
  echo "Networking mode: $network_mode" >&2
  echo "Checked:" >&2
  printf '  - %s\n' "${unique[@]}" >&2
  echo "Expected skill: $SKILL_PATH" >&2
  echo "Run launch_debug_chrome.ps1; use mirrored mode or install the 9223 NAT portproxy." >&2
  exit 1
fi

version_json="$(curl --fail --silent --noproxy '*' \
  --connect-timeout "$CONNECT_TIMEOUT" --max-time "$MAX_TIME" \
  "$selected/json/version")"

mapfile -t version_values < <(python3 - "$version_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
print(data.get("Browser", ""))
print(data.get("webSocketDebuggerUrl", ""))
PY
)
browser="${version_values[0]:-}"
websocket_url="${version_values[1]:-}"
chrome_pid=""

if [[ -n "$state_file" && -r "$state_file" ]]; then
  chrome_pid="$(python3 - "$state_file" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8-sig") as f:
        data = json.load(f)
    print(data.get("chromePid", ""))
except Exception:
    pass
PY
)"
fi

if [[ -z "$chrome_pid" ]]; then
  chrome_pid="$(timeout 3s powershell.exe -NoProfile -NonInteractive -Command \
    "\$c=Get-NetTCPConnection -State Listen -LocalPort $CHROME_PORT -ErrorAction SilentlyContinue | Select-Object -First 1; if(\$c){\$c.OwningProcess}" \
    2>/dev/null | tr -d '\r' | tail -n 1)"
fi

skill_exists=false
[[ -f "$SKILL_PATH" ]] && skill_exists=true

case "$MODE" in
  url)
    printf '%s\n' "$selected"
    ;;
  export)
    printf "export CRC_CDP_URL='%s'\n" "$selected"
    ;;
  json)
    python3 - "$selected" "$network_mode" "$chrome_pid" "$browser" "$websocket_url" "$state_file" "$SKILL_PATH" "$skill_exists" <<'PY'
import json, sys
endpoint, mode, pid, browser, ws, state, skill, exists = sys.argv[1:]
print(json.dumps({
    "ready": True,
    "endpoint": endpoint,
    "networkingMode": mode,
    "chromePid": int(pid) if pid.isdigit() else None,
    "browser": browser or None,
    "webSocketDebuggerUrl": ws or None,
    "stateFile": state or None,
    "skillPath": skill,
    "skillExists": exists.lower() == "true",
}, ensure_ascii=False, indent=2))
PY
    ;;
  *)
    echo "Chrome CDP ready"
    echo "  Endpoint:        $selected"
    echo "  Networking mode: $network_mode"
    echo "  Chrome PID:      ${chrome_pid:-unknown}"
    echo "  Browser:         ${browser:-unknown}"
    echo "  Skill path:      $SKILL_PATH ($([[ "$skill_exists" == true ]] && echo found || echo missing))"
    echo ""
    echo "Current shell:"
    echo "  export CRC_CDP_URL='$selected'"
    ;;
esac
