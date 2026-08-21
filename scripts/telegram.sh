#!/usr/bin/env bash
# Talk to the clashogram bot on Telegram with curl and jq.
set -euo pipefail

API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN not set}"

# Without this every failure looks the same: nothing at all. A 409 means
# something else is already long polling, which is normally the bot itself.
call() {
    local response
    response=$(curl -s "$@")
    if [[ "$(jq -r '.ok' <<<"$response")" != true ]]; then
        jq -r '"telegram: \(.error_code) \(.description)"' <<<"$response" >&2
        [[ "$(jq -r '.error_code' <<<"$response")" == 409 ]] &&
            echo "hint: stop the bot first, it is consuming the updates" >&2
        return 1
    fi
    printf '%s' "$response"
}

me() {
    call "$API/getMe" \
        | jq -r '"@\(.result.username) | \(.result.first_name) | id \(.result.id)"'
}

updates() {
    local offset="${1:-}"
    # Not an array: bash 3.2, which is /bin/sh on macOS, calls an empty
    # one unbound under `set -u`.
    local url="$API/getUpdates"
    if [[ -n "$offset" ]]; then
        url="$url?offset=$offset"
    fi
    call "$url" | jq -r '
        ["update_id", "chat_id", "type", "title", "text"],
        (.result[] |
         [.update_id,
          (.message // .channel_post // .edited_message // {}).chat.id,
          (.message // .channel_post // {}).chat.type,
          (.message // .channel_post // {}).chat.title // "",
          (.message // .channel_post // {}).text // ""]) |
        @tsv'
}

send() {
    local chat_id="${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID not set}"
    call -d "chat_id=$chat_id" --data-urlencode "text=$1" "$API/sendMessage" \
        | jq -r '"sent as message \(.result.message_id)"'
}

case "${1:-}" in
    me)      me ;;
    updates) updates "${2:-}" ;;
    send)    send "${2:?usage: telegram.sh send <text>}" ;;
    *)       echo "usage: telegram.sh {me|updates [offset]|send <text>}" >&2; exit 1 ;;
esac