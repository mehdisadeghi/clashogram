########################################################################
# Subscriptions
########################################################################
"""Who is followed and who is told about it.

The rules live here and the sql lives in `storage`. Nothing in this
module talks to a chat service; it answers questions and records
answers, and the caller does the telling."""
import datetime


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def clans_with_chats(db):
    """Every followed clan mapped to the chats following it.

    Polling is grouped by clan, not by subscription, so two chats
    following one clan cost one poll rather than two."""
    grouped = {}
    for clan_tag, chat_id in db.subscriptions():
        grouped.setdefault(clan_tag, []).append(chat_id)
    return grouped


def clans_for_chat(db, chat_id):
    return [clan_tag for clan_tag, subscribed in db.subscriptions()
            if subscribed == str(chat_id)]


def subscribe(db, clan_tag, chat_id, war_id=None):
    """Follow a clan in a chat, without reciting the war so far.

    A war already under way has messages the other chats have seen. They
    are marked as seen here too, so the new chat starts from the next
    thing that happens. A clan whose first chat this is has nothing to
    copy and does get the war from its beginning."""
    db.subscribe(clan_tag, chat_id, _now())
    if war_id is None:
        return
    seen = set()
    for other in clans_with_chats(db).get(clan_tag, []):
        if str(other) != str(chat_id):
            seen.update(db.sent_msg_ids(war_id, other))
    for msg_id in seen:
        db.mark_sent(war_id, msg_id, chat_id)


def unsubscribe(db, clan_tag, chat_id):
    return db.unsubscribe(clan_tag, chat_id)


def operators(db):
    return db.operators()


def add_operator(db, user_id):
    db.add_operator(user_id, _now())


def remove_operator(db, user_id):
    return db.remove_operator(user_id)


def file_request(db, clan_tag, chat_id, requester_id):
    return db.file_request(clan_tag, chat_id, requester_id, _now())


def pending_requests(db):
    return db.pending_requests()


def resolve_request(db, request_id, approved):
    """Settle a request, subscribing it when approved."""
    request = db.resolve_request(request_id,
                                 'approved' if approved else 'denied')
    if request and approved:
        subscribe(db, request['clan_tag'], request['chat_id'])
        if not db.chat_steward(request['chat_id']):
            db.set_chat_steward(request['chat_id'], request['requester_id'])
    return request
