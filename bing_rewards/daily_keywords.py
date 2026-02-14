# SPDX-FileCopyrightText: 2026 Bing Rewards Enhancement
#
# SPDX-License-Identifier: MIT

"""Daily keywords rotation module for varied daily searches.

This module provides daily-rotated, non-repeating keywords across multiple
gaming-focused categories. Uses date-based seeding for consistent daily rotation.
"""

from __future__ import annotations

import random
from datetime import date
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    pass

from bing_rewards import search_history


# Category weights for keyword selection
# Higher weight = more keywords from that category
CATEGORY_WEIGHTS = {
    'popular_games': 20,
    'esports': 15,
    'hardware': 10,
    'genres': 10,
    'indie': 10,
    'personalities': 8,
    'events': 7,
    'technology': 5,
    'retro': 5,
    'multiplayer': 5,
    'development': 3,
    'culture': 2,
}


def load_keywords_from_file(filename: str) -> list[str]:
    """Load keywords from a file in the data directory.
    
    Args:
        filename: Name of the keyword file
        
    Returns:
        list: List of keywords
    """
    keywords = []
    
    try:
        data_path = resources.files('bing_rewards').joinpath('data', filename)
        
        with resources.as_file(data_path) as p:
            with p.open(mode='r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#') and not line.startswith('='):
                        keywords.append(line)
    except Exception as e:
        print(f"Error loading keywords from {filename}: {e}")
    
    return keywords


def load_gaming_keywords() -> list[str]:
    """Load gaming-focused keywords.
    
    Returns:
        list: List of gaming keywords
    """
    return load_keywords_from_file('keywords_gaming.txt')


def load_fallback_keywords() -> list[str]:
    """Load fallback keywords from original file.
    
    Returns:
        list: List of fallback keywords
    """
    return load_keywords_from_file('keywords.txt')


def get_daily_seed() -> int:
    """Get a seed value based on today's date.
    
    This ensures the same keywords appear in the same order
    for a given day, but different order each day.
    
    Returns:
        int: Seed value for random shuffling
    """
    today = date.today()
    return today.toordinal()


def get_weekly_rotation() -> int:
    """Get which week rotation we're on (0-51).
    
    This helps divide keywords into weekly pools to ensure
    maximum variety across a 7-day period.
    
    Returns:
        int: Week number (0-51)
    """
    today = date.today()
    return today.isocalendar()[1] % 52


def shuffle_for_today(keywords: list[str]) -> list[str]:
    """Shuffle keywords deterministically based on today's date.
    
    Args:
        keywords: List of keywords to shuffle
        
    Returns:
        list: Shuffled list of keywords
    """
    seed = get_daily_seed()
    
    # Create a copy to avoid modifying original
    shuffled = keywords.copy()
    
    # Use date-based seed for deterministic shuffle
    rng = random.Random(seed)
    rng.shuffle(shuffled)
    
    return shuffled


def filter_recent_searches(keywords: list[str], days: int = 7) -> list[str]:
    """Filter out keywords that were used recently.
    
    Args:
        keywords: List of keywords to filter
        days: Number of days to look back
        
    Returns:
        list: Filtered list of keywords
    """
    recent = search_history.get_recent_searches(days)
    
    filtered = [
        kw for kw in keywords 
        if kw.strip().lower() not in recent
    ]
    
    return filtered


def get_daily_keywords(count: int = 100, record_history: bool = True) -> list[str]:
    """Get a list of keywords for today's searches.
    
    Args:
        count: Maximum number of keywords to return
        record_history: Whether to record returned keywords in history
        
    Returns:
        list: List of keywords for today
    """
    # Load all gaming keywords
    gaming_keywords = load_gaming_keywords()
    
    # Fall back to original if gaming file is empty
    if not gaming_keywords:
        print("Warning: No gaming keywords found, using fallback")
        gaming_keywords = load_fallback_keywords()
    
    if not gaming_keywords:
        print("Warning: No keywords found at all!")
        return []
    
    # Shuffle based on today's date
    shuffled = shuffle_for_today(gaming_keywords)
    
    # Filter out recent searches
    available = filter_recent_searches(shuffled, days=7)
    
    # If we've used most keywords, reset and use shuffled without filter
    if len(available) < count:
        print(f"Note: Only {len(available)} unused keywords, recycling some recent ones")
        available = shuffled
    
    # Select keywords for today
    selected = available[:count]
    
    return selected


def daily_keyword_generator(record_history: bool = True) -> Iterator[str]:
    """Generator that yields unique keywords for today.
    
    This generator:
    1. Loads gaming keywords
    2. Shuffles based on date (same order each day)
    3. Filters recently used keywords (7-day window)
    4. Records used keywords to prevent same-day repetition
    
    Args:
        record_history: Whether to record yielded keywords
        
    Yields:
        str: Unique keyword for searching
    """
    # Load all keywords
    gaming_keywords = load_gaming_keywords()
    fallback_keywords = load_fallback_keywords()
    
    # Combine with gaming keywords prioritized
    all_keywords = gaming_keywords + fallback_keywords
    
    if not all_keywords:
        # Emergency fallback with basic keywords
        all_keywords = [
            "gaming news today",
            "video game reviews",
            "esports tournament",
            "new game releases",
            "gaming tips and tricks",
        ]
    
    # Get today's seed for consistent daily ordering
    seed = get_daily_seed()
    rng = random.Random(seed)
    
    # Create copy and shuffle
    shuffled = all_keywords.copy()
    rng.shuffle(shuffled)
    
    # Track what we've yielded this session
    session_used = set()
    
    # Get recent history
    recent_searches = search_history.get_recent_searches(7)
    
    # First pass: yield keywords not used in 7 days
    for keyword in shuffled:
        normalized = keyword.strip().lower()
        
        if normalized in session_used:
            continue
            
        if normalized not in recent_searches:
            session_used.add(normalized)
            
            if record_history:
                search_history.add_search(keyword)
            
            yield keyword
    
    # Second pass: if we run out, recycle older keywords
    # Re-shuffle with different seed for variety
    rng2 = random.Random(seed + 1000)
    rng2.shuffle(shuffled)
    
    for keyword in shuffled:
        normalized = keyword.strip().lower()
        
        if normalized in session_used:
            continue
        
        session_used.add(normalized)
        
        if record_history:
            search_history.add_search(keyword)
        
        yield keyword
    
    # Emergency: if somehow we've used everything, start over
    while True:
        for keyword in shuffled:
            yield keyword


def get_keyword_stats() -> dict:
    """Get statistics about keyword availability.
    
    Returns:
        dict: Keyword statistics
    """
    gaming = load_gaming_keywords()
    fallback = load_fallback_keywords()
    recent = search_history.get_recent_searches(7)
    
    total = len(gaming) + len(fallback)
    gaming_available = len([k for k in gaming if k.strip().lower() not in recent])
    fallback_available = len([k for k in fallback if k.strip().lower() not in recent])
    
    return {
        'gaming_keywords_total': len(gaming),
        'fallback_keywords_total': len(fallback),
        'total_keywords': total,
        'gaming_available': gaming_available,
        'fallback_available': fallback_available,
        'total_available': gaming_available + fallback_available,
        'recently_used_count': len(recent),
        'today_seed': get_daily_seed(),
        'week_rotation': get_weekly_rotation(),
    }


def preview_today_searches(count: int = 20) -> list[str]:
    """Preview what searches would happen today (without recording).
    
    Args:
        count: Number of searches to preview
        
    Returns:
        list: Preview list of search terms
    """
    gen = daily_keyword_generator(record_history=False)
    preview = []
    
    for i, kw in enumerate(gen):
        if i >= count:
            break
        preview.append(kw)
    
    return preview


# Test function
def test_daily_keywords():
    """Test the daily keywords functionality."""
    print("=" * 60)
    print("Testing Daily Keywords Module")
    print("=" * 60)
    
    # Get stats
    stats = get_keyword_stats()
    print("\n[STATS] Keyword Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Preview today's searches
    print("\n[PREVIEW] Preview of today's searches (first 10):")
    preview = preview_today_searches(10)
    for i, kw in enumerate(preview, 1):
        print(f"   {i}. {kw}")
    
    # Check consistency
    print("\n[CHECK] Consistency check (should be same order):")
    preview2 = preview_today_searches(5)
    for i, kw in enumerate(preview2, 1):
        match = "[OK]" if kw == preview[i-1] else "[FAIL]"
        print(f"   {match} {kw}")
    
    print("\n[DONE] Daily keywords test complete!")


if __name__ == "__main__":
    test_daily_keywords()
