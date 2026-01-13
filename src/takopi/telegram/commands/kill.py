from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...markdown import MarkdownParts
from ...transport import MessageRef, RenderedMessage, SendOptions
from ...worktrees import (
    WorktreeError,
    remove_worktree,
    resolve_existing_worktree,
    worktree_change_count,
)
from ..context import _format_context
from ..render import prepare_telegram
from ..topic_state import TopicStateStore
from ..topics import _topic_key, _topics_command_error
from ..types import TelegramCallbackQuery, TelegramIncomingMessage
from .reply import make_reply

if TYPE_CHECKING:
    from ..bridge import TelegramBridgeConfig

KILL_CALLBACK_PREFIX = "takopi:kill:"

_KILL_ACTION_TOPIC = "topic"
_KILL_ACTION_WORKTREE = "worktree"
_KILL_ACTION_FORCE = "force"
_KILL_ACTION_ABORT = "abort"
_KILL_ACTIONS = {
    _KILL_ACTION_TOPIC,
    _KILL_ACTION_WORKTREE,
    _KILL_ACTION_FORCE,
    _KILL_ACTION_ABORT,
}


def _kill_callback(thread_id: int, action: str) -> str:
    return f"{KILL_CALLBACK_PREFIX}{thread_id}:{action}"


def _parse_kill_callback(data: str | None) -> tuple[int, str] | None:
    if not data or not data.startswith(KILL_CALLBACK_PREFIX):
        return None
    payload = data[len(KILL_CALLBACK_PREFIX) :]
    thread_str, sep, action = payload.partition(":")
    if not sep or not thread_str.isdigit() or action not in _KILL_ACTIONS:
        return None
    return int(thread_str), action


def _kill_prompt_markup(thread_id: int, *, has_worktree: bool) -> dict[str, Any]:
    keyboard: list[list[dict[str, str]]] = []
    if has_worktree:
        keyboard.append(
            [
                {
                    "text": "delete worktree + topic",
                    "callback_data": _kill_callback(thread_id, _KILL_ACTION_WORKTREE),
                }
            ]
        )
        keyboard.append(
            [
                {
                    "text": "delete topic only",
                    "callback_data": _kill_callback(thread_id, _KILL_ACTION_TOPIC),
                }
            ]
        )
    else:
        keyboard.append(
            [
                {
                    "text": "delete topic",
                    "callback_data": _kill_callback(thread_id, _KILL_ACTION_TOPIC),
                }
            ]
        )
    keyboard.append(
        [{"text": "cancel", "callback_data": _kill_callback(thread_id, _KILL_ACTION_ABORT)}]
    )
    return {"inline_keyboard": keyboard}


def _kill_confirm_markup(thread_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "delete worktree",
                    "callback_data": _kill_callback(thread_id, _KILL_ACTION_FORCE),
                },
                {
                    "text": "abort",
                    "callback_data": _kill_callback(thread_id, _KILL_ACTION_ABORT),
                },
            ]
        ]
    }


def _change_label(count: int) -> str:
    if count == 1:
        return "1 uncommitted change"
    return f"{count} uncommitted changes"


async def _send_kill_message(
    cfg: TelegramBridgeConfig,
    *,
    chat_id: int,
    thread_id: int | None,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    reply_to_message_id: int | None = None,
) -> None:
    rendered_text, entities = prepare_telegram(MarkdownParts(header=text))
    message = RenderedMessage(
        text=rendered_text,
        extra={"entities": entities, "reply_markup": reply_markup},
    )
    options = SendOptions(thread_id=thread_id)
    if reply_to_message_id is not None:
        options = SendOptions(
            reply_to=MessageRef(channel_id=chat_id, message_id=reply_to_message_id),
            thread_id=thread_id,
        )
    await cfg.exec_cfg.transport.send(
        channel_id=chat_id,
        message=message,
        options=options,
    )


async def _delete_topic(
    cfg: TelegramBridgeConfig,
    store: TopicStateStore | None,
    *,
    chat_id: int,
    thread_id: int,
) -> bool:
    deleted = await cfg.bot.delete_forum_topic(
        chat_id=chat_id,
        message_thread_id=thread_id,
    )
    if not deleted:
        await _send_kill_message(
            cfg,
            chat_id=chat_id,
            thread_id=thread_id,
            text="failed to delete the topic.",
        )
        return False
    if store is not None:
        await store.delete_thread(chat_id, thread_id)
    return True


async def _handle_kill_command(
    cfg: TelegramBridgeConfig,
    msg: TelegramIncomingMessage,
    store: TopicStateStore,
    *,
    resolved_scope: str | None = None,
    scope_chat_ids: frozenset[int] | None = None,
) -> None:
    reply = make_reply(cfg, msg)
    error = _topics_command_error(
        cfg,
        msg.chat_id,
        resolved_scope=resolved_scope,
        scope_chat_ids=scope_chat_ids,
    )
    if error is not None:
        await reply(text=error)
        return
    tkey = _topic_key(msg, cfg, scope_chat_ids=scope_chat_ids)
    if tkey is None:
        await reply(text="this command only works inside a topic.")
        return
    snapshot = await store.get_thread(*tkey)
    context = snapshot.context if snapshot is not None else None
    worktree_path = None
    if context is not None and context.project and context.branch:
        project = cfg.runtime.project_config(context.project)
        if project is None:
            await reply(text=f"error:\nunknown project {context.project!r}")
            return
        try:
            worktree_path = resolve_existing_worktree(project, context.branch)
        except WorktreeError as exc:
            await reply(text=f"error:\n{exc}")
            return
    if worktree_path is None:
        text = "delete this topic? (no worktree found for this topic)"
        reply_markup = _kill_prompt_markup(tkey[1], has_worktree=False)
    else:
        label = _format_context(cfg.runtime, context)
        text = f"delete this topic?\nalso delete worktree `{label}`?"
        reply_markup = _kill_prompt_markup(tkey[1], has_worktree=True)
    await _send_kill_message(
        cfg,
        chat_id=msg.chat_id,
        thread_id=msg.thread_id,
        text=text,
        reply_markup=reply_markup,
        reply_to_message_id=msg.message_id,
    )


async def handle_kill_callback(
    cfg: TelegramBridgeConfig,
    query: TelegramCallbackQuery,
    store: TopicStateStore | None,
) -> None:
    parsed = _parse_kill_callback(query.data)
    if parsed is None:
        await cfg.bot.answer_callback_query(
            callback_query_id=query.callback_query_id,
        )
        return
    thread_id, action = parsed
    if store is None or not cfg.topics.enabled:
        await cfg.bot.answer_callback_query(
            callback_query_id=query.callback_query_id,
            text="topics are disabled.",
        )
        return
    if action == _KILL_ACTION_ABORT:
        await cfg.bot.answer_callback_query(
            callback_query_id=query.callback_query_id,
            text="cancelled.",
        )
        return
    if action == _KILL_ACTION_TOPIC:
        await cfg.bot.answer_callback_query(
            callback_query_id=query.callback_query_id,
            text="deleting topic...",
        )
        await _delete_topic(cfg, store, chat_id=query.chat_id, thread_id=thread_id)
        return

    snapshot = await store.get_thread(query.chat_id, thread_id)
    context = snapshot.context if snapshot is not None else None
    if context is None or context.project is None or context.branch is None:
        await cfg.bot.answer_callback_query(
            callback_query_id=query.callback_query_id,
            text="no worktree for this topic.",
        )
        await _send_kill_message(
            cfg,
            chat_id=query.chat_id,
            thread_id=thread_id,
            text="no worktree found for this topic; deleting topic only.",
        )
        await _delete_topic(cfg, store, chat_id=query.chat_id, thread_id=thread_id)
        return

    project = cfg.runtime.project_config(context.project)
    if project is None:
        await cfg.bot.answer_callback_query(
            callback_query_id=query.callback_query_id,
            text="unknown project.",
        )
        await _send_kill_message(
            cfg,
            chat_id=query.chat_id,
            thread_id=thread_id,
            text=f"error:\nunknown project {context.project!r}",
        )
        return

    try:
        worktree_path = resolve_existing_worktree(project, context.branch)
    except WorktreeError as exc:
        await cfg.bot.answer_callback_query(
            callback_query_id=query.callback_query_id,
            text="worktree error.",
        )
        await _send_kill_message(
            cfg,
            chat_id=query.chat_id,
            thread_id=thread_id,
            text=f"error:\n{exc}",
        )
        return

    if worktree_path is None:
        await cfg.bot.answer_callback_query(
            callback_query_id=query.callback_query_id,
            text="no worktree found.",
        )
        await _send_kill_message(
            cfg,
            chat_id=query.chat_id,
            thread_id=thread_id,
            text="no worktree found for this topic; deleting topic only.",
        )
        await _delete_topic(cfg, store, chat_id=query.chat_id, thread_id=thread_id)
        return

    if action == _KILL_ACTION_WORKTREE:
        try:
            change_count = worktree_change_count(worktree_path)
        except WorktreeError as exc:
            await cfg.bot.answer_callback_query(
                callback_query_id=query.callback_query_id,
                text="git status failed.",
            )
            await _send_kill_message(
                cfg,
                chat_id=query.chat_id,
                thread_id=thread_id,
                text=f"error:\n{exc}",
            )
            return
        if change_count:
            await cfg.bot.answer_callback_query(
                callback_query_id=query.callback_query_id,
                text="uncommitted changes found.",
            )
            changes = _change_label(change_count)
            await _send_kill_message(
                cfg,
                chat_id=query.chat_id,
                thread_id=thread_id,
                text=(
                    f"worktree `{worktree_path}` has {changes}.\n"
                    "delete it and discard these changes? (topic will be deleted too)"
                ),
                reply_markup=_kill_confirm_markup(thread_id),
            )
            return

    await cfg.bot.answer_callback_query(
        callback_query_id=query.callback_query_id,
        text="deleting worktree...",
    )
    try:
        removed = remove_worktree(
            project, context.branch, force=action == _KILL_ACTION_FORCE
        )
    except WorktreeError as exc:
        await _send_kill_message(
            cfg,
            chat_id=query.chat_id,
            thread_id=thread_id,
            text=f"error:\n{exc}",
        )
        return
    if removed is None:
        await _send_kill_message(
            cfg,
            chat_id=query.chat_id,
            thread_id=thread_id,
            text="no worktree found for this topic; deleting topic only.",
        )
    await _delete_topic(cfg, store, chat_id=query.chat_id, thread_id=thread_id)
