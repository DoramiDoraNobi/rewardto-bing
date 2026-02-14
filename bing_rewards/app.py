# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import io
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterator

if os.name == 'posix':
    import signal

# Windows-specific imports for cookie extraction
if os.name == 'nt':
    try:
        import sqlite3
        import win32crypt
        import base64
        # Try to import Crypto, fallback if not available
        try:
            from Crypto.Cipher import AES
            CRYPTO_AVAILABLE = True
        except ImportError:
            CRYPTO_AVAILABLE = False
    except ImportError:
        CRYPTO_AVAILABLE = False
else:
    CRYPTO_AVAILABLE = False


from pynput import keyboard
from pynput.keyboard import Key

from bing_rewards import options as app_options


def get_chrome_cookies(profile_name: str = "Default") -> dict:
    """Extract Microsoft account cookies from Chrome profile.

    Args:
        profile_name: Chrome profile name to extract cookies from

    Returns:
        dict: Microsoft account related cookies
    """
    if not CRYPTO_AVAILABLE or os.name != 'nt':
        print("  Cookie extraction tidak tersedia di sistem ini")
        return {}

    try:
        # Chrome user data path
        chrome_path = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
        profile_path = chrome_path / profile_name
        cookies_db = profile_path / "Cookies"

        if not cookies_db.exists():
            print(f"  Database cookies tidak ditemukan: {cookies_db}")
            return {}

        # Copy database to avoid lock issues
        temp_db = cookies_db.with_suffix('.temp')
        import shutil
        shutil.copy2(cookies_db, temp_db)

        # Connect to cookies database
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()

        # Query Microsoft-related cookies
        microsoft_domains = [
            'login.live.com',
            'account.microsoft.com',
            'login.microsoftonline.com',
            'www.bing.com',
            '.microsoft.com',
            '.live.com'
        ]

        cookies = {}
        for domain in microsoft_domains:
            cursor.execute("""
                SELECT name, value, encrypted_value, host_key, path, expires_utc
                FROM cookies
                WHERE host_key LIKE ? OR host_key = ?
            """, (f'%{domain}%', domain))

            for row in cursor.fetchall():
                name, value, encrypted_value, host, path, expires = row

                # Decrypt if encrypted
                if encrypted_value:
                    try:
                        decrypted_value = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode()
                        value = decrypted_value
                    except Exception:
                        continue

                if value and name:
                    cookies[f"{host}_{name}"] = {
                        'name': name,
                        'value': value,
                        'domain': host,
                        'path': path,
                        'expires': expires
                    }

        conn.close()
        temp_db.unlink()  # Clean up temp file

        print(f" Berhasil extract {len(cookies)} cookies Microsoft")
        return cookies

    except Exception as e:
        print(f" Error extract cookies: {e}")
        return {}


def save_session_data(cookies: dict, profile_name: str) -> bool:
    """Save extracted session data for later use.

    Args:
        cookies: Extracted cookies dictionary
        profile_name: Profile name for saving

    Returns:
        bool: Success status
    """
    try:
        # Save to app data directory
        app_data = Path.home() / "AppData" / "Local" / "bing-rewards"
        app_data.mkdir(exist_ok=True)

        session_file = app_data / f"session_{profile_name}.json"

        with open(session_file, 'w') as f:
            json.dump({
                'timestamp': time.time(),
                'profile': profile_name,
                'cookies': cookies
            }, f, indent=2)

        print(f" Session data tersimpan: {session_file}")
        return True

    except Exception as e:
        print(f" Error simpan session: {e}")
        return False


def load_session_data(profile_name: str) -> dict:
    """Load previously saved session data.

    Args:
        profile_name: Profile name to load

    Returns:
        dict: Loaded session data or empty dict
    """
    try:
        app_data = Path.home() / "AppData" / "Local" / "bing-rewards"
        session_file = app_data / f"session_{profile_name}.json"

        if not session_file.exists():
            return {}

        with open(session_file, 'r') as f:
            data = json.load(f)

        # Check if session is not too old (24 hours)
        if time.time() - data.get('timestamp', 0) > 86400:
            print("  Session data sudah expired (>24 jam)")
            return {}

        print(f" Session data dimuat: {len(data.get('cookies', {}))} cookies")
        return data

    except Exception as e:
        print(f" Error load session: {e}")
        return {}


def word_generator() -> Iterator[str]:
    """Generate unique keywords for daily varied searches.

    This function now uses the daily_keywords module which:
    1. Uses 2000+ gaming-focused keywords
    2. Shuffles based on date (different order each day)
    3. Tracks used searches in 7-day rolling window
    4. Prevents repetition across days
    
    Yields:
        str: A unique keyword for searching.

    Raises:
        OSError: If there are issues accessing the keywords files.
    """
    try:
        # Import here to avoid circular imports
        from bing_rewards import daily_keywords
        
        print("\n[STATS] Keyword Statistics:")
        stats = daily_keywords.get_keyword_stats()
        print(f"   Gaming keywords available: {stats['gaming_available']}/{stats['gaming_keywords_total']}")
        print(f"   Recently used (7 days): {stats['recently_used_count']}")
        print(f"   Today's rotation seed: {stats['today_seed']}")
        print()
        
        # Use the daily keyword generator
        yield from daily_keywords.daily_keyword_generator(record_history=True)
        
    except ImportError:
        # Fallback to old method if daily_keywords module is not available
        print("Warning: daily_keywords module not found, using fallback method")
        word_data = resources.files('bing_rewards').joinpath('data', 'keywords.txt')
        
        while True:
            with (
                resources.as_file(word_data) as p,
                p.open(mode='r', encoding='utf-8') as fh,
            ):
                fh.seek(0, io.SEEK_END)
                size = fh.tell()

                if size == 0:
                    raise ValueError('Keywords file is empty')

                fh.seek(random.randint(0, size - 1), io.SEEK_SET)
                fh.readline()

                for raw_line in fh:
                    stripped_line = raw_line.strip()
                    if stripped_line:
                        yield stripped_line

                fh.seek(0)
                for raw_line in fh:
                    stripped_line = raw_line.strip()
                    if stripped_line:
                        yield stripped_line
                        
    except OSError as e:
        print(f'Error accessing keywords file: {e}')
        raise
    except Exception as e:
        print(f'Unexpected error in word generation: {e}')
        raise


def browser_cmd(exe: Path, agent: str, profile: str = '', force_location: str = '') -> list[str]:
    """Validate command to open Google Chrome with user-agent `agent`."""
    exe = Path(exe)
    if exe.is_file() and exe.exists():
        cmd = [str(exe.resolve())]
    elif pth := shutil.which(exe):
        cmd = [str(pth)]
    else:
        print(
            f'Command "{exe}" could not be found.\n'
            'Make sure it is available on PATH, '
            'or use the --exe flag to give an absolute path.'
        )
        sys.exit(1)

    
    # -------------------------------------------------------------------------
    # MODERN BYPASS TECHNIQUE: NATIVE IDENTITY (v3.5)
    # -------------------------------------------------------------------------
    # Do NOT force User-Agent for Desktop searches if we are just using the 
    # installed browser. Forcing UA creates a "Client Hints Mismatch" 
    # (Header vs Javascript features) which is a primary bot detection vector.
    #
    # Only force UA if:
    # 1. It is a Mobile search (we must emulate mobile)
    # 2. We are spoofing a completely different browser family (not implemented here)
    # -------------------------------------------------------------------------
    
    is_mobile_agent = 'Android' in agent or 'iPhone' in agent
    
    if is_mobile_agent:
        # For Mobile: We MUST spoof because we are on a Desktop PC
        cmd.extend([f'--user-agent="{agent}"'])
        # Add device emulation flags to make it more convincing
        cmd.extend(['--enable-viewport', '--force-device-scale-factor=1'])
    else:
        # For Desktop: USE NATIVE IDENTITY!
        # Don't add --user-agent flag. Let Chrome/Edge report its real dynamic version.
        # This fixes the "sec-ch-ua" mismatch problem.
        print(" 🛡️  Stealth: Menggunakan Native Browser Identity (No Fake UA)")

    cmd.append('--new-window')
    
    # STEALTH MODE: Advanced Anti-Detection Flags
    # These flags help hide the fact that the browser is being controlled by automation
    cmd.extend([
        # Crucial for bypassing "navigator.webdriver" check
        '--disable-blink-features=AutomationControlled',
        
        # Remove "Chrome is being controlled by automated test software" bar
        '--disable-infobars',
        '--exclude-switches=enable-automation',
        
        # Make the window look like a normal user session
        '--start-maximized',
        '--no-default-browser-check',
        '--no-first-run',
        
        # Disable background throttling to ensure scripts run smoothly
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding'
    ])
    
    # Force location for Bing Rewards
    if force_location:
        print(f" DEBUG: Menerapkan force location: {force_location}")
        # Add Chrome flags to override geolocation
        if force_location.upper() == 'US':
            cmd.extend([
                '--disable-geolocation',
                '--fake-geoposition=39.8283,-98.5795',  # Geographic center of US
                '--lang=en-US',
                '--accept-lang=en-US,en;q=0.9',
                '--disable-features=VizDisplayCompositor',
                # '--force-webrtc-ip-handling-policy=disable_non_proxied_udp', # Removed for cleaner fingerprint
                '--timezone-override-for-testing=America/New_York' # Try to enforce US TZ
            ])
            print(f" Force lokasi: United States (US)")
        elif force_location.upper() == 'UK':
            cmd.extend([
                '--disable-geolocation',
                '--fake-geoposition=51.5074,-0.1278',  # London, UK
                '--lang=en-GB',
                '--accept-lang=en-GB,en;q=0.9',
                '--disable-features=VizDisplayCompositor',
                # '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                '--timezone-override-for-testing=Europe/London'
            ])
            print(f" Force lokasi: United Kingdom (UK)")
        elif force_location.upper() == 'CA':
            cmd.extend([
                '--disable-geolocation',
                '--fake-geoposition=56.1304,-106.3468',  # Canada center
                '--lang=en-CA',
                '--accept-lang=en-CA,en;q=0.9',
                '--disable-features=VizDisplayCompositor',
                # '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                '--timezone-override-for-testing=America/Toronto'
            ])
            print(f" Force lokasi: Canada (CA)")
        elif force_location.upper() == 'AU':
            cmd.extend([
                '--disable-geolocation',
                '--fake-geoposition=-25.2744,133.7751',  # Australia center
                '--lang=en-AU',
                '--accept-lang=en-AU,en;q=0.9',
                '--disable-features=VizDisplayCompositor',
                # '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                '--timezone-override-for-testing=Australia/Sydney'
            ])
            print(f" Force lokasi: Australia (AU)")
        else:
            print(f"  Lokasi '{force_location}' tidak dikenal, menggunakan lokasi default")
        
        # Add additional flags to force US region for Bing
        if force_location.upper() == 'US':
            cmd.extend([
                '--host-rules=MAP *.bing.com 204.79.197.200',  # Force US Bing server
            ])
            print(" Menerapkan server Bing US map rule")
            print(" Menerapkan server Bing US dan optimasi tambahan")
    else:
        print(" DEBUG: Tidak ada force location yang diterapkan")
    
    # Switch to non default profile if supplied with valid string
    # NO CHECKING IS DONE if the profile exists
    if profile:
        cmd.extend([f'--profile-directory={profile}'])
    if os.environ.get('XDG_SESSION_TYPE', '').lower() == 'wayland':
        cmd.append('--ozone-platform=x11')
    return cmd


def open_browser(cmd: list[str]) -> subprocess.Popen:
    """Try to open a browser, and exit if the command cannot be found.

    Returns the subprocess.Popen object to handle the browser process.
    """
    try:
        # Open browser as a subprocess
        # Only if a new window should be opened
        if os.name == 'posix':
            chrome = subprocess.Popen(
                cmd, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, start_new_session=True
            )
        else:
            chrome = subprocess.Popen(cmd)
    except OSError as e:
        print('Unexpected error:', e)
        print(f"Running command: '{' '.join(cmd)}'")
        sys.exit(1)

    print(f'Opening browser [{chrome.pid}]')
    return chrome


def close_browser(chrome: subprocess.Popen | None):
    """Close the browser process if it exists and is still running.

    Args:
        chrome: The subprocess.Popen object representing the browser process, or None.
    """
    if chrome is None:
        return

    if chrome.poll() is not None:  # Check if the process has already terminated
        print(f'Browser [{chrome.pid}] has already terminated.')
        return

    print(f'Closing browser [{chrome.pid}]')
    try:
        if os.name == 'posix':
            os.killpg(chrome.pid, signal.SIGTERM)
            # Optionally wait for process termination to avoid zombies
            chrome.wait(timeout=5)  # Wait for up to 5 seconds
        else:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(chrome.pid)],
                capture_output=True,
                check=True,  # raise exception if taskkill fails
                timeout=5,
            )
    except ProcessLookupError:
        print(f'Browser process [{chrome.pid}] not found (already closed).')
    except subprocess.CalledProcessError as e:
        print(f'Error closing browser [{chrome.pid}]: {e}')
        print(f'Stderr: {e.stderr.decode()}')
    except subprocess.TimeoutExpired:
        print(f'Timeout while closing browser [{chrome.pid}].')
    except Exception as e:
        print(f'Unexpected error while closing browser [{chrome.pid}]: {e}')


def get_user_agent_for_location(location: str, is_mobile: bool = False) -> str:
    """Get appropriate user agent for specified location."""
    if is_mobile:
        mobile_agents = {
            'US': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'UK': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'CA': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'AU': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        }
        return mobile_agents.get(location.upper(), mobile_agents['US'])
    else:
        desktop_agents = {
            'US': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'UK': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'CA': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'AU': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }
        return desktop_agents.get(location.upper(), desktop_agents['US'])


def account_selection(options: Namespace) -> tuple[bool, bool, str]:
    """Handle account selection and login process.

    Opens browser to Microsoft login page, waits for user to login/logout,
    then returns control to the application.

    Args:
        options: Command line options and configuration

    Returns:
        tuple[bool, bool, str]: (success, force_clear_used, force_location)
    """
    print("\n" + "="*60)
    print("🔐 BING REWARDS - KONFIGURASI AWAL")
    print("="*60)

    # 1. BROWSER SELECTION
    try:
        from bing_rewards import browser_utils
        print("\n🔍 Memindai browser yang terinstall...")
        browsers = browser_utils.scan_system()
        
        if browsers:
            print("\nBrowser ditemukan:")
            browser_keys = list(browsers.keys())
            for i, key in enumerate(browser_keys, 1):
                name = browsers[key]['name']
                print(f"{i}. {name}")
            
            print(f"{len(browser_keys) + 1}. Gunakan setting manual (dari config)")
            
            while True:
                try:
                    choice = input(f"\nPilih browser (1-{len(browser_keys) + 1}): ").strip()
                    idx = int(choice) - 1
                    
                    if 0 <= idx < len(browser_keys):
                        selected_key = browser_keys[idx]
                        selected_browser = browsers[selected_key]
                        
                        # Update options with selected browser path
                        options.browser_path = selected_browser['executable']
                        print(f"✅ Menggunakan: {selected_browser['name']}")
                        
                        # 2. PROFILE SELECTION
                        profiles = selected_browser['profiles']
                        if profiles:
                            print(f"\nProfile ditemukan untuk {selected_browser['name']}:")
                            for i, prof in enumerate(profiles, 1):
                                print(f"{i}. {prof['name']} (ID: {prof['id']})")
                            
                            print(f"{len(profiles) + 1}. Profile Default")
                            
                            p_choice = input(f"\nPilih profile (1-{len(profiles) + 1}): ").strip()
                            try:
                                p_idx = int(p_choice) - 1
                                if 0 <= p_idx < len(profiles):
                                    selected_profile = profiles[p_idx]['id']
                                    options.profile = [selected_profile]
                                    print(f"✅ Menggunakan profile: {profiles[p_idx]['name']}")
                                else:
                                    print("⏩ Menggunakan Default Profile")
                                    options.profile = ["Default"]
                            except ValueError:
                                print("⏩ Menggunakan Default Profile")
                                options.profile = ["Default"]
                        else:
                            print("ℹ️ Tidak ada profile ditemukan, menggunakan Default.")
                            options.profile = ["Default"]
                        break
                        
                    elif idx == len(browser_keys):
                        print("⏩ Menggunakan setting manual dari config")
                        break
                    else:
                        print("❌ Pilihan tidak valid")
                except ValueError:
                    print("❌ Masukkan angka.")
        else:
            print("⚠️ Tidak ada browser terdeteksi secara otomatis.")
            
    except ImportError:
        print("⚠️ Module browser_utils tidak ditemukan.")
    except Exception as e:
        print(f"⚠️ Error saat scan browser: {e}")

    print("\n" + "="*60)
    print("🔐 ACCOUNT SELECTION MODE")
    print("="*60)
    print("1. Browser akan terbuka ke halaman login Microsoft")
    print("2. Logout dari akun yang sudah login (jika ada)")
    print("3. Login dengan akun yang diinginkan")
    print("4. Setelah login berhasil, tutup browser")
    print("5. Kembali ke terminal dan tekan ENTER untuk melanjutkan")
    print("6. Atau tekan ESC untuk membatalkan")
    print("="*60)

    # Default settings (login method and location menus disabled)
    login_url = "https://login.live.com"
    force_clear = False
    extract_session = False
    force_location = ""
    print("\n Menggunakan login via Microsoft Account (live.com)")
    print(" Menggunakan lokasi default/lokal")

    # Get the profile to use (first profile if multiple)
    profile_to_use = ""
    if hasattr(options, 'profile') and options.profile:
        if isinstance(options.profile, list):
            profile_to_use = options.profile[0]
        else:
            profile_to_use = options.profile

    # If force clear, use a fresh profile name to avoid old sessions
    if force_clear:
        profile_to_use = "BingRewardsClean"
        print(f" Menggunakan profile bersih: '{profile_to_use}'")
        print("   (Profile terpisah untuk menghindari konflik session)")

    # Use a more stealthy user agent for login
    login_agent = get_user_agent_for_location(force_location or "US", False)

    # Convert browser_path to Path object
    browser_path = Path(options.browser_path)

    # Add login URL directly to command
    cmd = browser_cmd(browser_path, login_agent, profile_to_use, force_location)

    # If force clear is enabled, add flags to clear browsing data
    if force_clear:
        print("\n FORCE CLEAR MODE AKTIF:")
        print("   - Akan membersihkan cookies dan session lama")
        print("   - Logout paksa dari semua akun Microsoft")
        print("   - Session baru akan tersimpan di profile normal")

        # Add Chrome flags to clear data but keep profile for saving session
        cmd.extend([
            "--clear-token-service",
            "--disable-background-mode",
            "--disable-extensions"
            # Removed --incognito so session can be saved!
        ])

        # Start with logout URL first to clear old sessions
        logout_url = "https://login.live.com/logout.srf"
        cmd.append(logout_url)

        print(f"    Membuka logout URL: {logout_url}")
        print("    Profile normal akan digunakan untuk menyimpan session")
    else:
        cmd.append(login_url)  # Open directly to login URL

    print(f"\n Menggunakan Chrome profile: '{profile_to_use or 'Default'}'")
    print("   (Profile yang sama akan digunakan untuk searching)")

    print(f"\n Membuka browser untuk login...")
    if force_clear:
        print(" Command: Chrome + Force Clear Mode")
    else:
        print(f" Command: {' '.join(cmd[:3])} ... {login_url}")

    try:
        # Open browser with login page
        if not options.dryrun:
            chrome = open_browser(cmd)
            print(f" Browser terbuka dengan PID: {chrome.pid}")
            if force_clear:
                print(" Mode Force Clear aktif - logout otomatis")
                time.sleep(4)  # Extra time for logout

                print("\n MANUAL CLEAR INSTRUCTIONS:")
                print("   1. Tekan Ctrl+Shift+Delete untuk buka Clear browsing data")
                print("   2. Pilih 'All time' dan centang semua opsi")
                print("   3. Klik 'Clear data'")
                print("   4. Atau biarkan saja jika tidak mau manual clear")
                print("   5. Lanjut dengan navigasi ke login...")
                time.sleep(3)

                # Navigate to login after logout
                print(f" Navigasi ke login: {login_url}")
                key_controller = keyboard.Controller()

                # Open new tab for login
                with key_controller.pressed(Key.ctrl):
                    key_controller.press('t')
                    key_controller.release('t')
                time.sleep(1)

                # Type login URL
                for char in login_url:
                    key_controller.tap(char)
                    time.sleep(0.02)
                key_controller.tap(Key.enter)
                print(" Navigasi ke login berhasil")
            else:
                print(f" Langsung membuka: {login_url}")
            time.sleep(2)  # Wait for browser to load

            print(f"\n INSTRUKSI LOGIN:")
            if force_clear:
                print("    MODE FORCE CLEAR AKTIF:")
                print("   1. Browser akan logout otomatis dari semua akun")
                print("   2. Tab baru akan terbuka untuk login")
                print("   3. Login dengan akun yang diinginkan (contoh: redlonz)")
                print("   4. Pastikan logout dari akun lama (miko) jika masih ada")
                print("   5.   WAJIB TUTUP browser setelah login selesai")
            elif "bing.com" in login_url:
                print("   1. Klik tombol 'Sign in' di pojok kanan atas")
                print("   2. Logout dari akun yang sudah ada (jika perlu ganti akun)")
                print("   3. Login dengan akun Microsoft yang diinginkan")
            else:
                print("   1. Login dengan akun Microsoft yang diinginkan")
                print("   2. Atau logout dulu jika sudah ada yang login dan ingin ganti akun")
            print("   3. Pastikan login berhasil")
            print("   4.   WAJIB TUTUP browser setelah selesai login")
            print("   5. Kembali ke terminal dan ikuti petunjuk selanjutnya")
            print("\n TIPS:")
            if force_clear:
                print("   - Mode ini membersihkan session lama secara paksa")
                print("   - Gunakan jika akun masih salah setelah login normal")
                print("   - Session baru akan tersimpan dengan benar")
            else:
                print("   - Jangan biarkan browser login tetap terbuka")
            print("   - Session login akan tersimpan di profile Chrome")
            print("   - Browser pencarian akan menggunakan profile yang sama")

        # Wait for user to complete login process
        print(f"\n Menunggu proses login selesai...")
        print("    PETUNJUK PENTING:")
        print("   - Selesaikan login di browser yang baru terbuka")
        print("   - WAJIB TUTUP browser setelah login selesai")
        print("   - Kemudian tekan ENTER di terminal ini untuk melanjutkan")
        print("   - Atau ketik 'exit' untuk membatalkan")
        print("     JANGAN tekan ENTER sebelum browser ditutup!")

        # Simple input method instead of complex keyboard events
        while True:
            try:
                user_input = input("\n  Tekan ENTER untuk melanjutkan (atau ketik 'exit' untuk batal): ").strip().lower()

                if user_input == 'exit':
                    print("\n Account selection dibatalkan")
                    if not options.dryrun:
                        close_browser(chrome)
                    return False, False, ""
                elif user_input == '' or user_input == 'enter':
                    # Check if browser is still running before proceeding
                    if not options.dryrun and chrome.poll() is None:
                        print("\n  Browser masih terbuka! Tutup browser terlebih dahulu sebelum menekan ENTER.")
                        print("   Ini penting untuk memastikan login tersimpan dengan benar.")
                        continue
                    print("\n Browser ditutup, melanjutkan dengan akun yang dipilih")
                    print("    Menunggu 3 detik untuk memastikan session tersimpan...")
                    time.sleep(3)  # Give time for session to be saved

                    # Extract session if smart mode is enabled
                    if extract_session:
                        print("\n SMART SESSION EXTRACT:")
                        print("    Mengambil cookies dan session data...")

                        # Extract cookies from Chrome profile
                        profile_for_extract = profile_to_use if not force_clear else "BingRewardsClean"
                        cookies = get_chrome_cookies(profile_for_extract)

                        if cookies:
                            # Save session data
                            if save_session_data(cookies, profile_for_extract):
                                print("    Session berhasil di-extract dan disimpan!")
                                print("    Browser search akan menggunakan session yang tepat")
                            else:
                                print("     Gagal simpan session, gunakan mode normal")
                        else:
                            print("     Tidak ada cookies Microsoft ditemukan")
                            print("    Fallback ke mode normal...")

                    return True, force_clear, force_location
                else:
                    print(" Input tidak valid. Tekan ENTER untuk melanjutkan atau ketik 'exit' untuk batal.")

            except KeyboardInterrupt:
                print("\n Account selection dibatalkan (CTRL+C)")
                if not options.dryrun:
                    close_browser(chrome)
                return False, False, ""

            # Auto-detect if browser is closed
            if not options.dryrun and chrome.poll() is not None:
                print("\n Browser ditutup otomatis, melanjutkan dengan akun yang dipilih")
                print("    Menunggu 3 detik untuk memastikan session tersimpan...")
                time.sleep(3)  # Give time for session to be saved

                # Extract session if smart mode is enabled
                if extract_session:
                    print("\n SMART SESSION EXTRACT (Auto-detect):")
                    print("    Mengambil cookies dan session data...")

                    profile_for_extract = profile_to_use if not force_clear else "BingRewardsClean"
                    cookies = get_chrome_cookies(profile_for_extract)

                    if cookies:
                        if save_session_data(cookies, profile_for_extract):
                            print("    Session berhasil di-extract dan disimpan!")
                        else:
                            print("     Gagal simpan session")
                    else:
                        print("     Tidak ada cookies Microsoft ditemukan")

                return True, force_clear, force_location

    except Exception as e:
        print(f"\n Error dalam account selection: {e}")
        return False, False, ""


def search(count: int, words_gen: Iterator[str], agent: str, options: Namespace, force_clear_used: bool = False, force_location: str = ""):
    """Perform the actual searches in a browser.

    Open a chromium browser window with specified `agent` string, complete `count`
    searches from list `words`, finally terminate browser process on completion.
    """
    chrome = None
    if not options.no_window:
        # Convert browser_path to Path object for consistency
        browser_path = Path(options.browser_path)

        # Get the profile to use (same as login if force clear was used)
        profile_to_use = ""
        if hasattr(options, 'profile') and options.profile:
            if isinstance(options.profile, list):
                profile_to_use = options.profile[0]
            else:
                profile_to_use = options.profile

        # Use same clean profile if force clear was used
        if force_clear_used:
            profile_to_use = "BingRewardsClean"
            print(f" Menggunakan profile bersih untuk search: '{profile_to_use}'")

        cmd = browser_cmd(browser_path, agent, profile_to_use, force_location)

        # If account selection was used, add Bing homepage to refresh session
        if options.account_select:
            if force_location and force_location.upper() == 'US':
                # Use US-specific Bing URL
                cmd.append("https://www.bing.com/?cc=us&setlang=en-us")
                print(" Membuka Bing US dengan parameter region")
            elif force_location and force_location.upper() == 'UK':
                cmd.append("https://www.bing.com/?cc=gb&setlang=en-gb")
                print(" Membuka Bing UK dengan parameter region")
            elif force_location and force_location.upper() == 'CA':
                cmd.append("https://www.bing.com/?cc=ca&setlang=en-ca")
                print(" Membuka Bing CA dengan parameter region")
            elif force_location and force_location.upper() == 'AU':
                cmd.append("https://www.bing.com/?cc=au&setlang=en-au")
                print(" Membuka Bing AU dengan parameter region")
            else:
                cmd.append("https://www.bing.com")
                
            print(f" Membuka browser pencarian dengan profile: '{profile_to_use or 'Default'}'")
            if force_clear_used:
                print("   Menggunakan session bersih dari login sebelumnya...")
            elif force_location:
                print(f"   Menggunakan lokasi: {force_location}")
            else:
                print("   Memuat ulang session untuk memastikan akun yang benar...")

        if not options.dryrun:
            chrome = open_browser(cmd)

    # Wait for Chrome to load with some randomization
    # Give extra time after account selection to ensure session is loaded
    base_delay = options.load_delay
    if options.account_select:
        base_delay += 3.0  # Extra delay after account selection
    random_delay = random.uniform(0.5, 1.5)  # Add 0.5-1.5 seconds random delay
    time.sleep(base_delay + random_delay)

    # If account selection was used, verify we're using the right account
    if options.account_select and not options.dryrun:
        print("\n Memverifikasi akun yang sedang login...")

        # Navigate to Bing to check current account
        key_controller = keyboard.Controller()

        # Focus address bar and go to Bing
        with key_controller.pressed(Key.ctrl):
            key_controller.press('l')
            key_controller.release('l')
        time.sleep(0.5)

        # Type Bing URL
        bing_url = "https://www.bing.com"
        for char in bing_url:
            key_controller.tap(char)
            time.sleep(0.02)
        key_controller.tap(Key.enter)

        time.sleep(3)  # Wait for Bing to load

        print(" VERIFIKASI AKUN:")
        print("   1. Periksa pojok kanan atas halaman Bing")
        print("   2. Pastikan akun yang login sudah benar")
        print("   3. Jika akun salah, tekan CTRL+C untuk batal")
        print("   4. Jika akun sudah benar, searching akan dimulai dalam 5 detik...")
        print("   ⚠️  JANGAN sentuh mouse atau keyboard saat browser terbuka!")
        
        time.sleep(5)  # Give user time to verify

    # keyboard controller from pynput
    key_controller = keyboard.Controller()

    # Ctrl + E to open address bar with the default search engine
    # Alt + D focuses address bar without using search engine
    key_mod, key = (Key.ctrl, 'e') if options.bing else (Key.alt, 'd')

    for i in range(count):
        # Get a random query from set of words
        query = next(words_gen)

        # If user's default search engine is Bing, type the query to the address bar directly
        # Otherwise, form the bing.com search url with location-specific parameters
        if options.bing:
            search_url = query
        else:
            # Use location-specific search URLs
            if force_location and force_location.upper() == 'US':
                search_url = f"https://www.bing.com/search?q={quote_plus(query)}&cc=us&setlang=en-us&form=QBRE"
            elif force_location and force_location.upper() == 'UK':
                search_url = f"https://www.bing.com/search?q={quote_plus(query)}&cc=gb&setlang=en-gb&form=QBRE"
            elif force_location and force_location.upper() == 'CA':
                search_url = f"https://www.bing.com/search?q={quote_plus(query)}&cc=ca&setlang=en-ca&form=QBRE"
            elif force_location and force_location.upper() == 'AU':
                search_url = f"https://www.bing.com/search?q={quote_plus(query)}&cc=au&setlang=en-au&form=QBRE"
            else:
                search_url = options.search_url + quote_plus(query)

        # Use pynput to trigger keyboard events and type search queries
        if not options.dryrun:
            # Add small random delay before each search to appear more human
            pre_search_delay = random.uniform(0.2, 0.8)
            time.sleep(pre_search_delay)

            # Retry focus mechanism
            for _ in range(2):
                with key_controller.pressed(key_mod):
                    key_controller.press(key)
                    key_controller.release(key)
                time.sleep(0.2)

            if options.ime:
                key_controller.tap(Key.shift)

            # Random delay after opening address bar
            time.sleep(random.uniform(0.1, 0.3))

            # Fix for double URL issue: ensure address bar is cleared
            # Alt+D usually selects all, but sometimes it puts cursor at end
            # We explicitly Select All + Backspace to be safe
            with key_controller.pressed(Key.ctrl):
                key_controller.tap('a')
            time.sleep(0.05)
            key_controller.tap(Key.backspace)
            time.sleep(0.05)

            # Type the url into the address bar with slightly randomized delays
            for char in search_url + '\n':
                key_controller.tap(char)
                # Vary typing speed to seem more human-like
                char_delay = random.uniform(0.02, 0.05)
                time.sleep(char_delay)
            key_controller.tap(Key.enter)

        print(f'Search {i + 1}: {query}')

        # Delay to let page load with increased randomization
        match options.search_delay:
            case int(x) | float(x) | [float(x)]:
                base_delay = x
                # Add random variance to make timing less predictable
                delay = base_delay + random.uniform(-0.5, 1.0)
            case [float(min_s), float(max_s)] | [int(min_s), int(max_s)]:
                delay = random.uniform(min_s, max_s)
            case other:
                # catastrophic failure
                raise ValueError(f'Invalid configuration format: "search_delay": {other!r}')

        # Ensure minimum delay for safety
        delay = max(delay, 1.0)
        time.sleep(delay)

    # Skip killing the window if exit flag set
    if options.no_exit:
        return

    close_browser(chrome)


def main():
    """Program entrypoint.

    Loads keywords from a file, interprets command line arguments
    and executes search function in separate thread.
    Setup listener callback for ESC key.
    """
    options = app_options.get_options()
    words_gen = word_generator()

    # Account selection phase
    force_clear_used = False
    force_location = ""
    if not options.dryrun and options.account_select:
        print(" Bing Rewards Searcher")
        print("Memulai proses account selection...")

        success, force_clear_used, force_location = account_selection(options)
        if not success:
            print(" Program dibatalkan oleh pengguna")
            sys.exit(0)

        if force_clear_used:
            print("\n Force Clear berhasil - session lama dibersihkan")
        
        if force_location:
            print(f"\n Lokasi reward dipaksa ke: {force_location}")

        print("\n" + "="*60)
        print(" MEMULAI PENCARIAN")
        print("="*60)

        # Add a small delay to ensure account is properly set
        time.sleep(2)
    elif not options.dryrun:
        print(" Bing Rewards Searcher")
        print("  Account selection dilewati (--no-account-select)")
        print("\n" + "="*60)
        print(" MEMULAI PENCARIAN")
        print("="*60)

    def desktop(profile=''):
        # Complete search with desktop settings
        count = options.count if 'count' in options else options.desktop_count
        print(f'Doing {count} desktop searches using "{profile}"')
        if force_location:
            print(f' Menggunakan lokasi: {force_location}')

        temp_options = options
        temp_options.profile = profile
        # Use location-specific user agent
        desktop_agent = get_user_agent_for_location(force_location or "US", False) if force_location else options.desktop_agent
        search(count, words_gen, desktop_agent, temp_options, force_clear_used, force_location)
        print('Desktop Search complete!\n')

    def mobile(profile=''):
        # Complete search with mobile settings
        count = options.count if 'count' in options else options.mobile_count
        print(f'Doing {count} mobile searches using "{profile}"')
        if force_location:
            print(f' Menggunakan lokasi mobile: {force_location}')

        temp_options = options
        temp_options.profile = profile
        # Use location-specific mobile user agent
        mobile_agent = get_user_agent_for_location(force_location or "US", True) if force_location else options.mobile_agent
        search(count, words_gen, mobile_agent, temp_options, force_clear_used, force_location)
        print('Mobile Search complete!\n')

    def both(profile=''):
        desktop(profile)
        mobile(profile)

    # ── Daily Activities (run BEFORE search to earn points first) ──
    if options.daily and not options.dryrun:
        print("\n" + "=" * 60)
        print("🎯 MENJALANKAN DAILY ACTIVITIES")
        print("=" * 60)

        try:
            from bing_rewards import daily_activities

            profile_for_daily = "Default"
            if hasattr(options, 'profile') and options.profile:
                if isinstance(options.profile, list):
                    profile_for_daily = options.profile[0]
                else:
                    profile_for_daily = options.profile

            daily_activities.run(
                browser_path=str(options.browser_path),
                profile=profile_for_daily,
                dryrun=options.dryrun,
            )
        except ImportError:
            print("  ❌ Playwright belum terinstall!")
            print("     Jalankan: pip install playwright")
        except Exception as e:
            print(f"  ❌ Error daily activities: {e}")

        print("\n" + "=" * 60)
        print("🔍 MELANJUTKAN KE SEARCH AUTOMATION")
        print("=" * 60)
        time.sleep(2)

    # Execute main method in a separate thread
    if options.desktop:
        target_func = desktop
    elif options.mobile:
        target_func = mobile
    else:
        # If neither mode is specified, complete both modes
        target_func = both

    # Run for each specified profile (defaults to ['Default'])
    for profile in options.profile:
        # Start the searching in separate thread
        search_thread = threading.Thread(target=target_func, args=(profile,), daemon=True)
        search_thread.start()

        print('Press ESC to quit searching')

        try:
            # Listen for keyboard events and exit if ESC pressed
            while search_thread.is_alive():
                with keyboard.Events() as events:
                    event = events.get(timeout=0.5)  # block for 0.5 seconds
                    # Exit if ESC key pressed
                    if event and event.key == Key.esc:
                        print('ESC pressed, terminating')
                        return  # Exit the entire function if ESC is pressed

        except KeyboardInterrupt:
            print('CTRL-C pressed, terminating')
            return  # Exit the entire function if CTRL-C is pressed

        # Wait for the current profile's searches to complete
        search_thread.join()

    # Open rewards dashboard
    if options.open_rewards and not options.dryrun:
        webbrowser.open_new('https://account.microsoft.com/rewards')

