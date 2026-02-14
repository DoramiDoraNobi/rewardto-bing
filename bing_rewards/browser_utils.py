# SPDX-FileCopyrightText: 2026 Bing Rewards Enhancement
#
# SPDX-License-Identifier: MIT

"""Utilities for detecting installed browsers and user profiles."""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def get_local_appdata() -> Path:
    """Get Local AppData directory."""
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    return Path.home() / '.config'  # Linux fallback (approximate)


def get_program_files() -> List[Path]:
    """Get Program Files directories."""
    paths = []
    if os.environ.get('ProgramFiles'):
        paths.append(Path(os.environ['ProgramFiles']))
    if os.environ.get('ProgramFiles(x86)'):
        paths.append(Path(os.environ['ProgramFiles(x86)']))
    return paths


BROWSERS = {
    'edge': {
        'name': 'Microsoft Edge',
        'exe': 'msedge.exe',
        'app_paths': [
            'Microsoft/Edge/Application',
            'Microsoft/Edge Beta/Application',
            'Microsoft/Edge Dev/Application'
        ],
        'user_data': ['Microsoft/Edge/User Data']
    },
    'chrome': {
        'name': 'Google Chrome',
        'exe': 'chrome.exe',
        'app_paths': ['Google/Chrome/Application'],
        'user_data': ['Google/Chrome/User Data']
    },
    'brave': {
        'name': 'Brave Browser',
        'exe': 'brave.exe',
        'app_paths': ['BraveSoftware/Brave-Browser/Application'],
        'user_data': ['BraveSoftware/Brave-Browser/User Data']
    }
}


def find_browser_executable(browser_key: str) -> Optional[Path]:
    """Find executable path for a specific browser."""
    if browser_key not in BROWSERS:
        return None
        
    browser_info = BROWSERS[browser_key]
    exe_name = browser_info['exe']
    
    # Check common installation locations
    search_dirs = get_program_files()
    search_dirs.append(get_local_appdata())  # Some user-level installs
    
    for base_dir in search_dirs:
        for app_path in browser_info['app_paths']:
            exe_path = base_dir / app_path / exe_name
            if exe_path.exists():
                return exe_path
                
    # Check PATH
    if shutil.which(exe_name):
        return Path(shutil.which(exe_name))
        
    return None


def get_browser_profiles(browser_key: str) -> List[Dict[str, str]]:
    """Scan for user profiles for a specific browser.
    
    Returns:
        List of dicts with 'id' (folder name) and 'name' (display name).
    """
    if browser_key not in BROWSERS:
        return []
        
    browser_info = BROWSERS[browser_key]
    local_appdata = get_local_appdata()
    
    profiles = []
    
    for user_data_rel in browser_info['user_data']:
        user_data_path = local_appdata / user_data_rel
        if not user_data_path.exists():
            continue
            
        # 1. Try reading Local State file for list of profiles
        local_state_path = user_data_path / 'Local State'
        if local_state_path.exists():
            try:
                with open(local_state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                profile_info_cache = data.get('profile', {}).get('info_cache', {})
                for profile_dir, info in profile_info_cache.items():
                    name = info.get('name', profile_dir)
                    profiles.append({'id': profile_dir, 'name': name})
            except Exception as e:
                print(f"Error reading Local State for {browser_key}: {e}")
        
        # 2. If no profiles found yet (or just Default), scan directories manually
        # "Default" usually exists but might not be in Local State in some versions
        if not profiles:
            potential_dirs = ['Default'] + [f'Profile {i}' for i in range(1, 20)]
            for p_dir in potential_dirs:
                pref_path = user_data_path / p_dir / 'Preferences'
                if pref_path.exists():
                    try:
                        with open(pref_path, 'r', encoding='utf-8') as f:
                            pref_data = json.load(f)
                        
                        # Try to get Google profile name
                        name = pref_data.get('profile', {}).get('name', p_dir)
                        
                        # Check for existing entry
                        if not any(p['id'] == p_dir for p in profiles):
                            profiles.append({'id': p_dir, 'name': name})
                    except:
                        # If error reading preferences, just add directory name
                        if not any(p['id'] == p_dir for p in profiles):
                            profiles.append({'id': p_dir, 'name': p_dir})

    # Sort profiles: Default first, then others
    profiles.sort(key=lambda x: (x['id'] != 'Default', x['name']))
    return profiles


def scan_system() -> Dict[str, Dict]:
    """Scan system for all supported browsers and their profiles."""
    results = {}
    
    for key, info in BROWSERS.items():
        exe_path = find_browser_executable(key)
        if exe_path:
            profiles = get_browser_profiles(key)
            results[key] = {
                'name': info['name'],
                'executable': str(exe_path),
                'profiles': profiles
            }
            
    return results


if __name__ == '__main__':
    print("Scanning system for browsers...")
    detected = scan_system()
    print(json.dumps(detected, indent=2))
