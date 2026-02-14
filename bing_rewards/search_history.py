# SPDX-FileCopyrightText: 2026 Bing Rewards Enhancement
#
# SPDX-License-Identifier: MIT

"""Search history tracking for daily varied searches.

This module tracks used searches to prevent repetition within a rolling 7-day window.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def get_history_file() -> Path:
    """Get the path to the search history file.
    
    Returns:
        Path: The path to search_history.json
    """
    if os.name == 'nt':
        app_data = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        app_data = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    
    history_dir = app_data / 'bing-rewards'
    history_dir.mkdir(parents=True, exist_ok=True)
    
    return history_dir / 'search_history.json'


def load_history() -> dict:
    """Load search history from file.
    
    Returns:
        dict: Dictionary with dates as keys and list of searches as values
    """
    history_file = get_history_file()
    
    if not history_file.exists():
        return {}
    
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_history(history: dict) -> bool:
    """Save search history to file.
    
    Args:
        history: Dictionary with dates as keys and list of searches as values
    
    Returns:
        bool: True if saved successfully
    """
    history_file = get_history_file()
    
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        print(f"Error saving history: {e}")
        return False


def cleanup_old_history(history: dict, days: int = 7) -> dict:
    """Remove entries older than specified days.
    
    Args:
        history: The history dictionary
        days: Number of days to keep (default 7)
    
    Returns:
        dict: Cleaned history dictionary
    """
    cutoff_date = date.today() - timedelta(days=days)
    cutoff_str = cutoff_date.isoformat()
    
    cleaned = {
        date_key: searches 
        for date_key, searches in history.items() 
        if date_key >= cutoff_str
    }
    
    return cleaned


def get_recent_searches(days: int = 7) -> set[str]:
    """Get all searches from the past N days.
    
    Args:
        days: Number of days to look back (default 7)
    
    Returns:
        set: Set of search terms used in the past N days
    """
    history = load_history()
    history = cleanup_old_history(history, days)
    
    # Save cleaned history
    save_history(history)
    
    recent = set()
    for date_searches in history.values():
        recent.update(date_searches)
    
    return recent


def add_search(search_term: str) -> bool:
    """Add a search term to today's history.
    
    Args:
        search_term: The search term to record
    
    Returns:
        bool: True if added successfully
    """
    history = load_history()
    today = date.today().isoformat()
    
    if today not in history:
        history[today] = []
    
    # Normalize search term
    normalized = search_term.strip().lower()
    
    if normalized not in history[today]:
        history[today].append(normalized)
    
    return save_history(history)


def is_search_used_recently(search_term: str, days: int = 7) -> bool:
    """Check if a search term was used in the past N days.
    
    Args:
        search_term: The search term to check
        days: Number of days to look back (default 7)
    
    Returns:
        bool: True if the search was used recently
    """
    recent = get_recent_searches(days)
    normalized = search_term.strip().lower()
    return normalized in recent


def get_stats() -> dict:
    """Get search history statistics.
    
    Returns:
        dict: Statistics about search history
    """
    history = load_history()
    history = cleanup_old_history(history, 7)
    
    total_searches = sum(len(searches) for searches in history.values())
    unique_searches = len(get_recent_searches(7))
    days_with_data = len(history)
    
    return {
        'total_searches_7_days': total_searches,
        'unique_searches_7_days': unique_searches,
        'days_with_data': days_with_data,
        'history_file': str(get_history_file()),
    }


def clear_history() -> bool:
    """Clear all search history.
    
    Returns:
        bool: True if cleared successfully
    """
    history_file = get_history_file()
    
    try:
        if history_file.exists():
            history_file.unlink()
        return True
    except IOError as e:
        print(f"Error clearing history: {e}")
        return False


# Test function
def test_history():
    """Test the history tracking functionality."""
    print("Testing search history module...")
    
    # Add some test searches
    test_searches = ["test search 1", "test search 2", "test search 3"]
    
    for search in test_searches:
        add_search(search)
        print(f"Added: {search}")
    
    # Check if they're recorded
    for search in test_searches:
        is_used = is_search_used_recently(search)
        print(f"'{search}' used recently: {is_used}")
    
    # Get stats
    stats = get_stats()
    print(f"Stats: {stats}")
    
    print("History test complete!")


if __name__ == "__main__":
    test_history()
