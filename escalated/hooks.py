"""
WordPress-style hook system for Escalated.

Provides actions (side-effect callbacks) and filters (value-transforming
callbacks) with priority-based execution ordering.

Usage::

    from escalated.hooks import add_action, do_action, add_filter, apply_filters

    # Actions — fire-and-forget side effects
    add_action('ticket_created', my_callback, priority=10)
    do_action('ticket_created', ticket, user)

    # Filters — transform a value through a chain of callbacks
    add_filter('ticket_subject', my_filter, priority=10)
    subject = apply_filters('ticket_subject', original_subject, ticket)

    # Decorator shortcuts
    @on_action('ticket_created')
    def handle_ticket_created(ticket, user):
        ...

    @on_filter('ticket_subject', priority=5)
    def uppercase_subject(value, ticket):
        return value.upper()
"""

import functools
import logging
from collections import defaultdict

logger = logging.getLogger("escalated.hooks")


class HookManager:
    """
    Central hook manager implementing WordPress-style actions and filters
    with priority-based execution.

    Lower priority numbers execute first (default is 10).
    """

    def __init__(self):
        # {tag: {priority: [callable, ...]}}
        self._actions = defaultdict(lambda: defaultdict(list))
        self._filters = defaultdict(lambda: defaultdict(list))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def add_action(self, tag, callback, priority=10):
        """
        Register a callback for an action hook.

        Args:
            tag: The action name (e.g. 'ticket_created').
            callback: A callable to invoke when the action fires.
            priority: Execution order — lower runs first. Default 10.
        """
        if not callable(callback):
            raise TypeError(f"Callback for action '{tag}' must be callable.")
        self._actions[tag][priority].append(callback)

    def do_action(self, tag, *args, **kwargs):
        """
        Fire all callbacks registered for an action, in priority order.

        Args:
            tag: The action name.
            *args, **kwargs: Passed through to every callback.
        """
        if tag not in self._actions:
            return

        for priority in sorted(self._actions[tag].keys()):
            for callback in self._actions[tag][priority]:
                try:
                    callback(*args, **kwargs)
                except Exception:
                    logger.exception(
                        "Error in action hook '%s' (priority %s, callback %r)",
                        tag,
                        priority,
                        callback,
                    )

    def has_action(self, tag):
        """Return True if any callbacks are registered for *tag*."""
        if tag not in self._actions:
            return False
        return any(
            len(callbacks) > 0
            for callbacks in self._actions[tag].values()
        )

    def remove_action(self, tag, callback=None):
        """
        Remove action callbacks.

        If *callback* is None, all callbacks for *tag* are removed.
        Otherwise only the matching callback is removed (from every priority).
        """
        if callback is None:
            self._actions.pop(tag, None)
            return

        if tag not in self._actions:
            return

        for priority in list(self._actions[tag].keys()):
            self._actions[tag][priority] = [
                cb for cb in self._actions[tag][priority] if cb is not callback
            ]
            if not self._actions[tag][priority]:
                del self._actions[tag][priority]

        if not self._actions[tag]:
            del self._actions[tag]

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def add_filter(self, tag, callback, priority=10):
        """
        Register a callback for a filter hook.

        The callback receives the current value as its first argument,
        followed by any extra arguments, and must return the (possibly
        modified) value.

        Args:
            tag: The filter name (e.g. 'ticket_subject').
            callback: A callable(value, *args, **kwargs) -> value.
            priority: Execution order — lower runs first. Default 10.
        """
        if not callable(callback):
            raise TypeError(f"Callback for filter '{tag}' must be callable.")
        self._filters[tag][priority].append(callback)

    def apply_filters(self, tag, value, *args, **kwargs):
        """
        Pass *value* through every registered filter callback and return
        the final result.

        Args:
            tag: The filter name.
            value: The initial value to filter.
            *args, **kwargs: Extra arguments forwarded to each callback.
        """
        if tag not in self._filters:
            return value

        for priority in sorted(self._filters[tag].keys()):
            for callback in self._filters[tag][priority]:
                try:
                    value = callback(value, *args, **kwargs)
                except Exception:
                    logger.exception(
                        "Error in filter hook '%s' (priority %s, callback %r)",
                        tag,
                        priority,
                        callback,
                    )

        return value

    def has_filter(self, tag):
        """Return True if any callbacks are registered for *tag*."""
        if tag not in self._filters:
            return False
        return any(
            len(callbacks) > 0
            for callbacks in self._filters[tag].values()
        )

    def remove_filter(self, tag, callback=None):
        """
        Remove filter callbacks.

        If *callback* is None, all callbacks for *tag* are removed.
        Otherwise only the matching callback is removed (from every priority).
        """
        if callback is None:
            self._filters.pop(tag, None)
            return

        if tag not in self._filters:
            return

        for priority in list(self._filters[tag].keys()):
            self._filters[tag][priority] = [
                cb for cb in self._filters[tag][priority] if cb is not callback
            ]
            if not self._filters[tag][priority]:
                del self._filters[tag][priority]

        if not self._filters[tag]:
            del self._filters[tag]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_actions(self):
        """Return the raw actions registry (for debugging/testing)."""
        return dict(self._actions)

    def get_filters(self):
        """Return the raw filters registry (for debugging/testing)."""
        return dict(self._filters)

    def clear(self):
        """Remove all registered actions and filters. Useful for testing."""
        self._actions.clear()
        self._filters.clear()


# ---------------------------------------------------------------------------
# Module-level singleton and convenience functions
# ---------------------------------------------------------------------------

hooks = HookManager()


def add_action(tag, callback, priority=10):
    """Register an action callback on the global hook manager."""
    hooks.add_action(tag, callback, priority)


def do_action(tag, *args, **kwargs):
    """Fire an action on the global hook manager."""
    hooks.do_action(tag, *args, **kwargs)


def has_action(tag):
    """Check if an action has callbacks on the global hook manager."""
    return hooks.has_action(tag)


def remove_action(tag, callback=None):
    """Remove an action callback from the global hook manager."""
    hooks.remove_action(tag, callback)


def add_filter(tag, callback, priority=10):
    """Register a filter callback on the global hook manager."""
    hooks.add_filter(tag, callback, priority)


def apply_filters(tag, value, *args, **kwargs):
    """Apply filters on the global hook manager."""
    return hooks.apply_filters(tag, value, *args, **kwargs)


def has_filter(tag):
    """Check if a filter has callbacks on the global hook manager."""
    return hooks.has_filter(tag)


def remove_filter(tag, callback=None):
    """Remove a filter callback from the global hook manager."""
    hooks.remove_filter(tag, callback)


# ---------------------------------------------------------------------------
# Decorator shortcuts
# ---------------------------------------------------------------------------


def on_action(tag, priority=10):
    """
    Decorator to register a function as an action callback::

        @on_action('ticket_created')
        def handle(ticket, user):
            ...
    """
    def decorator(func):
        add_action(tag, func, priority)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def on_filter(tag, priority=10):
    """
    Decorator to register a function as a filter callback::

        @on_filter('ticket_subject', priority=5)
        def uppercase(value, ticket):
            return value.upper()
    """
    def decorator(func):
        add_filter(tag, func, priority)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
