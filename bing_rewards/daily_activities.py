# SPDX-FileCopyrightText: 2026 Bing Rewards Enhancement
#
# SPDX-License-Identifier: MIT

"""Automate Microsoft Rewards daily activities using Playwright.

Handles quizzes, polls, trivia, and click-only tasks on the Rewards dashboard.
Uses the user's existing Chrome/Edge browser — no separate Chromium download needed.

Uses a DEDICATED automation profile directory (not the main browser profile)
to avoid conflicts when the browser is already running.
"""

from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

# Rewards dashboard URL
REWARDS_URL = "https://rewards.bing.com/"
BING_URL = "https://www.bing.com/"


class Activity:
    """Represents a single daily activity card."""

    def __init__(self, title: str, points: str, url: str, completed: bool = False):
        self.title = title
        self.points = points
        self.url = url
        self.completed = completed

    def __repr__(self) -> str:
        status = "✅" if self.completed else "⬜"
        return f"{status} {self.title} (+{self.points}) -> {self.url}"


async def _random_delay(min_s: float = 1.0, max_s: float = 3.0):
    """Wait a random amount of time to appear more human-like."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _wait_for_page_load(page: Page, timeout: int = 10000):
    """Wait for page to finish loading."""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
        await _random_delay(1.0, 2.0)
    except Exception:
        await _random_delay(2.0, 3.0)


# ──────────────────────────────────────────────
# Activity Detection
# ──────────────────────────────────────────────

async def detect_activities(page: Page) -> list[Activity]:
    """Scan the Rewards dashboard for available daily activity cards.

    Returns a list of Activity objects with title, points, URL, and completion status.
    """
    activities: list[Activity] = []

    # Wait for dashboard to load
    await _wait_for_page_load(page)
    await _random_delay(2.0, 4.0)

    # Try multiple selector strategies for activity cards
    # Microsoft changes their DOM frequently, so we try several approaches

    # Strategy 1: Look for mee-card elements (common in Rewards dashboard)
    cards = await page.query_selector_all("mee-card")

    if not cards:
        # Strategy 2: Look for card-like containers with point badges
        cards = await page.query_selector_all("[class*='card'], [class*='Card']")

    if not cards:
        # Strategy 3: Look for activity links in the daily set section
        cards = await page.query_selector_all(
            "a[href*='daily'], a[href*='quiz'], a[href*='poll']"
        )

    for card in cards:
        try:
            # Try to extract title
            title_el = await card.query_selector(
                "[class*='title'], [class*='Title'], h3, h4, [aria-label]"
            )
            title = ""
            if title_el:
                title = (await title_el.inner_text()).strip()
            if not title:
                title = (await card.inner_text()).strip()[:80]

            if not title or len(title) < 3:
                continue

            # Try to extract points
            points_el = await card.query_selector(
                "[class*='point'], [class*='Point'], [class*='badge'], [class*='Badge']"
            )
            points = ""
            if points_el:
                points = (await points_el.inner_text()).strip()

            # Try to extract URL
            url = ""
            link_el = await card.query_selector("a[href]")
            if link_el:
                url = await link_el.get_attribute("href") or ""
            else:
                # The card itself might be a link
                url = await card.get_attribute("href") or ""

            # Check if already completed (look for checkmark or completed state)
            completed = False
            check_el = await card.query_selector(
                "[class*='complete'], [class*='Complete'], "
                "[class*='check'], [class*='Check'], "
                "[aria-label*='completed'], [aria-label*='Completed']"
            )
            if check_el:
                completed = True

            if url and not completed:
                activities.append(Activity(
                    title=title,
                    points=points,
                    url=url,
                    completed=completed,
                ))

        except Exception as e:
            print(f"  ⚠️ Error parsing card: {e}")
            continue

    return activities


# ──────────────────────────────────────────────
# Activity Type Detection & Routing
# ──────────────────────────────────────────────

async def detect_activity_type(page: Page) -> str:
    """Detect the type of activity on the current page.

    Returns one of: 'quiz', 'poll', 'trivia', 'click_only'
    """
    await _wait_for_page_load(page)
    await _random_delay(1.5, 3.0)

    # Check for quiz elements
    quiz_selectors = [
        "#rqQuestionState",
        "[class*='rqQuestion']",
        "[id*='rqAnswerOption']",
        ".wk_choicesInst498",
        "#quizCompleteContainer",
        "[class*='QuizQuestion']",
    ]
    for sel in quiz_selectors:
        if await page.query_selector(sel):
            return "quiz"

    # Check for poll elements
    poll_selectors = [
        "#btPollOverlay",
        "[class*='pollOption']",
        "[class*='PollOption']",
        "[class*='bt_poll']",
        "[id*='btoption']",
    ]
    for sel in poll_selectors:
        if await page.query_selector(sel):
            return "poll"

    # Check for trivia / this-or-that elements
    trivia_selectors = [
        ".wk_Circle",
        "[class*='TriviaOption']",
        "#rqAnswerOption0",
        "[class*='trivia']",
        "[class*='thisOrThat']",
        "[class*='btOptionCard']",
    ]
    for sel in trivia_selectors:
        if await page.query_selector(sel):
            return "trivia"

    # Check for lightspeed quiz
    lightspeed_selectors = [
        "[class*='lightspeed']",
        "#rqStartQuiz",
        "[id*='StartQuiz']",
    ]
    for sel in lightspeed_selectors:
        if await page.query_selector(sel):
            return "quiz"

    # Default: click-only (just visiting the page earns points)
    return "click_only"


# ──────────────────────────────────────────────
# Activity Handlers
# ──────────────────────────────────────────────

async def handle_quiz(page: Page) -> bool:
    """Handle quiz-type activities.

    Strategy: Click through answer options. Most quizzes allow retry on wrong answers.
    """
    print("    📝 Tipe: Quiz - mencoba menjawab...")

    try:
        # Check if quiz needs to be started first
        start_btn = await page.query_selector(
            "#rqStartQuiz, [id*='StartQuiz'], [class*='start']"
        )
        if start_btn:
            await start_btn.click()
            await _random_delay(2.0, 3.0)

        # Try answering up to 20 questions (some quizzes have multiple)
        for q in range(20):
            # Look for answer options
            options = await page.query_selector_all(
                "[id*='rqAnswerOption'], .wk_choicesInstOptionContainer, "
                "[class*='AnswerOption'], [class*='answerOption']"
            )

            if not options:
                # Also try generic clickable options
                options = await page.query_selector_all(
                    ".option-card, [class*='option'], [role='button']"
                )

            if not options:
                # Quiz might be done
                break

            # Click a random option
            choice = random.choice(options)
            try:
                await choice.click()
                print(f"    ✅ Menjawab pertanyaan {q + 1}")
            except Exception:
                pass

            await _random_delay(1.5, 3.0)

            # Check if quiz is complete
            complete = await page.query_selector(
                "#quizCompleteContainer, [class*='quizComplete'], "
                "[class*='QuizComplete'], [class*='congratulations']"
            )
            if complete:
                print("    🎉 Quiz selesai!")
                return True

        return True

    except Exception as e:
        print(f"    ❌ Error pada quiz: {e}")
        return False


async def handle_poll(page: Page) -> bool:
    """Handle poll-type activities.

    Strategy: Click a random poll option.
    """
    print("    📊 Tipe: Poll - memilih opsi...")

    try:
        # Look for poll options
        options = await page.query_selector_all(
            "#btoption0, #btoption1, [id*='btoption'], "
            "[class*='pollOption'], [class*='PollOption'], "
            "[class*='bt_poll'] [role='button']"
        )

        if not options:
            # Try broader selectors
            options = await page.query_selector_all(
                "[class*='option-card'], [class*='btOption']"
            )

        if options:
            choice = random.choice(options)
            await choice.click()
            print("    ✅ Memilih opsi poll")
            await _random_delay(2.0, 3.0)
            return True
        else:
            print("    ⚠️ Tidak menemukan opsi poll")
            return False

    except Exception as e:
        print(f"    ❌ Error pada poll: {e}")
        return False


async def handle_trivia(page: Page) -> bool:
    """Handle trivia / this-or-that activities.

    Strategy: Click random answers. No penalty for wrong answers.
    """
    print("    🧠 Tipe: Trivia - menjawab...")

    try:
        # Try answering up to 15 trivia questions
        for q in range(15):
            # Look for trivia options
            options = await page.query_selector_all(
                "#rqAnswerOption0, #rqAnswerOption1, "
                "[id*='rqAnswerOption'], "
                ".wk_Circle, [class*='btOptionCard'], "
                "[class*='TriviaOption'], [class*='option-card']"
            )

            if not options:
                break

            # Click a random option
            choice = random.choice(options)
            try:
                await choice.click()
                print(f"    ✅ Menjawab trivia {q + 1}")
            except Exception:
                pass

            await _random_delay(1.5, 3.0)

            # Check if trivia is complete
            complete = await page.query_selector(
                "[class*='complete'], [class*='Complete'], "
                "[class*='congratulations'], #quizCompleteContainer"
            )
            if complete:
                print("    🎉 Trivia selesai!")
                return True

        return True

    except Exception as e:
        print(f"    ❌ Error pada trivia: {e}")
        return False


async def handle_click_only(page: Page) -> bool:
    """Handle click-only activities (just visiting the page earns points)."""
    print("    👆 Tipe: Click-only - cukup buka halaman...")

    try:
        # Just wait for the page to load fully
        await _wait_for_page_load(page)
        await _random_delay(3.0, 5.0)

        # Try scrolling down a bit for engagement
        await page.evaluate("window.scrollBy(0, 300)")
        await _random_delay(1.0, 2.0)

        print("    ✅ Halaman terbuka, poin didapat!")
        return True

    except Exception as e:
        print(f"    ❌ Error pada click-only: {e}")
        return False


async def complete_activity(page: Page, activity: Activity) -> bool:
    """Open an activity and complete it based on its type."""
    print(f"\n  🔄 Membuka: {activity.title}")

    try:
        # Navigate to activity URL
        full_url = activity.url
        if not full_url.startswith("http"):
            full_url = f"https://rewards.bing.com{full_url}"

        await page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
        await _random_delay(2.0, 4.0)

        # Detect activity type
        activity_type = await detect_activity_type(page)

        # Route to correct handler
        handlers = {
            "quiz": handle_quiz,
            "poll": handle_poll,
            "trivia": handle_trivia,
            "click_only": handle_click_only,
        }

        handler = handlers.get(activity_type, handle_click_only)
        success = await handler(page)

        if success:
            print(f"  ✅ Selesai: {activity.title}")
        else:
            print(f"  ⚠️ Mungkin belum selesai: {activity.title}")

        return success

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


# ──────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────

async def run_daily_activities(
    browser_path: str = "",
    profile: str = "Default",
    headless: bool = False,
    dryrun: bool = False,
) -> int:
    """Main entry point for daily activities automation.

    Uses a DEDICATED automation profile directory (not the main browser profile)
    to avoid conflicts when the browser is already running.

    On first run, the user needs to login to Microsoft once.
    After that, the session is saved and reused automatically.

    Args:
        browser_path: Path to Chrome/Edge executable. Auto-detected if empty.
        profile: Browser profile directory name (unused, kept for API compat).
        headless: Run browser in headless mode (not recommended for Rewards).
        dryrun: If True, detect activities but don't complete them.

    Returns:
        Number of activities completed.
    """
    from playwright.async_api import async_playwright

    print("\n" + "=" * 60)
    print("🎯 BING REWARDS - DAILY ACTIVITIES")
    print("=" * 60)

    # Auto-detect browser if not specified
    if not browser_path:
        try:
            from bing_rewards import browser_utils
            browsers = browser_utils.scan_system()
            if browsers:
                # Prefer Edge (better for Bing Rewards), then Chrome, then Brave
                for preferred in ["edge", "chrome", "brave"]:
                    if preferred in browsers:
                        browser_path = browsers[preferred]["executable"]
                        print(f"  🔍 Browser terdeteksi: {browsers[preferred]['name']}")
                        break
        except Exception:
            pass

    if not browser_path:
        print("  ❌ Browser tidak ditemukan! Install Chrome atau Edge.")
        return 0

    print(f"  🌐 Menggunakan: {browser_path}")

    completed = 0

    async with async_playwright() as p:
        try:
            # Use a DEDICATED automation profile (not the main browser profile!)
            # This avoids "Opening in existing browser session" conflicts
            bot_data_dir = _get_bot_data_dir()
            first_run = not bot_data_dir.exists() or not any(bot_data_dir.iterdir())

            bot_data_dir.mkdir(parents=True, exist_ok=True)

            if first_run:
                print(f"\n  🆕 PERTAMA KALI — perlu login ke Microsoft Account")
                print(f"  📁 Profile bot disimpan di: {bot_data_dir}")
            else:
                print(f"  📁 Bot profile: {bot_data_dir}")

            print(f"  🚀 Membuka browser...\n")

            # Launch with persistent context using dedicated bot profile
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(bot_data_dir),
                executable_path=browser_path,
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-infobars",
                ],
                viewport={"width": 1280, "height": 800},
                ignore_default_args=["--enable-automation"],
            )

            page = await context.new_page()

            # Navigate to Rewards dashboard
            print("  📊 Membuka Rewards Dashboard...")
            await page.goto(REWARDS_URL, wait_until="domcontentloaded", timeout=30000)
            await _random_delay(3.0, 5.0)

            # Check if logged in
            logged_in = await _check_login(page)
            if not logged_in:
                print("\n  ⚠️  Belum login ke Microsoft Account!")
                print("  � Silakan login di jendela browser yang terbuka...")
                print("     Setelah login, tekan ENTER di sini untuk lanjut.\n")

                # Wait for user to login manually
                await asyncio.get_event_loop().run_in_executor(None, input)

                # Re-navigate after login
                await page.goto(REWARDS_URL, wait_until="domcontentloaded", timeout=30000)
                await _random_delay(3.0, 5.0)

                logged_in = await _check_login(page)
                if not logged_in:
                    print("  ❌ Masih belum login. Coba jalankan ulang.")
                    await context.close()
                    return 0

                print("  ✅ Login berhasil! Session disimpan untuk lain kali.\n")

            # Detect available activities
            print("  🔍 Mendeteksi daily activities...")
            activities = await detect_activities(page)

            if not activities:
                print("  ℹ️ Tidak ada daily activity yang tersedia.")
                print("     Mungkin sudah semua selesai, atau halaman belum dimuat.")

                # Try alternative: look for clickable promo cards
                print("\n  🔍 Mencoba deteksi alternatif...")
                activities = await _detect_alternative(page)

            if activities:
                print(f"\n  📋 Ditemukan {len(activities)} activity:")
                for i, act in enumerate(activities, 1):
                    print(f"     {i}. {act}")

                if dryrun:
                    print("\n  🔇 Mode Dryrun - tidak menjalankan activities.")
                else:
                    print(f"\n  ▶️ Memulai penyelesaian activities...")
                    for act in activities:
                        success = await complete_activity(page, act)
                        if success:
                            completed += 1
                        await _random_delay(2.0, 4.0)

                        # Go back to dashboard after each activity
                        try:
                            await page.goto(
                                REWARDS_URL,
                                wait_until="domcontentloaded",
                                timeout=30000,
                            )
                            await _random_delay(2.0, 3.0)
                        except Exception:
                            pass
            else:
                print("  ℹ️ Tidak ada activity yang perlu diselesaikan.")

            # Summary
            print("\n" + "=" * 60)
            print(f"  📊 HASIL: {completed}/{len(activities)} activities selesai")
            print("=" * 60)

            await context.close()

        except Exception as e:
            print(f"\n  ❌ Error fatal: {e}")
            import traceback
            traceback.print_exc()

    return completed


async def _check_login(page: Page) -> bool:
    """Check if user is logged into Microsoft account."""
    try:
        # Look for user avatar/name (indicates logged in)
        user_element = await page.query_selector(
            "#id_n, [class*='user-name'], [class*='mectrl_profilepic'], "
            "[class*='avatar'], #meControl"
        )

        if user_element:
            return True

        # Check page content for rewards points (only visible when logged in)
        content = await page.content()
        if "rewards" in content.lower() and (
            "point" in content.lower() or "poin" in content.lower()
        ):
            return True

        # Look for sign-in indicators (if found, NOT logged in)
        sign_in = await page.query_selector(
            "a[href*='login'], [class*='signIn'], [class*='SignIn'], "
            "#id_l, [id*='signin']"
        )

        return sign_in is None

    except Exception:
        return True  # Assume logged in if check fails


async def _detect_alternative(page: Page) -> list[Activity]:
    """Alternative detection method — look for promotional/activity links."""
    activities = []

    try:
        # Look for any clickable promotional cards with point indicators
        links = await page.query_selector_all("a[href]")

        for link in links:
            try:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()

                # Filter for reward-related links
                if not text or len(text) < 5 or len(text) > 200:
                    continue

                # Look for links that seem like activities
                reward_indicators = [
                    "quiz", "poll", "trivia", "puzzle",
                    "+5", "+10", "+15", "+20", "+30", "+50",
                    "daily", "challenge",
                ]

                text_lower = text.lower()
                href_lower = href.lower()

                is_reward = any(
                    ind in text_lower or ind in href_lower
                    for ind in reward_indicators
                )

                if is_reward and href:
                    # Extract points from text
                    points = ""
                    for word in text.split():
                        if word.startswith("+") and word[1:].isdigit():
                            points = word
                            break

                    activities.append(Activity(
                        title=text[:80],
                        points=points,
                        url=href,
                    ))

            except Exception:
                continue

    except Exception as e:
        print(f"  ⚠️ Error in alternative detection: {e}")

    return activities


def _get_bot_data_dir() -> Path:
    """Get a DEDICATED user data directory for the automation bot.

    This is separate from the user's main browser profile to avoid
    conflicts when the browser is already running.

    Location: %LOCALAPPDATA%/BingRewardsBot/User Data
    """
    import os

    localappdata = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    )
    return localappdata / "BingRewardsBot" / "User Data"


def run(
    browser_path: str = "",
    profile: str = "Default",
    headless: bool = False,
    dryrun: bool = False,
) -> int:
    """Synchronous wrapper for run_daily_activities."""
    return asyncio.run(
        run_daily_activities(browser_path, profile, headless, dryrun)
    )


if __name__ == "__main__":
    run()
